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
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str = "user"


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


if __name__ == "__main__":
    import uvicorn
    print(f"\n  TravelBot  →  http://localhost:8000\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)