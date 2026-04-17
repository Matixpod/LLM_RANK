"""The scan pipeline — fan out each question to Perplexity + Gemini in parallel."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import Domain, Question, Result, Scan, SessionLocal
from .parsers import (
    classify_visibility,
    normalize_domain,
    parse_gemini_response,
    parse_perplexity,
)
from .question_gen import (
    estimated_cost_gemini,
    estimated_cost_perplexity,
    generate_questions,
)
from .scoring import per_model_score, score_from_statuses

logger = logging.getLogger(__name__)

MODEL_PERPLEXITY = "perplexity"
MODEL_GEMINI = "gemini"

# In-memory progress tracker: scan_id -> {"progress": n, "total": m}
SCAN_PROGRESS: dict[int, dict[str, int]] = {}


# ---------------------------------------------------------------------------
# External calls
# ---------------------------------------------------------------------------
async def call_perplexity(
    session: aiohttp.ClientSession, question: str
) -> dict[str, Any]:
    """Call Perplexity's chat.completions endpoint. Returns the raw JSON or {'error': ...}."""
    if not settings.perplexity_api_key:
        return {"error": "PERPLEXITY_API_KEY not set"}

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.perplexity_model,
        "messages": [{"role": "user", "content": question}],
    }
    try:
        async with session.post(url, json=payload, headers=headers, timeout=90) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                return {"error": f"HTTP {resp.status}", "body": data}
            return data
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
        logger.exception("Perplexity call failed: %s", exc)
        return {"error": str(exc)}


