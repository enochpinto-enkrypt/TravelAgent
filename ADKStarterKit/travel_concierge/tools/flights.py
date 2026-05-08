import asyncio
import logging
import re
import threading
from datetime import datetime
from typing import Any, Dict, List

try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None  # gracefully degrade if playwright not installed


logger = logging.getLogger(__name__)


_LOCATION_CODE_MAP = {
    "bangalore": "in",
    "bengaluru": "in",
    "india": "in",
    "kochi": "cok",
    "cochin": "cok",
}


def _format_result(title: str, price: str, link: str, airline: str) -> Dict[str, str]:
    return {"title": title or "Flight option", "price": price or "", "link": link or "", "airline": airline or ""}


def _location_to_code(value: str) -> str:
    clean = (value or "").strip().lower()
    if clean in _LOCATION_CODE_MAP:
        return _LOCATION_CODE_MAP[clean]
    alnum = re.sub(r"[^a-z0-9]", "", clean)
    return (alnum[:3] or "any").lower()


def _normalize_date_token(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""

    # Remove ordinal suffixes like 1st, 2nd, 17th.
    raw = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", raw)
    raw = re.sub(r"\s+", " ", raw)

    patterns = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %b",
        "%d %B",
    ]

    for pattern in patterns:
        try:
            parsed = datetime.strptime(raw, pattern)
            if "%Y" not in pattern:
                parsed = parsed.replace(year=datetime.utcnow().year)
            return parsed.strftime("%y%m%d")
        except ValueError:
            continue

    # Already in compact YYYYMMDD.
    if re.fullmatch(r"\d{8}", raw):
        return datetime.strptime(raw, "%Y%m%d").strftime("%y%m%d")

    # Already in compact YYMMDD.
    if re.fullmatch(r"\d{6}", raw):
        return raw

    return ""


def search_flights_playwright(
    origin: str,
    destination: str,
    departure_date: str = "",
    return_date: str = "",
    max_results: int = 3,
) -> Dict[str, Any]:
    """Attempt to scrape a flight aggregator (Skyscanner) using Playwright.

    This is a best-effort scraper intended to return a small list of candidate
    flight options (title, price, link). It requires the `playwright` package
    and browser binaries (`playwright install`). If Playwright is not
    available this function returns an error dictionary.
    """
    logger.warning(
        "[flights] scraper_triggered origin=%s destination=%s departure_date=%s return_date=%s",
        origin,
        destination,
        departure_date,
        return_date,
    )

    if not async_playwright:
        logger.warning("[flights] playwright_not_installed")
        return {"error": "playwright not installed"}

    def _run_in_new_thread() -> Dict[str, Any]:
        result_box: Dict[str, Any] = {}
        err_box: Dict[str, Exception] = {}

        def _target() -> None:
            try:
                result_box["value"] = asyncio.run(
                    _search_flights_playwright_async(
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        return_date=return_date,
                        max_results=max_results,
                    )
                )
            except Exception as exc:
                err_box["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join()

        if "error" in err_box:
            raise err_box["error"]
        return result_box.get("value", {"error": "Unknown threading error."})

    try:
        asyncio.get_running_loop()
        return _run_in_new_thread()
    except RuntimeError:
        return asyncio.run(
            _search_flights_playwright_async(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                max_results=max_results,
            )
        )


async def _search_flights_playwright_async(
    origin: str,
    destination: str,
    departure_date: str = "",
    return_date: str = "",
    max_results: int = 3,
) -> Dict[str, Any]:
    origin_code = _location_to_code(origin)
    destination_code = _location_to_code(destination)
    depart_token = _normalize_date_token(departure_date)
    return_token = _normalize_date_token(return_date)

    if not depart_token:
        return {
            "error": "Invalid or missing departure_date. Expected formats like YYYY-MM-DD or 17th May.",
        }

    if return_token:
        url = (
            f"https://www.skyscanner.co.in/transport/flights/{origin_code}/{destination_code}/{depart_token}/{return_token}/"
            "?adultsv2=1&cabinclass=economy&childrenv2=&ref=home&rtn=1"
            "&preferdirects=false&outboundaltsenabled=false&inboundaltsenabled=false"
        )
    else:
        url = (
            f"https://www.skyscanner.co.in/transport/flights/{origin_code}/{destination_code}/{depart_token}/"
            "?adultsv2=1&cabinclass=economy&childrenv2=&ref=home&rtn=0"
            "&preferdirects=false&outboundaltsenabled=false&inboundaltsenabled=false"
        )
    logger.warning("[flights] scraping_url=%s", url)

    results: List[Dict[str, str]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/115.0 Safari/537.36"
                )
            )
            await page.goto(url, timeout=30000)

            # Wait a short while for client-side rendering to populate prices.
            await page.wait_for_timeout(5000)

            anchors = await page.query_selector_all("a")
            for a in anchors:
                try:
                    txt = (await a.inner_text()).strip()
                except Exception:
                    txt = ""
                if not txt:
                    continue

                m = re.search(r"\$\s?\d[\d,]*", txt)
                if not m:
                    m = re.search(r"(USD|EUR|GBP|INR)\s?\d[\d,]*", txt)
                if m:
                    price = m.group(0)
                    title = (await a.get_attribute("aria-label")) or txt.splitlines()[0]
                    href = (await a.get_attribute("href")) or ""
                    link = ("https://www.skyscanner.com" + href) if href.startswith("/") else href
                    results.append(_format_result(title, price, link, ""))
                if len(results) >= max_results:
                    break

            await browser.close()
    except Exception as exc:
        logger.warning("[flights] scraping_failed error=%s", exc)
        return {"error": f"Playwright scraping failed: {exc}"}

    if not results:
        logger.warning("[flights] no_results_found")
        return {"error": "No flight results found via Skyscanner scraping."}

    logger.warning("[flights] results_found count=%s", len(results))
    return {"source": "skyscanner_playwright", "results": results}
