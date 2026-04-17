"""CLI entry point for LLM-RANK. Scans, question regeneration, or serves the API."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from backend.config import configure_logging, settings
from backend.database import Domain, SessionLocal, init_db
from backend.parsers import normalize_domain
from backend.pipeline import run_scan

logger = logging.getLogger("llm_rank.cli")


def _check_python_version() -> None:
    if sys.version_info < (3, 11):
        sys.stderr.write(
            "ERROR: LLM-RANK requires Python 3.11+. "
            "Install via: sudo apt install python3.11 python3.11-venv && "
            "python3.11 -m venv venv && source venv/bin/activate\n"
        )
        sys.exit(1)


async def _get_or_create_domain(domain: str, industry: str, language: str) -> int:
    """Return id of an existing or newly-created domain row."""
    normalized = normalize_domain(domain)["full"]
    async with SessionLocal() as db:
        existing = await db.execute(select(Domain).where(Domain.domain == normalized))
        row = existing.scalar_one_or_none()
        if row:
            if row.language != language:
                row.language = language
                await db.commit()
            return row.id
        d = Domain(domain=normalized, industry=industry, language=language)
        db.add(d)
        await db.commit()
        await db.refresh(d)
        return d.id


async def _cmd_scan(domain: str, industry: str, language: str, force_regenerate: bool) -> None:
    await init_db()
    domain_id = await _get_or_create_domain(domain, industry, language)
    logger.info("Starting scan for %s (domain_id=%d)", domain, domain_id)
    scan_id = await run_scan(domain_id, force_regenerate=force_regenerate)
    logger.info("Scan finished — scan_id=%d", scan_id)


def _cmd_serve() -> None:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


def main() -> None:
    _check_python_version()
    configure_logging()

    parser = argparse.ArgumentParser(description="LLM-RANK: AI visibility tracker")
    parser.add_argument("--domain", help="Domain to scan (e.g. example.com)")
    parser.add_argument("--industry", help="Industry description")
    parser.add_argument(
        "--language",
        default="English",
        help="Language for generated questions (e.g. English, Polish, German). Default: English",
    )
    parser.add_argument(
        "--generate-questions",
        action="store_true",
        help="Force regeneration of questions for this domain",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI server (default http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    if args.serve:
        _cmd_serve()
        return

    if not args.domain or not args.industry:
        parser.error("--domain and --industry are required (or use --serve)")

    asyncio.run(_cmd_scan(args.domain, args.industry, args.language, args.generate_questions))


if __name__ == "__main__":
    main()
