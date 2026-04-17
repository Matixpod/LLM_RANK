"""LLM Visibility Score calculation."""
from __future__ import annotations

from typing import Iterable

POINTS = {"cited": 3, "mentioned": 1, "not_present": 0, "error": 0}


def points_for(status: str) -> int:
    return POINTS.get(status, 0)


def score_from_statuses(statuses: Iterable[str], questions_count: int) -> float:
    """Generic scorer over (questions × models) statuses.

    Max = questions_count * num_models * 3. We compute num_models from the
    total statuses / questions_count.
    """
    statuses = list(statuses)
    if not statuses or questions_count <= 0:
        return 0.0
    num_models = max(1, len(statuses) // questions_count)
    total = sum(points_for(s) for s in statuses)
    max_total = questions_count * num_models * 3
    if max_total == 0:
        return 0.0
    return round((total / max_total) * 100, 1)


def per_model_score(statuses_for_model: list[str]) -> float:
    """Score for a single model: (sum / (n * 3)) * 100."""
    if not statuses_for_model:
        return 0.0
    total = sum(points_for(s) for s in statuses_for_model)
    max_total = len(statuses_for_model) * 3
    return round((total / max_total) * 100, 1)
