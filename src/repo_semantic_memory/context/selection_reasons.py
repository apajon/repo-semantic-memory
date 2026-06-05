"""Closed-vocabulary machine-readable selection reasons for context-pack output.

Provides a deterministic, closed-vocabulary reason model so agents and evaluators
can parse why each file/entity was included in a context pack without parsing
free-form text.

This is the Ranking v2 Step 5 (Prompt 58.5) implementation.
No NLP models are used; all classification is deterministic pure-Python logic.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Closed vocabulary
# ---------------------------------------------------------------------------

#: All valid selection reason codes.  Enforced in :class:`SelectionReason.__post_init__`.
SELECTION_REASON_CODES: frozenset[str] = frozenset(
    {
        # Entity matched via BM25 lexical / field scoring.
        "lexical_match",
        # Entity matched because of query intent / task-hint conditioning.
        "intent_match",
        # Entity score was adjusted by a task-aware path prior.
        "path_prior",
        # Entity selected as a primary/central result from the main ranking pass.
        "central_candidate",
        # Entity selected as a graph-expansion neighbor of a seed entity.
        "graph_neighbor",
        # Support file: selected because a central entity imports it.
        "support_import",
        # Support file: selected because it exports / is exported by a central entity.
        "support_export",
        # Support file: selected via an ``inherits`` relation with a central entity.
        "support_inherits",
        # Support file: selected because it is in the same package as a central entity.
        "support_same_package",
        # Support file: selected as a public-API surface (e.g. ``__init__.py``).
        "support_public_api",
        # Test file: selected via an explicit ``tests`` relation to a central entity.
        "test_relation",
        # Test file: selected via directory-path proximity to central entities.
        "test_path_proximity",
        # Test file: selected because its filename stem matches a central entity.
        "test_stem_match",
        # Test file: selected via lexical token overlap with query tokens.
        "test_lexical_match",
        # Entity flagged with a scope/quality warning (e.g. generated artifact).
        "scope_warning",
    }
)


# ---------------------------------------------------------------------------
# SelectionReason dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionReason:
    """Machine-readable selection reason for a context-pack entity or relation.

    Attributes:
        code: Closed-vocabulary reason code.  Must be one of
            :data:`SELECTION_REASON_CODES`.
        detail: Optional short string providing additional context (e.g. the
            path of a related file, matched intent name, or numeric delta).
            ``None`` when no further disambiguation is needed.
    """

    code: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.code not in SELECTION_REASON_CODES:
            raise ValueError(
                f"Unknown selection reason code: {self.code!r}. "
                f"Must be one of: {sorted(SELECTION_REASON_CODES)}"
            )

    def to_dict(self) -> dict[str, object]:
        """Serialize to a deterministic dictionary suitable for JSON output."""
        payload: dict[str, object] = {"code": self.code}
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def dedupe_selection_reasons(
    reasons: tuple[SelectionReason, ...],
) -> tuple[SelectionReason, ...]:
    """Remove duplicate reasons preserving first-seen deterministic order.

    Two reasons are considered identical when they share the same ``code``
    *and* ``detail`` value.
    """
    seen: dict[tuple[str, str | None], None] = {}
    for reason in reasons:
        key = (reason.code, reason.detail)
        seen[key] = None
    return tuple(SelectionReason(code, detail) for code, detail in seen)


# ---------------------------------------------------------------------------
# Classifier: map free-form reason strings → SelectionReason
# ---------------------------------------------------------------------------


def classify_reason_string(reason: str) -> SelectionReason:
    """Map a pipeline reason string to a closed-vocabulary :class:`SelectionReason`.

    Classifies the human-readable reason strings produced by the pipeline stages
    in ``pack_builder.py`` into the closed vocabulary.  Covers all reason strings
    produced by:

    - ``pack_builder._score_entity`` (lexical / intent / path_prior / penalty)
    - ``graph_selection.select_graph_neighbors`` (graph)
    - ``support_expansion.select_support_files`` (support)
    - ``test_branch.select_test_branch`` (test)

    Unrecognized strings fall back to ``"central_candidate"``.

    Args:
        reason: Human-readable reason string from the pipeline.

    Returns:
        A :class:`SelectionReason` with a closed-vocabulary ``code`` and an
        optional ``detail`` extracted from the reason string.
    """
    r = reason.strip()
    r_lower = r.lower()

    # ---- Test-branch reasons (prefix: "test branch:") ----
    if r_lower.startswith("test branch:"):
        rest = r_lower[len("test branch:") :].strip()
        if "tests relation" in rest:
            return SelectionReason("test_relation", _last_path_token(r))
        if "stem proximity" in rest or "filename stem" in rest:
            return SelectionReason("test_stem_match", _parens_content(r))
        if "lexical token" in rest:
            return SelectionReason("test_lexical_match", _parens_content(r))
        return SelectionReason("test_path_proximity")

    # ---- Support-expansion reasons (prefix: "support:") ----
    if r_lower.startswith("support:"):
        rest = r_lower[len("support:") :].strip()
        if "imported by" in rest or rest.startswith("imports "):
            return SelectionReason("support_import", _last_path_token(r))
        if "export surface" in rest or "exported by" in rest:
            return SelectionReason("support_export", _last_path_token(r))
        if "inherit" in rest:
            return SelectionReason("support_inherits", _last_path_token(r))
        if "same package" in rest:
            return SelectionReason("support_same_package", _parens_content(r))
        if "public api" in rest:
            return SelectionReason("support_public_api", _parens_content(r))
        # Fallback for "support: structural adjacency" and similar.
        return SelectionReason("support_same_package")

    # ---- Graph-neighbor reasons ----
    if r_lower.startswith("graph neighbor"):
        return SelectionReason("graph_neighbor")

    # ---- Path-prior reasons (prefix: "path prior") ----
    if r_lower.startswith("path prior"):
        return SelectionReason("path_prior", _parens_content(r))

    # ---- Scope warnings / penalties ----
    if "generated" in r_lower and "artifact" in r_lower:
        return SelectionReason("scope_warning", "generated artifact")

    # Public-API downranks (docs/tooling) are path adjustments, not intent signals.
    if "public api task hint" in r_lower and "downrank" in r_lower:
        if "docs" in r_lower or "prose" in r_lower:
            return SelectionReason("path_prior", "docs downrank")
        if "tool" in r_lower:
            return SelectionReason("path_prior", "tooling downrank")

    # ---- Intent-match reasons (task hint / task intent boosts) ----
    if any(
        kw in r_lower
        for kw in (
            "task hint",
            "task intent",
            "intent boost",
            "test-like",
            "supporting context",
            "public api task",
            "boosted public",
        )
    ):
        return SelectionReason("intent_match", _extract_intent_detail(r_lower))

    # ---- Lexical reasons ----
    if "lexical" in r_lower:
        return SelectionReason("lexical_match")

    # ---- Fallback (e.g. "fallback deterministic seed", "incident to selected entity") ----
    return SelectionReason("central_candidate")


def build_selection_reasons(
    reasons_by_key: dict[str, tuple[str, ...]],
) -> dict[str, tuple[SelectionReason, ...]]:
    """Build a structured selection-reasons dict from free-form reason strings.

    Maps each entry in *reasons_by_key* (entity-id or relation-key → reason
    strings) to :class:`SelectionReason` objects using :func:`classify_reason_string`,
    then deduplicates within each entry.

    Entries with no reasons are omitted from the output.

    Args:
        reasons_by_key: Mapping from entity/relation key to a tuple of
            human-readable reason strings (as produced by
            ``pack_builder.score_capped_reasons_by_key``).

    Returns:
        Mapping from entity/relation key to a tuple of
        :class:`SelectionReason` objects, deduplicated and in deterministic order.
    """
    result: dict[str, tuple[SelectionReason, ...]] = {}
    for key in sorted(reasons_by_key.keys()):
        raw_reasons = reasons_by_key[key]
        if not raw_reasons:
            continue
        structured = tuple(classify_reason_string(r) for r in raw_reasons)
        result[key] = dedupe_selection_reasons(structured)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _last_path_token(reason: str) -> str | None:
    """Return the last whitespace-delimited token that looks like a file path."""
    for token in reversed(reason.split()):
        if "/" in token:
            return token
    return None


def _parens_content(reason: str) -> str | None:
    """Return the content inside the last parentheses pair, stripped of quotes."""
    start = reason.rfind("(")
    end = reason.rfind(")")
    if 0 <= start < end:
        inner = reason[start + 1 : end].strip().strip("'\"")
        return inner or None
    return None


def _extract_intent_detail(r_lower: str) -> str | None:
    """Extract the primary intent name from a lower-cased task-hint reason string."""
    if "implementation" in r_lower and "test" in r_lower:
        return "implementation+tests"
    if "implementation" in r_lower:
        return "implementation"
    if "test" in r_lower:
        return "tests"
    if "public api" in r_lower or "public_api" in r_lower:
        return "public_api"
    if "config" in r_lower or "build" in r_lower or "release" in r_lower:
        return "config_build_release"
    return None