async def call_gemini(
    session: aiohttp.ClientSession, question: str
) -> dict[str, Any]:
    """Call Gemini generateContent with the Google Search grounding tool enabled."""
    if not settings.google_api_key:
        return {"error": "GOOGLE_API_KEY not set"}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.google_api_key}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        # Google Search grounding for gemini-2.0-flash
        "tools": [{"google_search": {}}],
    }
    headers = {"Content-Type": "application/json"}
    try:
        async with session.post(url, json=payload, headers=headers, timeout=90) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                return {"error": f"HTTP {resp.status}", "body": data}
            return data
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
        logger.exception("Gemini call failed: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Per-question execution
# ---------------------------------------------------------------------------
async def _row_from(model: str, question_id: int, raw: dict[str, Any], domain_str: str) -> dict[str, Any]:
    """Convert one model's raw response into a result row."""
    if "error" in raw:
        return {
            "question_id": question_id,
            "model": model,
            "visibility_status": "error",
            "raw_response": raw,
            "cited_urls": [],
            "response_text": "",
        }

    if model == MODEL_GEMINI:
        # 5-level parser: resolves redirect URLs, then checks titles,
        # grounding segments, and response text.
        parsed = await parse_gemini_response(raw, domain_str)
        return {
            "question_id": question_id,
            "model": model,
            "visibility_status": parsed["visibility_status"],
            "raw_response": raw,
            "cited_urls": parsed["cited_urls"],
            "response_text": parsed["response_text"],
        }

    # Perplexity (and any future models): standard URI-host + text check.
    text, urls = parse_perplexity(raw)
    return {
        "question_id": question_id,
        "model": model,
        "visibility_status": classify_visibility(urls, text, domain_str),
        "raw_response": raw,
        "cited_urls": urls,
        "response_text": text,
    }


async def _run_one(
    session: aiohttp.ClientSession,
    question: Question,
    domain_str: str,
    enabled: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Run one question against enabled models in parallel."""
    tasks: list[Any] = []
    order: list[str] = []
    if MODEL_PERPLEXITY in enabled:
        tasks.append(call_perplexity(session, question.text))
        order.append(MODEL_PERPLEXITY)
    if MODEL_GEMINI in enabled:
        tasks.append(call_gemini(session, question.text))
        order.append(MODEL_GEMINI)

    raws = await asyncio.gather(*tasks) if tasks else []
    return list(await asyncio.gather(*[
        _row_from(m, question.id, r, domain_str) for m, r in zip(order, raws)
    ]))


# ---------------------------------------------------------------------------
# Question bootstrapping
# ---------------------------------------------------------------------------
async def ensure_questions(
    db: AsyncSession, domain: Domain, force_regenerate: bool = False
) -> list[Question]:
    """Return active questions for a domain, generating them on first use.

    Also regenerates when the domain's language no longer matches the language
    the existing questions were written in — otherwise a Polish domain would
    keep being scanned with old English questions.
    """
    result = await db.execute(
        select(Question).where(Question.domain_id == domain.id, Question.is_active == True)  # noqa: E712
    )
    existing = list(result.scalars().all())

    language_drift = bool(existing) and any(
        (q.language or "English") != domain.language for q in existing
    )
    should_regenerate = force_regenerate or language_drift

    if existing and not should_regenerate:
        return existing

    if should_regenerate and existing:
        if language_drift:
            logger.info(
                "Language drift for '%s' (domain=%s, questions=%s) — regenerating",
                domain.domain,
                domain.language,
                sorted({q.language or "English" for q in existing}),
            )
        for q in existing:
            q.is_active = False
        await db.flush()

    logger.info(
        "Generating questions for '%s' (industry=%s, language=%s)",
        domain.domain, domain.industry, domain.language,
    )
    texts = await generate_questions(
        domain.industry, count=10, language=domain.language, domain=domain.domain
    )
    new_questions = [
        Question(
            domain_id=domain.id,
            text=t,
            language=domain.language,
            is_active=True,
        )
        for t in texts
    ]
    db.add_all(new_questions)
    await db.flush()
    await db.commit()
    for q in new_questions:
        await db.refresh(q)
    return new_questions


# ---------------------------------------------------------------------------
# Scan orchestration
# ---------------------------------------------------------------------------
async def run_scan(
    domain_id: int,
    force_regenerate: bool = False,
    scan_id: int | None = None,
) -> int:
    """Run a full scan for a domain. Creates or updates a Scan row. Returns scan_id.

    If `scan_id` is provided, reuse that pre-created scan (so the caller can
    return it to the client immediately for polling).
    """
    async with SessionLocal() as db:
        domain = await db.get(Domain, domain_id)
        if domain is None:
            raise ValueError(f"Domain id={domain_id} not found")

        questions = await ensure_questions(db, domain, force_regenerate=force_regenerate)
        if not questions:
            raise RuntimeError("No questions available for this domain")

        if scan_id is None:
            scan = Scan(
                domain_id=domain.id,
                started_at=datetime.utcnow(),
                questions_count=len(questions),
                status="running",
            )
            db.add(scan)
            await db.flush()
            scan_id = scan.id
        else:
            scan = await db.get(Scan, scan_id)
            if scan is None:
                raise ValueError(f"Scan id={scan_id} not found")
            scan.started_at = datetime.utcnow()
            scan.questions_count = len(questions)
            scan.status = "running"
        await db.commit()

    enabled = settings.enabled_models
    if not enabled:
        raise RuntimeError("No models enabled — set LLM_RANK_ENABLED_MODELS in .env")

    SCAN_PROGRESS[scan_id] = {"progress": 0, "total": len(questions) * len(enabled)}
    domain_str = normalize_domain(domain.domain)["full"]
    logger.info("Scan %d running with models=%s on %d questions", scan_id, enabled, len(questions))

    all_rows: list[dict[str, Any]] = []
    input_chars = 0
    output_chars = 0

    async with aiohttp.ClientSession() as http:
        # Process each question, but fan-out the 2 model calls in parallel per question.
        # Cap question-level concurrency to avoid hammering the APIs.
        sem = asyncio.Semaphore(4)

        async def _bounded(q: Question) -> list[dict[str, Any]]:
            async with sem:
                rows = await _run_one(http, q, domain_str, enabled)
                SCAN_PROGRESS[scan_id]["progress"] += len(enabled)
                return rows

        results_lists = await asyncio.gather(*[_bounded(q) for q in questions])
        for rl in results_lists:
            all_rows.extend(rl)
            for r in rl:
                input_chars += len(next((q.text for q in questions if q.id == r["question_id"]), ""))
                output_chars += len(r.get("response_text") or "")

    # Persist results and compute scores
    async with SessionLocal() as db:
        for row in all_rows:
            db.add(
                Result(
                    scan_id=scan_id,
                    question_id=row["question_id"],
                    model=row["model"],
                    visibility_status=row["visibility_status"],
                    raw_response=row["raw_response"],
                    cited_urls=row["cited_urls"],
                    response_text=row["response_text"],
                )
            )

        px_statuses = [r["visibility_status"] for r in all_rows if r["model"] == MODEL_PERPLEXITY]
        gm_statuses = [r["visibility_status"] for r in all_rows if r["model"] == MODEL_GEMINI]

        perplexity_score = per_model_score(px_statuses) if MODEL_PERPLEXITY in enabled else None
        gemini_score = per_model_score(gm_statuses) if MODEL_GEMINI in enabled else None
        overall = score_from_statuses([r["visibility_status"] for r in all_rows], len(questions))

        scan = await db.get(Scan, scan_id)
        scan.finished_at = datetime.utcnow()
        scan.score = overall
        scan.perplexity_score = perplexity_score
        scan.gemini_score = gemini_score
        scan.status = "complete"
        await db.commit()

    # Cost logging — only for enabled models
    px_cost = (
        estimated_cost_perplexity(" " * input_chars, " " * output_chars, search_requests=len(questions))
        if MODEL_PERPLEXITY in enabled else 0.0
    )
    gm_cost = (
        estimated_cost_gemini(" " * input_chars, " " * output_chars)
        if MODEL_GEMINI in enabled else 0.0
    )
    logger.info(
        "Scan %d complete — score=%.1f (px=%s, gm=%s). Cost est: $%.4f",
        scan_id, overall,
        f"{perplexity_score:.1f}" if perplexity_score is not None else "—",
        f"{gemini_score:.1f}" if gemini_score is not None else "—",
        px_cost + gm_cost,
    )

    return scan_id
