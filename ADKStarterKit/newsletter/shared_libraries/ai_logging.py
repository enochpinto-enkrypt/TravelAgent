"""Lightweight AI call logging utilities.

Provides structured logging for AI interactions: model, prompt/context,
approximate token counts, response usage (if available), duration, and
extra parameters. Writes JSON lines to a file so it can be consumed by
log collectors.
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional


LOG_PATH = os.getenv("AI_LOG_PATH") or os.path.join(os.getcwd(), "ai_calls.log")


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("ai_logger")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        formatter = logging.Formatter("%(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger


_LOGGER = _setup_logger()


def approx_token_count(text: Optional[str]) -> int:
    """Return a rough token estimate for a text string.

    This is intentionally conservative and lightweight: tokenizers may vary,
    so we use the word count as a baseline.
    """
    if not text:
        return 0
    words = len(text.split())
    # approximate: 1 word -> ~1.3 tokens on average (depends on tokenizer)
    return max(1, int(words * 1.3))


def _short_preview(text: Optional[str], limit: int = 1000) -> Optional[str]:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + "..."


def log_ai_call(
    event: str,
    model: Optional[str] = None,
    prompt: Optional[str] = None,
    response: Optional[Dict[str, Any]] = None,
    start_time: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a single AI-related event as JSON.

    Args:
        event: Short event name (e.g., 'completion', 'tool_call').
        model: Model identifier when applicable.
        prompt: The prompt or context sent to the model.
        response: The response object/dict returned by the call (if any).
        start_time: If provided, will be used to compute duration (time.time()).
        extra: Any additional data to include.
    """
    ts = time.time()
    duration = None
    if start_time is not None:
        duration = max(0.0, ts - start_time)

    usage = None
    if isinstance(response, dict):
        # Common AI response usage locations (OpenAI-like / Google-like)
        usage = response.get("usage") or response.get("meta") or response.get("_usage")

    payload = {
        "timestamp": ts,
        "event": event,
        "model": model,
        "prompt_preview": _short_preview(prompt),
        "prompt_char_length": len(prompt) if prompt is not None else 0,
        "prompt_word_count": len(prompt.split()) if prompt else 0,
        "approx_prompt_tokens": approx_token_count(prompt),
        "response_keys": list(response.keys()) if isinstance(response, dict) else None,
        "response_usage": usage,
        "duration_seconds": duration,
        "extra": extra,
    }

    # Write a single JSON line
    try:
        _LOGGER.info(json.dumps(payload, default=str))
    except Exception:
        # Best-effort: fallback to plain logging
        logging.getLogger("ai_logger_fallback").info(str(payload))


def log_decorator(event: str = "ai_call", model: Optional[str] = None, extra_base: Optional[Dict[str, Any]] = None):
    """Decorator to wrap functions that perform AI/tool calls.

    The wrapped function should accept a `prompt` or `query` parameter or
    return a dict-like response. This decorator logs before/after with duration
    and usage details (if present in the returned dict).
    """

    def _decorator(fn):
        def _wrapped(*args, **kwargs):
            start = time.time()
            prompt = kwargs.get("prompt") or kwargs.get("query") or None
            log_ai_call(event + ".start", model=model, prompt=prompt, start_time=None, extra=extra_base)
            try:
                result = fn(*args, **kwargs)
            except Exception as e:  # still log the failure
                log_ai_call(
                    event + ".error",
                    model=model,
                    prompt=prompt,
                    response={"error": str(e)},
                    start_time=start,
                    extra=extra_base,
                )
                raise
            log_ai_call(event + ".end", model=model, prompt=prompt, response=(result if isinstance(result, dict) else None), start_time=start, extra=extra_base)
            return result

        return _wrapped

    return _decorator
