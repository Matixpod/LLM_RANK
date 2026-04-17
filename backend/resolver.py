"""Async redirect resolver for Gemini grounding URLs.

Gemini's grounding API returns opaque redirect URLs of the form:
  https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFm...

These are signed tokens — the original source domain is not encoded in the
URL string and cannot be extracted without following the redirect.  This
module resolves batches of such URLs concurrently using aiohttp HEAD requests,
returning the final destination URLs for domain matching.

The module is intentionally self-contained with no LLM-RANK imports so it
can be tested and reused independently.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache — persists per-process, resets on restart.
# Prevents re-resolving the same redirect URL across questions in a scan.
# ---------------------------------------------------------------------------
_cache: dict[str, str | None] = {}

_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)


def clear_cache() -> None:
    """Reset the redirect cache (for testing)."""
    _cache.clear()


def extract_domain_from_url(url: str | None) -> str | None:
    """Extract the bare domain from a URL, stripping www. prefix.

    Returns None for None input or malformed URLs.

    Examples:
        "https://www.neilpatel.com/blog/" → "neilpatel.com"
        "https://blog.example.co.uk/page" → "blog.example.co.uk"
        None → None
    """
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        return _WWW_RE.sub("", host)
    except (ValueError, AttributeError):
        return None


async def _resolve_one(
    url: str,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str | None]:
    """Resolve a single redirect URL. Returns (original_url, resolved_url | None).

    Never raises — all exceptions are caught and logged.
    """
    # Check cache first
    if url in _cache:
        logger.debug("resolver cache hit: %s → %s", url, _cache[url])
        return url, _cache[url]

    async with semaphore:
        try:
            # HEAD is faster (no body download)
            async with session.head(url, allow_redirects=True) as resp:
                resolved = str(resp.url)
                _cache[url] = resolved
                logger.debug("resolved: %s → %s", url, resolved)
                return url, resolved
        except aiohttp.ClientResponseError as exc:
            if exc.status == 405:
                # Server rejected HEAD — retry with GET
                try:
                    async with session.get(url, allow_redirects=True) as resp:
                        resolved = str(resp.url)
                        _cache[url] = resolved
                        logger.debug("resolved (GET fallback): %s → %s", url, resolved)
                        return url, resolved
                except Exception as get_exc:
                    logger.warning("resolver GET fallback failed for %s: %s: %s",
                                   url, type(get_exc).__name__, get_exc)
                    _cache[url] = None
                    return url, None
        except Exception as exc:
            logger.warning("resolver failed for %s: %s: %s",
                           url, type(exc).__name__, exc)
            _cache[url] = None
            return url, None


async def resolve_redirects(
    urls: list[str],
    timeout_seconds: float = 5.0,
    max_concurrent: int = 10,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Resolve a batch of redirect URLs concurrently.

    Args:
        urls: list of opaque redirect URLs from Gemini groundingChunks
        timeout_seconds: per-request timeout
        max_concurrent: max simultaneous connections

    Returns:
        (url_mapping, stats) where:
          - url_mapping: {original_url: resolved_url_or_None}
          - stats: {total, resolved, failed, cached, duration_ms}

    Never raises — all exceptions are caught internally.
    """
    empty_stats: dict[str, Any] = {
        "total": len(urls),
        "resolved": 0,
        "failed": len(urls),
        "cached": 0,
        "duration_ms": 0.0,
    }

    if not urls:
        empty_stats["total"] = 0
        empty_stats["failed"] = 0
        return {}, empty_stats

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    # Count how many are already cached (before we start timing network)
    cached_count = sum(1 for u in unique if u in _cache)

    semaphore = asyncio.Semaphore(max_concurrent)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    connector = aiohttp.TCPConnector(limit=max_concurrent)

    t0 = time.monotonic()
    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
        ) as session:
            results = await asyncio.gather(
                *[_resolve_one(u, session, semaphore) for u in unique]
            )
    except Exception as exc:
        # Session creation or gather itself failed catastrophically
        logger.warning("resolve_redirects session failed: %s: %s",
                       type(exc).__name__, exc)
        return {}, empty_stats

    duration_ms = (time.monotonic() - t0) * 1000

    url_map: dict[str, str | None] = {}
    resolved_count = 0
    failed_count = 0

    for orig, resolved in results:
        url_map[orig] = resolved
        if resolved is not None:
            resolved_count += 1
        else:
            failed_count += 1

    stats: dict[str, Any] = {
        "total": len(unique),
        "resolved": resolved_count,
        "failed": failed_count,
        "cached": cached_count,
        "duration_ms": round(duration_ms, 1),
    }

    logger.info(
        "resolve_redirects: %d URLs — %d resolved, %d failed, %d cached, %.0fms",
        stats["total"], stats["resolved"], stats["failed"],
        stats["cached"], stats["duration_ms"],
    )

    return url_map, stats
