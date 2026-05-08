"""
main.py — replaces `adk web` entirely.

Runs a single FastAPI server that:
  1. Imports your ADK agent directly (no subprocess)
  2. Manages sessions
  3. Streams responses via SSE
  4. Serves your custom HTML/CSS/JS frontend

Run with:
    python main.py
  OR
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Then open: http://localhost:8000
"""

import os
import uuid
import json
import asyncio
import html
import re
from datetime import datetime
from pathlib import Path

# ── Load environment variables ────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

# ── ADK imports ───────────────────────────────────────────────────────────────
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# ── Import YOUR agent ─────────────────────────────────────────────────────────
# Update this import to match your agent module / root_agent variable name.
# e.g. if your file is ../travel_agent/agent.py with `root_agent` defined:
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))   # agent is one level up

try:
    # Import the travel_concierge agent from this repository.
    # Update this line if you want to use a different agent module.
    from travel_concierge.agent import root_agent
    APP_NAME = "travel_concierge"
except ImportError as e:
    print(f"\n⚠️  Could not import agent: {e}")
    print("   Edit thetravel_concierge import at the top of main.py to point to your agent.\n")
    raise

# ── Session service & runner ──────────────────────────────────────────────────
session_service = InMemorySessionService()

# Verify API key is available
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("⚠️  GOOGLE_API_KEY not found in environment variables. Please check your .env file.")

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="TravelBot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
PDF_DIR = Path(__file__).parent / "generated_pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")


# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str = "user"


class PdfRequest(BaseModel):
    itinerary_text: str
    session_id: str | None = None
    title: str | None = None


def _normalize_pdf_text(text: str) -> str:
    cleaned = str(text).replace("\r\n", "\n")
    cleaned = re.sub(r"[\t ]+", " ", cleaned)
    cleaned = re.sub(r"\s*(#{1,6}\s+)", r"\n\1", cleaned)
    cleaned = re.sub(r"\s+(?=[\-–—•]\s+[A-Za-z0-9])", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_emojis(text: str) -> str:
    return re.sub(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\uFE0F]",
        "",
        text,
    ).strip()


def _format_pdf_inline(text: str) -> str:
    formatted = html.escape(_strip_emojis(text))
    formatted = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", formatted)
    formatted = re.sub(r"\*(.+?)\*", r"<i>\1</i>", formatted)
    return formatted.replace("\n", "<br/>")


def _slugify_filename(text: str, fallback: str = "itinerary") -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:40] or fallback


def _build_pdf_story(itinerary_text: str, title: str) -> list:
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "TravelPdfTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=10,
    )
    subtitle_style = ParagraphStyle(
        "TravelPdfSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6b7a99"),
        spaceAfter=10,
    )
    heading_styles = {
        1: ParagraphStyle(
            "TravelPdfHeading1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1a56db"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        2: ParagraphStyle(
            "TravelPdfHeading2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1a1a2e"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        3: ParagraphStyle(
            "TravelPdfHeading3",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1a1a2e"),
            spaceBefore=6,
            spaceAfter=3,
        ),
    }
    body_style = ParagraphStyle(
        "TravelPdfBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "TravelPdfBullet",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=0,
        bulletIndent=0,
        spaceAfter=3,
    )

    normalized_text = _normalize_pdf_text(itinerary_text)
    lines = normalized_text.split("\n")

    story.append(Paragraph(_format_pdf_inline(title), title_style))
    story.append(Paragraph("Generated from the TravelBot itinerary response.", subtitle_style))
    story.append(Spacer(1, 0.3 * cm))

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 0.18 * cm))
            continue

        if line == "---":
            story.append(Spacer(1, 0.18 * cm))
            story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#d9e2ef")))
            story.append(Spacer(1, 0.18 * cm))
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = min(len(heading_match.group(1)), 3)
            heading_text = heading_match.group(2).strip()
            story.append(Paragraph(_format_pdf_inline(heading_text), heading_styles[level]))
            continue

        bullet_match = re.match(r"^([-•*])\s+(.*)$", line)
        if bullet_match:
            bullet_text = bullet_match.group(2).strip()
            story.append(Paragraph(f"• {_format_pdf_inline(bullet_text)}", bullet_style))
            continue

        story.append(Paragraph(_format_pdf_inline(line), body_style))

    return story


def _write_pdf_file(pdf_path: Path, itinerary_text: str, title: str) -> None:
    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=title,
        author="TravelBot",
    )
    document.build(_build_pdf_story(itinerary_text, title))


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    html = (Path(__file__).parent / "static" / "index.html").read_text()
    return HTMLResponse(content=html)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Accepts a message, runs it through the ADK agent,
    and streams SSE tokens back to the browser.
    """
    session_id = req.session_id or str(uuid.uuid4())
    user_id    = req.user_id

    # Create session if it doesn't exist
    existing = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not existing:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    user_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=req.message)],
    )

    async def event_generator():
        # Send session ID first so browser can persist it
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_message,
            ):
                # Stream text tokens as they arrive
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text and event.content.role == "model":
                            yield f"data: {json.dumps({'type': 'token', 'text': part.text})}\n\n"

                # Signal end of turn
                if event.is_final_response():
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'⚠️ Agent error: {str(e)}'})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/itinerary/pdf")
async def create_itinerary_pdf(req: PdfRequest):
    itinerary_text = req.itinerary_text.strip()
    if not itinerary_text:
        raise HTTPException(status_code=400, detail="No itinerary text was provided.")

    normalized_text = _normalize_pdf_text(itinerary_text)
    first_heading = re.search(r"^#\s+(.*)$", normalized_text, flags=re.MULTILINE)
    title_text = req.title or (first_heading.group(1).strip() if first_heading else "Travel Itinerary")
    safe_prefix = _slugify_filename(title_text)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    session_prefix = _slugify_filename(req.session_id or "session")
    filename = f"{safe_prefix}-{session_prefix}-{timestamp}-{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = PDF_DIR / filename

    _write_pdf_file(pdf_path, normalized_text, title_text)

    return {
        "filename": filename,
        "download_url": f"/pdfs/{filename}",
        "stored_path": str(pdf_path),
    }


if __name__ == "__main__":
    import uvicorn
    print(f"\n  TravelBot  →  http://localhost:8000\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)