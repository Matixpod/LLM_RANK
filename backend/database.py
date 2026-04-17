"""SQLAlchemy async engine, session factory, and ORM models for LLM-RANK."""
from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings


class Base(DeclarativeBase):
    pass


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(64), default="English")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )
    scans: Mapped[list["Scan"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(64), default="English")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    domain: Mapped[Domain] = relationship(back_populates="questions")


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    perplexity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    gemini_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    questions_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")

    domain: Mapped[Domain] = relationship(back_populates="scans")
    results: Mapped[list["Result"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(32))
    visibility_status: Mapped[str] = mapped_column(String(32))
    raw_response: Mapped[dict] = mapped_column(JSON, default=dict)
    cited_urls: Mapped[list] = mapped_column(JSON, default=list)
    response_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scan: Mapped[Scan] = relationship(back_populates="results")


engine = create_async_engine(settings.db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create all tables if they don't exist, and add any missing columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        info = await conn.exec_driver_sql("PRAGMA table_info(domains)")
        cols = {r[1] for r in info.fetchall()}
        if "language" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE domains ADD COLUMN language VARCHAR(64) DEFAULT 'English'"
            )
        q_info = await conn.exec_driver_sql("PRAGMA table_info(questions)")
        q_cols = {r[1] for r in q_info.fetchall()}
        if "language" not in q_cols:
            await conn.exec_driver_sql(
                "ALTER TABLE questions ADD COLUMN language VARCHAR(64) DEFAULT 'English'"
            )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a session per-request."""
    async with SessionLocal() as session:
        yield session
