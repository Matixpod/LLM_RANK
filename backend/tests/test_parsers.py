"""Tests for parse_gemini_response — runnable with pytest (requires pytest-asyncio)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.parsers import normalize_domain, parse_gemini_response


def _wrap(response_text: str, chunks=None, supports=None) -> dict:
    gm: dict = {}
    if chunks is not None:
        gm["groundingChunks"] = chunks
    if supports is not None:
        gm["groundingSupports"] = supports
    candidate: dict = {
        "content": {"parts": [{"text": response_text}]},
    }
    if gm:
        candidate["groundingMetadata"] = gm
    return {"candidates": [candidate]}


_NOOP_RESOLVE_STATS = {"total": 0, "resolved": 0, "failed": 0, "cached": 0, "duration_ms": 0}


@pytest.fixture(autouse=True)
def _mock_resolver():
    """Prevent real HTTP calls from the redirect resolver in all parser tests.

    Returns an empty mapping so Level 0 never matches, letting Levels 1–4
    be tested in isolation.  Individual tests can override this.
    """
    with patch(
        "backend.parsers.resolve_redirects",
        new_callable=AsyncMock,
        return_value=({}, _NOOP_RESOLVE_STATS),
    ):
        yield


# ---------------------------------------------------------------------------
# normalize_domain (sync — no mock needed)
# ---------------------------------------------------------------------------
def test_normalize_domain_multipart_tld():
    info = normalize_domain("bbc.co.uk")
    assert info["full"] == "bbc.co.uk"
    assert info["base"] == "bbc"
    assert "bbc.co.uk" in info["variants"]


def test_normalize_domain_simple():
    info = normalize_domain("https://www.NeilPatel.com/blog")
    assert info["full"] == "neilpatel.com"
    assert info["base"] == "neilpatel"
    assert set(info["variants"]) == {"neilpatel.com", "www.neilpatel.com", "neilpatel"}


# ---------------------------------------------------------------------------
# Level 0 — resolved redirect URL matches domain
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parse_gemini_response_level0_resolved_url():
    """Resolver returns a URL whose domain matches — must be 'cited' at level 0."""
    redirect_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz"
    resolved_url = "https://neilpatel.com/blog/seo-guide/"
    resolve_result = (
        {redirect_url: resolved_url},
        {"total": 1, "resolved": 1, "failed": 0, "cached": 0, "duration_ms": 42},
    )
    with patch(
        "backend.parsers.resolve_redirects",
        new_callable=AsyncMock,
        return_value=resolve_result,
    ):
        raw = _wrap(
            response_text="SEO starts with keyword research.",
            chunks=[{"web": {
                "uri": redirect_url,
                "title": "Unrelated Title",
            }}],
        )
        out = await parse_gemini_response(raw, domain="neilpatel.com")
    assert out["visibility_status"] == "cited"
    assert out["matched_level"] == 0
    assert out["matched_on"] == "resolved_url"
    assert out["matched_url"] == resolved_url
    assert out["resolved_urls"] == [resolved_url]
    assert out["resolve_stats"]["resolved"] == 1


@pytest.mark.asyncio
async def test_parse_gemini_response_level0_subdomain():
    """Resolved URL on a subdomain (blog.example.com) matches root domain."""
    redirect_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/sub"
    resolved_url = "https://blog.neilpatel.com/some-post/"
    resolve_result = (
        {redirect_url: resolved_url},
        {"total": 1, "resolved": 1, "failed": 0, "cached": 0, "duration_ms": 30},
    )
    with patch(
        "backend.parsers.resolve_redirects",
        new_callable=AsyncMock,
        return_value=resolve_result,
    ):
        raw = _wrap(
            response_text="Some unrelated text.",
            chunks=[{"web": {"uri": redirect_url, "title": "Unrelated"}}],
        )
        out = await parse_gemini_response(raw, domain="neilpatel.com")
    assert out["visibility_status"] == "cited"
    assert out["matched_level"] == 0


# ---------------------------------------------------------------------------
# Level 2 — title match (existing, now async)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parse_gemini_response_level2_title():
    """Domain appears only in a groundingChunk title — 'cited' at level 2."""
    raw = _wrap(
        response_text="SEO starts with keyword research and on-page basics.",
        chunks=[
            {"web": {
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz",
                "title": "Neil Patel | Digital Marketing Blog",
            }}
        ],
        supports=[
            {"segment": {"text": "keyword research is the foundation"}, "groundingChunkIndices": [0]}
        ],
    )
    out = await parse_gemini_response(raw, domain="neilpatel.com", brand_name="Neil Patel")
    assert out["visibility_status"] == "cited"
    assert out["matched_level"] == 2
    assert out["matched_on"] == "title"
    assert out["grounding_chunks_count"] == 1


# ---------------------------------------------------------------------------
# Level 3 — segment text match
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parse_gemini_response_level3_segment():
    """Domain appears only inside a grounding segment text — level 3 'cited'."""
    raw = _wrap(
        response_text="There are many SEO tools on the market today.",
        chunks=[
            {"web": {
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/aaa",
                "title": "Top 10 SEO Tools Compared",
            }}
        ],
        supports=[
            {"segment": {"text": "Ahrefs and similar tools from neilpatel.com dominate the list."},
             "groundingChunkIndices": [0]}
        ],
    )
    out = await parse_gemini_response(raw, domain="neilpatel.com", brand_name=None)
    assert out["visibility_status"] == "cited"
    assert out["matched_level"] == 3
    assert out["matched_on"] == "segment"


# ---------------------------------------------------------------------------
# Level 4 — response text
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parse_gemini_response_level4_response_text():
    """Domain appears only in the plain response text — level 4 'mentioned'."""
    raw = _wrap(
        response_text="For deeper SEO reading, check neilpatel.com guides.",
        chunks=[
            {"web": {
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/bbb",
                "title": "Unrelated SEO Overview",
            }}
        ],
        supports=[{"segment": {"text": "SEO overview is broad."}, "groundingChunkIndices": [0]}],
    )
    out = await parse_gemini_response(raw, domain="neilpatel.com", brand_name="Neil Patel")
    assert out["visibility_status"] == "mentioned"
    assert out["matched_level"] == 4
    assert out["matched_on"] == "response_text"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parse_gemini_response_no_grounding():
    """No groundingMetadata at all — not_present plus a debug warning."""
    raw = {"candidates": [{"content": {"parts": [{"text": "Hello world."}]}}]}
    out = await parse_gemini_response(raw, domain="neilpatel.com", brand_name="Neil Patel")
    assert out["visibility_status"] == "not_present"
    assert out["matched_level"] is None
    assert out["grounding_chunks_count"] == 0
    assert "warning" in out["debug_info"]


@pytest.mark.asyncio
async def test_parse_gemini_response_brand_word_boundary():
    """brand_name word boundary: 'Brand' must not match 'Branded' in text."""
    raw = _wrap(
        response_text="Branded solutions are popular in the SMB market.",
        chunks=[],
        supports=[],
    )
    out = await parse_gemini_response(raw, domain="example-xyz.test", brand_name="Brand")
    assert out["visibility_status"] == "not_present"


@pytest.mark.asyncio
async def test_parse_gemini_response_malformed():
    """Missing candidates list — classified as not_present with warning."""
    out = await parse_gemini_response({}, domain="neilpatel.com", brand_name=None)
    assert out["visibility_status"] == "not_present"
    assert "warning" in out["debug_info"]


@pytest.mark.asyncio
async def test_parse_gemini_response_resolver_failure_falls_through():
    """If resolver raises, parser falls through to Levels 1–4 gracefully."""
    with patch(
        "backend.parsers.resolve_redirects",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network down"),
    ):
        raw = _wrap(
            response_text="Check neilpatel.com for tips.",
            chunks=[{"web": {
                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/fail",
                "title": "Unrelated",
            }}],
        )
        out = await parse_gemini_response(raw, domain="neilpatel.com")
    # Resolver failed, but Level 4 should still catch the domain in response text
    assert out["visibility_status"] == "mentioned"
    assert out["matched_level"] == 4


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _main():
        await test_parse_gemini_response_level0_resolved_url()
        await test_parse_gemini_response_level0_subdomain()
        await test_parse_gemini_response_level2_title()
        await test_parse_gemini_response_level3_segment()
        await test_parse_gemini_response_level4_response_text()
        await test_parse_gemini_response_no_grounding()
        await test_parse_gemini_response_brand_word_boundary()
        await test_parse_gemini_response_malformed()
        await test_parse_gemini_response_resolver_failure_falls_through()

    test_normalize_domain_multipart_tld()
    test_normalize_domain_simple()
    asyncio.run(_main())
    print("ok — all parser tests passed")
