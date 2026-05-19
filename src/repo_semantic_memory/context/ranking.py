"""Deterministic ranking primitives for context-pack entity selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RankingCategory = Literal[
    "lexical",
    "path_role",
    "task_intent",
    "component",
    "graph",
    "penalty",
]

_ROUND_PRECISION = 6


@dataclass(frozen=True)
class RankingReason:
    """Compact deterministic explanation item for rank contributions."""

    category: RankingCategory
    message: str
    score_delta: float

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "message": self.message,
            "score_delta": _round_score(self.score_delta),
        }


@dataclass(frozen=True)
class RankingBreakdown:
    """Deterministic score components and lexical matching evidence."""

    lexical: float
    path_role: float
    task_intent: float
    component: float
    graph: float
    penalty: float
    total: float
    matched_terms: tuple[str, ...]
    matched_fields: tuple[str, ...]
    reasons: tuple[RankingReason, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "lexical": _round_score(self.lexical),
            "path_role": _round_score(self.path_role),
            "task_intent": _round_score(self.task_intent),
            "component": _round_score(self.component),
            "graph": _round_score(self.graph),
            "penalty": _round_score(self.penalty),
            "total": _round_score(self.total),
            "matched_terms": list(self.matched_terms),
            "matched_fields": list(self.matched_fields),
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


def combine_score_components(
    *,
    lexical: float,
    path_role: float,
    task_intent: float,
    component: float,
    graph: float,
    penalty: float,
) -> float:
    """Combine fixed score components with deterministic rounding."""
    return _round_score(lexical + path_role + task_intent + component + graph + penalty)


def build_breakdown(
    *,
    lexical: float,
    path_role: float,
    task_intent: float,
    component: float,
    graph: float,
    penalty: float,
    matched_terms: tuple[str, ...],
    matched_fields: tuple[str, ...],
    reasons: tuple[RankingReason, ...],
) -> RankingBreakdown:
    """Build a normalized ranking breakdown payload."""
    return RankingBreakdown(
        lexical=_round_score(lexical),
        path_role=_round_score(path_role),
        task_intent=_round_score(task_intent),
        component=_round_score(component),
        graph=_round_score(graph),
        penalty=_round_score(penalty),
        total=combine_score_components(
            lexical=lexical,
            path_role=path_role,
            task_intent=task_intent,
            component=component,
            graph=graph,
            penalty=penalty,
        ),
        matched_terms=matched_terms,
        matched_fields=matched_fields,
        reasons=reasons,
    )


def dedupe_stable(items: tuple[str, ...]) -> tuple[str, ...]:
    """Remove duplicates preserving first-seen deterministic order."""
    return tuple(dict.fromkeys(items))


def append_reason(
    reasons: list[RankingReason],
    *,
    category: RankingCategory,
    message: str,
    score_delta: float,
) -> None:
    """Append reason while normalizing score deltas."""
    reasons.append(
        RankingReason(
            category=category,
            message=message,
            score_delta=_round_score(score_delta),
        )
    )


def _round_score(value: float) -> float:
    return float(round(value, _ROUND_PRECISION))
