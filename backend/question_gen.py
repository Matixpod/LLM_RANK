"""Generate conversational industry questions via Gemini, with Claude + static fallbacks."""
from __future__ import annotations

import asyncio
import json
import logging
import re

import aiohttp

from .config import settings

logger = logging.getLogger(__name__)

class QuestionGenerationError(RuntimeError):
    """Raised when no generator could produce valid questions."""


def _extract_questions(text: str) -> list[str]:
    """Pull a list of questions out of LLM text output — prefers a JSON array."""
    text = text.strip()
    # Strip ```json fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()

    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [str(q).strip() for q in data if str(q).strip()]
        except json.JSONDecodeError:
            pass

    # Fallback: line-by-line, stripping numbering / bullets
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^[\-\*\d\.\)]+\s*", "", s)
        s = s.strip('"').strip("'").strip()
        if s.endswith("?") or len(s) > 20:
            lines.append(s)
    return lines


def _build_prompt(
    industry: str,
    language: str,
    count: int,
    domain: str | None,
    avoid: list[str] | None = None,
) -> str:
    business_hint = f" at {domain}" if domain else ""
    avoid_block = ""
    if avoid:
        sample = "\n".join(f"- {q}" for q in avoid[:40])
        avoid_block = (
            f"\nThe following questions have already been generated — do NOT "
            f"repeat them or produce near-duplicates. Generate fresh angles:\n"
            f"{sample}\n"
        )
    return (
        f"You are a potential customer of a business{business_hint} that offers: "
        f"{industry}.\n"
        f"Generate {count} questions you would type into Google Search (or ask "
        f"an AI assistant) if you were genuinely interested in using its services.\n"
        f"\n"
        f"Rules:\n"
        f"- Write every question in {language}. Do not mix languages.\n"
        f"- Write like a real person searching — short, natural, specific. "
        f"Do not paste the business description into the question.\n"
        f"- Each question ends with a question mark.\n"
        f"{avoid_block}"
        f"\n"
        f"Return ONLY a JSON array of exactly {count} strings."
    )


GEMINI_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


async def _generate_via_gemini(
    industry: str, count: int, language: str, domain: str | None, avoid: list[str] | None
) -> list[str]:
    """Ask Gemini for localized, business-relevant questions. Raises on failure.

    Retries transient 429/5xx responses with exponential backoff — Gemini
    occasionally returns 503 on demand spikes.
    """
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.google_api_key}"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _build_prompt(industry, language, count, domain, avoid)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.9,
            "responseMimeType": "application/json",
        },
    }

    max_attempts = 4
    data: dict = {}
    last_error: str | None = None
    async with aiohttp.ClientSession() as http:
        for attempt in range(max_attempts):
            try:
                async with http.post(url, json=payload, timeout=90) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        if resp.status in GEMINI_RETRYABLE_STATUSES and attempt < max_attempts - 1:
                            delay = 1.5 * (2 ** attempt)
                            logger.info(
                                "Gemini HTTP %s — retrying in %.1fs (attempt %d/%d)",
                                resp.status, delay, attempt + 1, max_attempts,
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise RuntimeError(f"Gemini HTTP {resp.status}: {data}")
                    break
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    delay = 1.5 * (2 ** attempt)
                    logger.info(
                        "Gemini transport error (%s) — retrying in %.1fs (attempt %d/%d)",
                        exc, delay, attempt + 1, max_attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise RuntimeError(f"Gemini transport error: {last_error}") from exc

    text_parts: list[str] = []
    for cand in data.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            t = part.get("text")
            if t:
                text_parts.append(t)
    questions = _extract_questions("\n".join(text_parts))
    if len(questions) < 3:
        raise RuntimeError(f"Gemini returned too few questions ({len(questions)})")
    return questions[:count]


async def _generate_via_claude(
    industry: str, count: int, language: str, domain: str | None, avoid: list[str] | None
) -> list[str]:
    """Ask Claude for localized questions. Raises on failure."""
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    msg = await client.messages.create(
        model=settings.claude_model,
        max_tokens=2048,
        messages=[
            {"role": "user", "content": _build_prompt(industry, language, count, domain, avoid)}
        ],
    )
    text_blocks = [getattr(b, "text", "") or "" for b in (msg.content or [])]
    questions = _extract_questions("\n".join(text_blocks))
    if len(questions) < 3:
        raise RuntimeError(f"Claude returned too few questions ({len(questions)})")
    return questions[:count]


async def generate_questions(
    industry: str,
    count: int = 10,
    language: str = "English",
    domain: str | None = None,
    avoid: list[str] | None = None,
) -> list[str]:
    """Generate `count` customer-voiced questions. Gemini → Claude → raise.

    `avoid` is a list of already-existing question texts the model should not
    duplicate, used when generating additional questions for an existing domain.
    """
    try:
        logger.info(
            "Generating %d questions via Gemini (industry=%r, language=%s, avoid=%d)",
            count, industry, language, len(avoid or []),
        )
        return await _generate_via_gemini(industry, count, language, domain, avoid)
    except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        logger.warning("Gemini question generation failed: %s", exc)

    if settings.anthropic_api_key:
        try:
            logger.info("Falling back to Claude for question generation")
            return await _generate_via_claude(industry, count, language, domain, avoid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Claude question generation failed: %s", exc)

    raise QuestionGenerationError(
        "Question generation failed on all configured providers. "
        "Check GOOGLE_API_KEY (and ANTHROPIC_API_KEY if set) and the server logs."
    )


def estimate_tokens(text: str) -> int:
    """Very rough token estimator (~4 chars/token)."""
    return max(1, len(text) // 4)


def estimated_cost_perplexity(input_text: str, output_text: str, search_requests: int) -> float:
    """Approximate USD cost for a Perplexity sonar-pro call."""
    in_tok = estimate_tokens(input_text)
    out_tok = estimate_tokens(output_text)
    return (in_tok / 1_000_000) + (out_tok / 1_000_000) + (search_requests * 0.005)


def estimated_cost_gemini(input_text: str, output_text: str) -> float:
    """Approximate USD cost for a Gemini flash call at ~$0.10 per 1M tokens."""
    tok = estimate_tokens(input_text) + estimate_tokens(output_text)
    return (tok / 1_000_000) * 0.10
