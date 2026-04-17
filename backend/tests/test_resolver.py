"""Tests for backend.resolver — redirect resolution and domain extraction."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

from backend.resolver import clear_cache, extract_domain_from_url, resolve_redirects


# ---------------------------------------------------------------------------
# extract_domain_from_url
# ---------------------------------------------------------------------------
class TestExtractDomain:
    def test_standard_url(self):
        assert extract_domain_from_url("https://www.neilpatel.com/blog/post/") == "neilpatel.com"

    def test_subdomain_preserved(self):
        assert extract_domain_from_url("https://blog.example.co.uk/page") == "blog.example.co.uk"

    def test_none_input(self):
        assert extract_domain_from_url(None) is None

    def test_empty_string(self):
        assert extract_domain_from_url("") is None

    def test_malformed(self):
        assert extract_domain_from_url("not-a-url") is not None or extract_domain_from_url("://") is None

    def test_no_www(self):
        assert extract_domain_from_url("https://neilpatel.com") == "neilpatel.com"

    def test_http(self):
        assert extract_domain_from_url("http://example.com/page") == "example.com"


# ---------------------------------------------------------------------------
# resolve_redirects
# ---------------------------------------------------------------------------
def _make_mock_session(url_map: dict[str, str], fail_urls: set[str] | None = None):
    """Build a mock aiohttp.ClientSession that simulates redirect resolution.

    url_map: {original_url: final_resolved_url}
    fail_urls: set of URLs that should raise asyncio.TimeoutError
    """
    fail_urls = fail_urls or set()

    async def _head(url, allow_redirects=True):
        if url in fail_urls:
            raise asyncio.TimeoutError()
        resolved = url_map.get(url, url)
        resp = MagicMock()
        resp.url = urlparse(resolved)._replace(scheme="https")
        # Make resp.url return the resolved string via str()
        resp.url = MagicMock()
        resp.url.__str__ = lambda self: resolved
        return resp

    ctx_manager = MagicMock()
    ctx_manager.__aenter__ = AsyncMock(side_effect=lambda: ctx_manager)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    def head_side_effect(url, **kwargs):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(side_effect=lambda: asyncio.ensure_future(_head_resolve(url)))
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    # Simpler approach: patch _resolve_one behavior via session.head as async ctx manager
    class FakeResponse:
        def __init__(self, resolved_url):
            self.url = resolved_url

    class FakeCtx:
        def __init__(self, url):
            self._url = url

        async def __aenter__(self):
            if self._url in fail_urls:
                raise asyncio.TimeoutError()
            resolved = url_map.get(self._url, self._url)
            return FakeResponse(resolved)

        async def __aexit__(self, *args):
            pass

    session.head = lambda url, **kw: FakeCtx(url)
    return session


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    """Ensure each test starts with a clean cache."""
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_resolve_redirects_success():
    """Successful resolution returns the final URL and correct stats."""
    url_map = {
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc": "https://neilpatel.com/blog/seo/",
    }
    mock_session = _make_mock_session(url_map)

    with patch("backend.resolver.aiohttp.ClientSession", return_value=mock_session):
        with patch("backend.resolver.aiohttp.TCPConnector"):
            with patch("backend.resolver.aiohttp.ClientTimeout"):
                mapping, stats = await resolve_redirects(list(url_map.keys()))

    orig = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    assert mapping[orig] == "https://neilpatel.com/blog/seo/"
    assert stats["resolved"] == 1
    assert stats["failed"] == 0

    domain = extract_domain_from_url(mapping[orig])
    assert domain == "neilpatel.com"


@pytest.mark.asyncio
async def test_resolve_redirects_timeout():
    """Timeout on one URL returns None for it; others still resolve."""
    good_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/good"
    bad_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/bad"
    url_map = {good_url: "https://example.com/page"}
    mock_session = _make_mock_session(url_map, fail_urls={bad_url})

    with patch("backend.resolver.aiohttp.ClientSession", return_value=mock_session):
        with patch("backend.resolver.aiohttp.TCPConnector"):
            with patch("backend.resolver.aiohttp.ClientTimeout"):
                mapping, stats = await resolve_redirects([good_url, bad_url])

    assert mapping[good_url] == "https://example.com/page"
    assert mapping[bad_url] is None
    assert stats["resolved"] == 1
    assert stats["failed"] == 1


@pytest.mark.asyncio
async def test_resolve_redirects_cache():
    """Second call with same URL uses cache — no new HTTP request."""
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/cached"
    url_map = {url: "https://cached-target.com/"}
    mock_session = _make_mock_session(url_map)

    with patch("backend.resolver.aiohttp.ClientSession", return_value=mock_session) as mock_cls:
        with patch("backend.resolver.aiohttp.TCPConnector"):
            with patch("backend.resolver.aiohttp.ClientTimeout"):
                # First call — should make HTTP request
                mapping1, stats1 = await resolve_redirects([url])
                assert mapping1[url] == "https://cached-target.com/"
                assert stats1["cached"] == 0

                # Second call — should hit cache
                mapping2, stats2 = await resolve_redirects([url])
                assert mapping2[url] == "https://cached-target.com/"
                assert stats2["cached"] == 1


@pytest.mark.asyncio
async def test_resolve_redirects_empty():
    """Empty URL list returns empty mapping and zero stats."""
    mapping, stats = await resolve_redirects([])
    assert mapping == {}
    assert stats["total"] == 0
    assert stats["failed"] == 0


@pytest.mark.asyncio
async def test_resolve_redirects_deduplicates():
    """Duplicate URLs are resolved only once."""
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/dup"
    url_map = {url: "https://target.com/"}
    mock_session = _make_mock_session(url_map)

    with patch("backend.resolver.aiohttp.ClientSession", return_value=mock_session):
        with patch("backend.resolver.aiohttp.TCPConnector"):
            with patch("backend.resolver.aiohttp.ClientTimeout"):
                mapping, stats = await resolve_redirects([url, url, url])

    assert mapping[url] == "https://target.com/"
    assert stats["total"] == 1  # only 1 unique URL
