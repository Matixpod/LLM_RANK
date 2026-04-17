"""Pydantic v2 request/response schemas for the FastAPI layer."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DomainCreate(BaseModel):
    domain: str = Field(..., min_length=1)
    industry: str = Field(..., min_length=1)
    language: str = Field(default="English", min_length=1)


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    industry: str
    language: str
    created_at: datetime


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain_id: int
    text: str
    language: str = "English"
    created_at: datetime
    is_active: bool


class QuestionCreate(BaseModel):
    text: str = Field(..., min_length=1)


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain_id: int
    started_at: datetime
    finished_at: datetime | None
    score: float | None
    perplexity_score: float | None
    gemini_score: float | None
    questions_count: int
    status: str


class ScanStatus(BaseModel):
    scan_id: int
    status: str
    progress: int
    total: int
    score: float | None
    perplexity_score: float | None
    gemini_score: float | None


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scan_id: int
    question_id: int
    question_text: str
    model: str
    visibility_status: str
    cited_urls: list[Any] = []
    response_text: str
    created_at: datetime


class GapOut(BaseModel):
    question_id: int
    text: str
    models_missing: list[str]


class ScanTriggerResponse(BaseModel):
    scan_id: int
    status: str
