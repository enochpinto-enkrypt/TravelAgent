"""Search helpers for travel use-cases (news, hotels, and flights)."""

import logging
import os
from typing import Any, Dict, List
from urllib.parse import unquote, urlparse, parse_qs

import requests
from travel_concierge.tools.flights import search_flights_playwright
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import google_search

logger = logging.getLogger(__name__)

_search_agent = Agent(
    model="gemini-2.5-flash",
    name="google_search_grounding",
    description="An agent providing Google-search grounding capability",
    instruction=""",
    Answer the user's question directly using google_search grounding tool; Provide a brief but concise response. 
    Rather than a detail response, provide the immediate actionable item for a tourist or traveler, in a single sentence.
    Do not ask the user to check or look up information for themselves, that's your role; do your best to be informative.
    IMPORTANT: 
    - Always return your response in bullet points
    - Specify what it matters to the user
    - Add a random joke at the end of your response
    """,
    tools=[google_search],
)

google_search_grounding = AgentTool(agent=_search_agent)


DEFAULT_MAX_RESULTS = 3
MAX_SNIPPET_CHARS = 140


def _trim_text(text: str, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    """Trim long text to reduce downstream prompt tokens."""
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "..."


def _compact_results(items: List[Dict[str, Any]], max_results: int) -> List[Dict[str, str]]:
    """Normalize, deduplicate and cap payload size for search results."""
    capped = max(1, min(max_results, 5))
    seen_links = set()
    compacted: List[Dict[str, str]] = []

    for item in items:
        link = (item.get("link") or item.get("url") or item.get("href") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        title = _trim_text(item.get("title") or item.get("name") or "", 90)
        snippet = _trim_text(item.get("snippet") or item.get("description") or item.get("body") or "")
        compacted.append({"title": title, "snippet": snippet, "link": link})

        if len(compacted) >= capped:
            break

    return compacted


def _google_custom_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Backward-compatible wrapper now powered by Brave/DuckDuckGo instead of Google APIs."""
    return _web_search(query=query, max_results=max_results)


def _duckduckgo_api_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Optional no-key DuckDuckGo Instant Answer API enrichment."""
    api_url = os.getenv("DUCKDUCKGO_API_URL", "https://api.duckduckgo.com/")

    try:
        response = requests.get(
            api_url,
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return {"error": f"DuckDuckGo API request failed: {exc}"}

    results: List[Dict[str, Any]] = []
    abstract_text = payload.get("AbstractText", "") if isinstance(payload, dict) else ""
    abstract_url = payload.get("AbstractURL", "") if isinstance(payload, dict) else ""
    heading = payload.get("Heading", "") if isinstance(payload, dict) else ""
    if abstract_text and abstract_url:
        results.append({"title": heading or "DuckDuckGo Instant Answer", "snippet": abstract_text, "link": abstract_url})

    related = payload.get("RelatedTopics", []) if isinstance(payload, dict) else []
    for topic in related:
        if len(results) >= max(1, min(max_results, 10)):
            break
        if isinstance(topic, dict) and topic.get("FirstURL") and topic.get("Text"):
            results.append(
                {
                    "title": topic.get("Text", "").split(" - ")[0],
                    "snippet": topic.get("Text", ""),
                    "link": topic.get("FirstURL", ""),
                }
            )

    if not results:
        return {"error": "DuckDuckGo Instant Answer API returned no useful results.", "query": query}

    compacted = _compact_results(results, max_results)
    if not compacted:
        return {"error": "DuckDuckGo Instant Answer API returned no useful results."}
    return {"source": "duckduckgo_instant_api", "results": compacted}


def _extract_duckduckgo_redirect(url: str) -> str:
    """Resolve DuckDuckGo redirect links to destination URL when possible."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
    except Exception:
        pass
    return url


def _duckduckgo_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Fallback HTML search parser that does not require an API key."""
    try:
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"DuckDuckGo search request failed: {exc}"}

    html = response.text
    results: List[Dict[str, Any]] = []
    chunks = html.split('<div class="result')
    for chunk in chunks[1:]:
        if len(results) >= max(1, min(max_results, 10)):
            break
        href_marker = 'href="'
        href_pos = chunk.find(href_marker)
        if href_pos == -1:
            continue
        href_start = href_pos + len(href_marker)
        href_end = chunk.find('"', href_start)
        if href_end == -1:
            continue
        raw_link = chunk[href_start:href_end]
        link = _extract_duckduckgo_redirect(raw_link)

        title_start = chunk.find('>')
        title_end = chunk.find('</a>', title_start)
        if title_start == -1 or title_end == -1:
            title = ""
        else:
            title = (
                chunk[title_start + 1 : title_end]
                .replace("<b>", "")
                .replace("</b>", "")
                .strip()
            )

        snippet = ""
        snippet_marker = 'class="result__snippet">'
        snippet_pos = chunk.find(snippet_marker)
        if snippet_pos != -1:
            snippet_start = snippet_pos + len(snippet_marker)
            snippet_end = chunk.find("</a>", snippet_start)
            if snippet_end != -1:
                snippet = (
                    chunk[snippet_start:snippet_end]
                    .replace("<b>", "")
                    .replace("</b>", "")
                    .strip()
                )

        if link:
            results.append({"title": title, "snippet": snippet, "link": link})

    compacted = _compact_results(results, max_results)
    if not compacted:
        return {"error": "DuckDuckGo returned no parseable results."}

    return {"source": "duckduckgo_html", "results": compacted}


def _web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> Dict[str, Any]:
    """Search provider chain: keyless DuckDuckGo HTML first, then optional API enrichment."""
    ddg = _duckduckgo_web_search(query=query, max_results=max_results)
    if ddg.get("results"):
        return ddg

    ddg_api = _duckduckgo_api_search(query=query, max_results=max_results)
    if ddg_api.get("results"):
        return ddg_api

    return {"error": "No results from DuckDuckGo providers."}


def search_available_hotels(
    destination: str,
    check_in_date: str = "",
    check_out_date: str = "",
    guests: int = 2,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> Dict[str, Any]:
    """Search hotel availability pages for a destination using Brave/DuckDuckGo."""
    date_part = ""
    if check_in_date and check_out_date:
        date_part = f" check-in {check_in_date} check-out {check_out_date}"
    elif check_in_date:
        date_part = f" check-in {check_in_date}"

    query = (
        f"available hotels in {destination}{date_part} for {guests} guests "
        "booking options"
    )
    return _web_search(query=query, max_results=max_results)


def search_flights_to_destination(
    origin: str,
    destination: str,
    departure_date: str = "",
    return_date: str = "",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> Dict[str, Any]:
    """Search flight options for an origin-destination route using scraper only."""
    logger.warning(
        "[flights] search_flights_to_destination_called origin=%s destination=%s departure_date=%s return_date=%s",
        origin,
        destination,
        departure_date,
        return_date,
    )

    play_results = search_flights_playwright(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        max_results=max_results,
    )
    if play_results.get("results"):
        logger.warning("[flights] scraper_results_returned count=%s", len(play_results.get("results", [])))
        return play_results

    logger.warning("[flights] scraper_returned_no_results error=%s", play_results.get("error", "unknown"))
    return {
        "source": "flight_scraper",
        "error": play_results.get("error", "Flight scraping did not return results."),
        "results": [],
    }