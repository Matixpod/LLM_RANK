"""Domain normalization, response parsing, and visibility classification."""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from .resolver import extract_domain_from_url, resolve_redirects

logger = logging.getLogger(__name__)

_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)

# Public-suffix fragments for the common multi-part TLDs we care about.
# Not exhaustive (no full PSL), but covers .co.uk / .com.au / .co.jp / .ac.uk etc.
_MULTIPART_TLD_HEADS = {"co", "com", "org", "net", "gov", "edu", "ac"}


def normalize_domain(domain: str) -> dict[str, Any]:
    """Parse a raw domain string into the variants used by all detection levels.

    Returns a dict:
      - full:     stripped hostname, lowercased ("neilpatel.com")
      - base:     brand token with the TLD removed ("neilpatel" from "neilpatel.com",
                  "bbc" from "bbc.co.uk")
      - variants: every form to test against URIs and text — domain, www-prefixed, base
    """
    s = (domain or "").strip().lower()
    s = _SCHEME_RE.sub("", s)
    s = _WWW_RE.sub("", s)
    s = s.split("/", 1)[0].rstrip(".")

    parts = s.split(".") if s else []
    if (
        len(parts) >= 3
        and parts[-2] in _MULTIPART_TLD_HEADS
        and len(parts[-1]) == 2  # country code like uk, au, jp
    ):
        base = parts[-3]
    elif len(parts) >= 2:
        base = parts[-2]
    else:
        base = s

    ordered: list[str] = []
    seen: set[str] = set()
    for v in (s, f"www.{s}" if s else "", base):
        if v and v not in seen:
            seen.add(v)
            ordered.append(v)

    return {"full": s, "base": base, "variants": ordered}


def _host_of(url: str) -> str:
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = (parsed.hostname or "").lower()
    except ValueError:
        return ""
    return _WWW_RE.sub("", host)


def url_matches_domain(url: str, domain: str) -> bool:
    """True if url's host equals domain or is a subdomain of it."""
    host = _host_of(url)
    if not host:
        return False
    return host == domain or host.endswith(f".{domain}")


def text_mentions_domain(text: str, domain: str) -> bool:
    """Loose check — domain substring appearing in response text."""
    if not text or not domain:
        return False
    t = text.lower()
    return domain in t or f"www.{domain}" in t


def classify_visibility(cited_urls: list[str], response_text: str, domain: str) -> str:
    """Return 'cited', 'mentioned', or 'not_present' for a single response."""
    full = normalize_domain(domain)["full"]
    if any(url_matches_domain(u, full) for u in cited_urls or []):
        return "cited"
    if text_mentions_domain(response_text or "", full):
        return "mentioned"
    return "not_present"


