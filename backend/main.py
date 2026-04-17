"""FastAPI application exposing domain management, scans, and exports."""
from __future__ import annotations

import csv
import io
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import configure_logging
from .database import Domain, Question, Result, Scan, get_session, init_db
from .parsers import normalize_domain
from .pipeline import SCAN_PROGRESS, run_scan
from .question_gen import QuestionGenerationError, generate_questions
from .schemas import (
    DomainCreate,
    DomainOut,
    GapOut,
    QuestionCreate,
    QuestionOut,
    ResultOut,
    ScanOut,
    ScanStatus,
    ScanTriggerResponse,
)

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="LLM-RANK", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------
@app.post("/api/domains", response_model=DomainOut)
async def create_domain(payload: DomainCreate, db: AsyncSession = Depends(get_session)):
    normalized = normalize_domain(payload.domain)["full"]
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid domain")

    existing = await db.execute(select(Domain).where(Domain.domain == normalized))
    row = existing.scalar_one_or_none()
    if row:
        return row

    domain = Domain(
        domain=normalized,
        industry=payload.industry,
        language=payload.language,
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@app.get("/api/domains", response_model=list[DomainOut])
async def list_domains(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Domain).order_by(desc(Domain.created_at)))
    return list(result.scalars().all())


@app.delete("/api/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(domain_id: int, db: AsyncSession = Depends(get_session)):
    domain = await db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    scan_ids = (
        await db.execute(select(Scan.id).where(Scan.domain_id == domain_id))
    ).scalars().all()

    await db.delete(domain)
    await db.commit()

    for sid in scan_ids:
        SCAN_PROGRESS.pop(sid, None)
    return None


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------
async def _run_scan_bg(domain_id: int, scan_id: int) -> None:
    try:
        await run_scan(domain_id, scan_id=scan_id)
    except Exception:
        logger.exception("Background scan failed for domain_id=%s", domain_id)
        # Mark the scan as failed so status polling reflects the error.
        from .database import SessionLocal as _SL
        async with _SL() as db:
            s = await db.get(Scan, scan_id)
            if s:
                s.status = "error"
                await db.commit()


@app.post("/api/scan/{domain_id}", response_model=ScanTriggerResponse)
async def trigger_scan(
    domain_id: int,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    domain = await db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    scan = Scan(domain_id=domain_id, status="queued", questions_count=0)
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    background.add_task(_run_scan_bg, domain_id, scan.id)
    return ScanTriggerResponse(scan_id=scan.id, status="queued")


@app.get("/api/domains/{domain_id}/scans/latest", response_model=ScanOut | None)
async def latest_scan(domain_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(Scan).where(Scan.domain_id == domain_id).order_by(desc(Scan.started_at)).limit(1)
    )
    return result.scalar_one_or_none()


@app.get("/api/scan/{scan_id}/status", response_model=ScanStatus)
async def scan_status(scan_id: int, db: AsyncSession = Depends(get_session)):
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    tracker = SCAN_PROGRESS.get(scan_id, {})
    return ScanStatus(
        scan_id=scan.id,
        status=scan.status,
        progress=tracker.get("progress", scan.questions_count * 2 if scan.status == "complete" else 0),
        total=tracker.get("total", scan.questions_count * 2),
        score=scan.score,
        perplexity_score=scan.perplexity_score,
        gemini_score=scan.gemini_score,
    )


@app.get("/api/scans/{scan_id}/results", response_model=list[ResultOut])
async def scan_results(scan_id: int, db: AsyncSession = Depends(get_session)):
    """Return every per-question / per-model result for a scan, with question text."""
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    rows = (
        await db.execute(
            select(Result, Question)
            .join(Question, Question.id == Result.question_id)
            .where(Result.scan_id == scan_id)
            .order_by(Result.question_id, Result.model)
        )
    ).all()

    return [
        ResultOut(
            id=r.id,
            scan_id=r.scan_id,
            question_id=r.question_id,
            question_text=q.text,
            model=r.model,
            visibility_status=r.visibility_status,
            cited_urls=r.cited_urls or [],
            response_text=r.response_text or "",
            created_at=r.created_at,
        )
        for r, q in rows
    ]


@app.get("/api/domains/{domain_id}/history", response_model=list[ScanOut])
async def domain_history(domain_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(Scan)
        .where(Scan.domain_id == domain_id, Scan.status == "complete")
        .order_by(Scan.started_at)
    )
    return list(result.scalars().all())


@app.get("/api/domains/{domain_id}/gaps", response_model=list[GapOut])
async def domain_gaps(domain_id: int, db: AsyncSession = Depends(get_session)):
    # Find the latest complete scan
    result = await db.execute(
        select(Scan)
        .where(Scan.domain_id == domain_id, Scan.status == "complete")
        .order_by(desc(Scan.started_at))
        .limit(1)
    )
    scan = result.scalar_one_or_none()
    if scan is None:
        return []

    res = await db.execute(
        select(Result, Question)
        .join(Question, Question.id == Result.question_id)
        .where(Result.scan_id == scan.id, Result.visibility_status == "not_present")
    )

    # Group by question
    by_qid: dict[int, GapOut] = {}
    for result_row, q in res.all():
        gap = by_qid.get(q.id)
        if gap is None:
            gap = GapOut(question_id=q.id, text=q.text, models_missing=[])
            by_qid[q.id] = gap
        gap.models_missing.append(result_row.model)

    # Sort by number of missing models (most missing first)
    return sorted(by_qid.values(), key=lambda g: -len(g.models_missing))


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------
@app.get("/api/questions/{domain_id}", response_model=list[QuestionOut])
async def list_questions(domain_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(Question).where(Question.domain_id == domain_id).order_by(Question.created_at)
    )
    return list(result.scalars().all())


@app.post("/api/questions/{domain_id}", response_model=QuestionOut)
async def add_question(
    domain_id: int,
    payload: QuestionCreate,
    db: AsyncSession = Depends(get_session),
):
    domain = await db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    q = Question(
        domain_id=domain_id,
        text=payload.text.strip(),
        language=domain.language,
        is_active=True,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


@app.post("/api/questions/{domain_id}/generate", response_model=list[QuestionOut])
async def generate_more_questions(
    domain_id: int,
    count: int = 10,
    db: AsyncSession = Depends(get_session),
):
    """Generate N additional LLM questions for a domain, appending to existing ones."""
    domain = await db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    count = max(1, min(count, 25))

    existing = (
        await db.execute(
            select(Question).where(
                Question.domain_id == domain_id, Question.is_active == True  # noqa: E712
            )
        )
    ).scalars().all()
    avoid = [q.text for q in existing]

    try:
        texts = await generate_questions(
            domain.industry,
            count=count,
            language=domain.language,
            domain=domain.domain,
            avoid=avoid,
        )
    except QuestionGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    seen = {t.strip().lower() for t in avoid}
    created: list[Question] = []
    for t in texts:
        key = t.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        q = Question(
            domain_id=domain_id,
            text=t.strip(),
            language=domain.language,
            is_active=True,
        )
        db.add(q)
        created.append(q)

    await db.commit()
    for q in created:
        await db.refresh(q)
    return created


@app.delete("/api/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: int, db: AsyncSession = Depends(get_session)):
    q = await db.get(Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.delete(q)
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@app.get("/api/export/{domain_id}/csv")
async def export_csv(domain_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(Scan, Result, Question)
        .join(Result, Result.scan_id == Scan.id)
        .join(Question, Question.id == Result.question_id)
        .where(Scan.domain_id == domain_id, Scan.status == "complete")
        .order_by(Scan.started_at)
    )
    rows = result.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["scan_date", "question", "model", "visibility_status", "cited_urls"])
    for scan, res, q in rows:
        writer.writerow(
            [
                scan.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                q.text,
                res.model,
                res.visibility_status,
                str(res.cited_urls or []),
            ]
        )

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="llm_rank_domain_{domain_id}.csv"'
        },
    )