# ---------------------------------------------------------------------------
# Perplexity (OpenAI-compatible response) parser
# ---------------------------------------------------------------------------
def parse_perplexity(raw: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (response_text, cited_urls) from a Perplexity chat.completions JSON."""
    text = ""
    try:
        choices = raw.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
    except (AttributeError, IndexError, TypeError):
        text = ""

    urls: list[str] = []
    for u in raw.get("citations") or []:
        if isinstance(u, str):
            urls.append(u)
        elif isinstance(u, dict) and "url" in u:
            urls.append(u["url"])
    for r in raw.get("search_results") or []:
        if isinstance(r, dict) and r.get("url"):
            urls.append(r["url"])

    seen: set[str] = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return text, deduped


# ---------------------------------------------------------------------------
# Gemini grounding parser (legacy simple form — kept for existing pipeline code)
# ---------------------------------------------------------------------------
def parse_gemini(raw: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (response_text, cited_urls) from a Gemini response dict."""
    text_parts: list[str] = []
    urls: list[str] = []
    try:
        candidates = raw.get("candidates") or []
        if not candidates:
            return "", []
        cand = candidates[0]
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"] or "")

        gm = cand.get("groundingMetadata") or {}
        for chunk in gm.get("groundingChunks") or []:
            web = (chunk or {}).get("web") or {}
            uri = web.get("uri")
            if uri:
                urls.append(uri)
    except (AttributeError, TypeError):
        pass

    seen: set[str] = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return "".join(text_parts), deduped


# ---------------------------------------------------------------------------
# Gemini grounding parser — 4-level visibility detection
# ---------------------------------------------------------------------------
def _empty_result(
    response_text: str = "",
    cited_urls: list[str] | None = None,
    resolved_urls: list[str | None] | None = None,
    cited_titles: list[str] | None = None,
    chunks_count: int = 0,
    debug_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "visibility_status": "not_present",
        "cited_urls": cited_urls or [],
        "resolved_urls": resolved_urls or [],
        "cited_titles": cited_titles or [],
        "matched_level": None,
        "matched_on": None,
        "matched_url": None,
        "response_text": response_text,
        "grounding_chunks_count": chunks_count,
        "resolve_stats": {},
        "debug_info": debug_info or {},
    }


def _hit(
    status: str,
    level: int | None,
    matched_on: str | None,
    response_text: str,
    cited_urls: list[str],
    cited_titles: list[str],
    chunks_count: int,
    debug_info: dict[str, Any],
    resolved_urls: list[str | None] | None = None,
    matched_url: str | None = None,
    resolve_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if level is not None:
        logger.debug("gemini parser: matched_level=%s matched_on=%s", level, matched_on)
    return {
        "visibility_status": status,
        "cited_urls": cited_urls,
        "resolved_urls": resolved_urls or [],
        "cited_titles": cited_titles,
        "matched_level": level,
        "matched_on": matched_on,
        "matched_url": matched_url,
        "response_text": response_text,
        "grounding_chunks_count": chunks_count,
        "resolve_stats": resolve_stats or {},
        "debug_info": debug_info,
    }


async def parse_gemini_response(
    response_data: dict[str, Any],
    domain: str,
    brand_name: str | None = None,
) -> dict[str, Any]:
    """Five-level visibility detection for a Gemini grounding response.

    The levels — tested in priority order, first match wins — exist because
    Gemini's `groundingChunks[].web.uri` is a vertexaisearch redirect URL that
    never contains the source domain.

      0. Resolved URL — follow the redirect to get the real destination URL
                        and check if it matches the tracked domain.  This is
                        the highest-fidelity signal.
      1. URI substring  — rare direct hit when Gemini does include the domain.
      2. Chunk title    — the page title is always populated and usually
                          contains the brand or bare domain.
      3. Segment text   — `groundingSupports[].segment.text` are the exact
                          response fragments that Gemini attributed to a
                          source; a domain/brand here is a direct citation.
      4. Response text  — last-resort fallback classified as "mentioned"
                          (not "cited") since the model referenced the brand
                          without a grounded source chunk.
    """
    # --- response_text extraction -----------------------------------------
    try:
        candidates = response_data.get("candidates") or []
        if not candidates:
            return {
                **_empty_result(debug_info={"warning": "no candidates in response"}),
            }
        cand = candidates[0] or {}
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        response_text = "".join(
            (p.get("text") or "") for p in parts if isinstance(p, dict)
        )
    except (AttributeError, TypeError) as exc:
        return {
            "visibility_status": "error",
            "cited_urls": [],
            "resolved_urls": [],
            "cited_titles": [],
            "matched_level": None,
            "matched_on": None,
            "matched_url": None,
            "response_text": "",
            "grounding_chunks_count": 0,
            "resolve_stats": {},
            "debug_info": {"error": repr(exc)},
        }

    info = normalize_domain(domain)
    dom_full = info["full"]
    dom_variants = [v for v in info["variants"] if v]
    brand_re: re.Pattern[str] | None = None
    if brand_name:
        brand_re = re.compile(r"\b" + re.escape(brand_name) + r"\b", re.IGNORECASE)

    # --- grounding metadata extraction ------------------------------------
    gm = cand.get("groundingMetadata") or {}
    chunks = gm.get("groundingChunks") or []
    supports = gm.get("groundingSupports") or []

    cited_urls: list[str] = []
    cited_titles: list[str] = []
    for chunk in chunks:
        web = (chunk or {}).get("web") or {}
        uri = web.get("uri") or ""
        title = web.get("title") or ""
        if uri:
            cited_urls.append(uri)
        cited_titles.append(title)

    segment_texts: list[str] = []
    for sup in supports:
        seg = (sup or {}).get("segment") or {}
        t = seg.get("text") or ""
        if t:
            segment_texts.append(t)

    debug_info: dict[str, Any] = {
        "titles": cited_titles,
        "segment_texts": segment_texts,
    }
    if not gm:
        debug_info["warning"] = "groundingMetadata absent — grounding not triggered"

    chunks_count = len(chunks)

    def _domain_in(text: str) -> bool:
        low = text.lower()
        return any(v in low for v in dom_variants)

    def _brand_in(text: str) -> bool:
        return bool(brand_re and brand_re.search(text))

    def _resolved_domain_matches(resolved_url: str) -> bool:
        """Check if a resolved URL's domain matches the tracked domain.

        Handles subdomains: "blog.example.com" matches tracked "example.com".
        """
        host = extract_domain_from_url(resolved_url)
        if not host:
            return False
        return host == dom_full or host.endswith(f".{dom_full}")

    # --- Level 0: Resolve redirect URLs, match resolved targets -----------
    # This is the primary detection: follow the opaque vertexaisearch
    # redirect to discover the actual source URL, then domain-match it.
    resolved_urls: list[str | None] = []
    rstats: dict[str, Any] = {}
    if cited_urls:
        try:
            url_map, rstats = await resolve_redirects(cited_urls)
            resolved_urls = [url_map.get(u) for u in cited_urls]
        except Exception:
            logger.exception("resolve_redirects failed unexpectedly")
            url_map = {}
            resolved_urls = [None] * len(cited_urls)

        debug_info["resolved_urls"] = resolved_urls
        debug_info["resolve_stats"] = rstats

        for resolved in resolved_urls:
            if resolved and _resolved_domain_matches(resolved):
                return _hit(
                    "cited", 0, "resolved_url",
                    response_text, cited_urls, cited_titles, chunks_count, debug_info,
                    resolved_urls=resolved_urls, matched_url=resolved,
                    resolve_stats=rstats,
                )

    # --- Level 1: URI direct match (rare; Gemini mostly returns redirects) ---
    for uri in cited_urls:
        if _domain_in(uri):
            return _hit(
                "cited", 1, "uri",
                response_text, cited_urls, cited_titles, chunks_count, debug_info,
                resolved_urls=resolved_urls, resolve_stats=rstats,
            )

    # --- Level 2: Title match on grounding chunks -------------------------
    for title in cited_titles:
        if not title:
            continue
        if _domain_in(title) or _brand_in(title):
            return _hit(
                "cited", 2, "title",
                response_text, cited_urls, cited_titles, chunks_count, debug_info,
                resolved_urls=resolved_urls, resolve_stats=rstats,
            )

    # --- Level 3: groundingSupports segment text --------------------------
    for seg_text in segment_texts:
        if _domain_in(seg_text) or _brand_in(seg_text):
            return _hit(
                "cited", 3, "segment",
                response_text, cited_urls, cited_titles, chunks_count, debug_info,
                resolved_urls=resolved_urls, resolve_stats=rstats,
            )

    # --- Level 4: plain response text fallback ("mentioned") --------------
    if response_text and (_domain_in(response_text) or _brand_in(response_text)):
        return _hit(
            "mentioned", 4, "response_text",
            response_text, cited_urls, cited_titles, chunks_count, debug_info,
            resolved_urls=resolved_urls, resolve_stats=rstats,
        )

    return _hit(
        "not_present", None, None,
        response_text, cited_urls, cited_titles, chunks_count, debug_info,
        resolved_urls=resolved_urls, resolve_stats=rstats,
    )
