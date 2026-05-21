"""Deterministic context noise taxonomy and compression profiles."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from repo_semantic_memory.context.context_pack import SourceCitation
from repo_semantic_memory.memory import CompactSemanticComponent
from repo_semantic_memory.model import Relation

RelationVerbosity = Literal["compact", "standard", "verbose"]
CitationVerbosity = Literal["minimal", "standard", "full"]
CompressionProfileName = Literal[
    "agent_brief",
    "agent_standard",
    "agent_debug",
    "human_review",
    "ci_summary",
    "full",
]

NOISE_CATEGORIES: Final[tuple[str, ...]] = (
    "generated artifacts",
    "repeated imports",
    "standard library imports",
    "unresolved external imports",
    "duplicate logical relations",
    "low-signal metadata",
    "long component lists",
    "test fixture boilerplate",
    "build/cache/docs artifacts",
    "oversized doc sections",
    "low-rank tooling/config context when task does not request it",
)

PRESERVATION_CATEGORIES: Final[tuple[str, ...]] = (
    "direct task matches",
    "source citations",
    "selected gold items during eval",
    "explicit public exports",
    "confirmed claims",
    "active invariants",
    "high-confidence test relations",
    "high-score graph neighbors",
    "selected implementation symbols",
)


@dataclass(frozen=True)
class CompressionProfile:
    """Declarative profile for deterministic context compression."""

    name: CompressionProfileName
    max_imports_per_module: int | None
    max_components_per_entity: int | None
    include_unresolved_imports: bool
    include_ranking_breakdown: bool
    include_low_confidence_inferred_components: bool
    relation_verbosity: RelationVerbosity
    citation_verbosity: CitationVerbosity
    max_related_symbols: int | None
    max_uncertainties: int | None
    include_compact_score_reasons: bool
    max_score_reasons_per_item: int | None
    max_ranking_reasons_per_item: int | None
    max_ranking_breakdowns: int | None


_PROFILES: Final[dict[str, CompressionProfile]] = {
    "agent_brief": CompressionProfile(
        name="agent_brief",
        max_imports_per_module=6,
        max_components_per_entity=2,
        include_unresolved_imports=False,
        include_ranking_breakdown=False,
        include_low_confidence_inferred_components=False,
        relation_verbosity="compact",
        citation_verbosity="minimal",
        max_related_symbols=20,
        max_uncertainties=6,
        include_compact_score_reasons=False,
        max_score_reasons_per_item=1,
        max_ranking_reasons_per_item=3,
        max_ranking_breakdowns=8,
    ),
    "agent_standard": CompressionProfile(
        name="agent_standard",
        max_imports_per_module=12,
        max_components_per_entity=4,
        include_unresolved_imports=True,
        include_ranking_breakdown=False,
        include_low_confidence_inferred_components=False,
        relation_verbosity="standard",
        citation_verbosity="standard",
        max_related_symbols=40,
        max_uncertainties=12,
        include_compact_score_reasons=False,
        max_score_reasons_per_item=2,
        max_ranking_reasons_per_item=4,
        max_ranking_breakdowns=12,
    ),
    "agent_debug": CompressionProfile(
        name="agent_debug",
        max_imports_per_module=20,
        max_components_per_entity=6,
        include_unresolved_imports=True,
        include_ranking_breakdown=True,
        include_low_confidence_inferred_components=True,
        relation_verbosity="verbose",
        citation_verbosity="full",
        max_related_symbols=80,
        max_uncertainties=30,
        include_compact_score_reasons=True,
        max_score_reasons_per_item=4,
        max_ranking_reasons_per_item=6,
        max_ranking_breakdowns=20,
    ),
    "human_review": CompressionProfile(
        name="human_review",
        max_imports_per_module=16,
        max_components_per_entity=4,
        include_unresolved_imports=True,
        include_ranking_breakdown=False,
        include_low_confidence_inferred_components=False,
        relation_verbosity="standard",
        citation_verbosity="standard",
        max_related_symbols=50,
        max_uncertainties=15,
        include_compact_score_reasons=False,
        max_score_reasons_per_item=2,
        max_ranking_reasons_per_item=4,
        max_ranking_breakdowns=12,
    ),
    "ci_summary": CompressionProfile(
        name="ci_summary",
        max_imports_per_module=8,
        max_components_per_entity=3,
        include_unresolved_imports=False,
        include_ranking_breakdown=False,
        include_low_confidence_inferred_components=False,
        relation_verbosity="compact",
        citation_verbosity="minimal",
        max_related_symbols=24,
        max_uncertainties=8,
        include_compact_score_reasons=False,
        max_score_reasons_per_item=1,
        max_ranking_reasons_per_item=3,
        max_ranking_breakdowns=8,
    ),
    "full": CompressionProfile(
        name="full",
        max_imports_per_module=None,
        max_components_per_entity=None,
        include_unresolved_imports=True,
        include_ranking_breakdown=True,
        include_low_confidence_inferred_components=True,
        relation_verbosity="verbose",
        citation_verbosity="full",
        max_related_symbols=None,
        max_uncertainties=None,
        include_compact_score_reasons=True,
        max_score_reasons_per_item=8,
        max_ranking_reasons_per_item=10,
        max_ranking_breakdowns=40,
    ),
}


def available_profile_names() -> tuple[str, ...]:
    """Return deterministic profile names in stable order."""
    return (
        "agent_brief",
        "agent_standard",
        "agent_debug",
        "human_review",
        "ci_summary",
        "full",
    )


def resolve_profile(profile: CompressionProfile | str | None) -> CompressionProfile:
    """Resolve a profile object or profile name to a known profile."""
    if isinstance(profile, CompressionProfile):
        return profile
    profile_name = profile or "agent_standard"
    resolved = _PROFILES.get(profile_name)
    if resolved is None:
        supported = ", ".join(available_profile_names())
        raise ValueError(f"Unknown profile '{profile_name}'. Supported profiles: {supported}")
    return resolved


def filter_related_relations(
    relations: Sequence[Relation], *, profile: CompressionProfile
) -> list[Relation]:
    """Filter/slice related relations for deterministic profile-specific verbosity."""
    compact_relation_kinds = frozenset({"contains", "calls", "imports", "inherits", "tests"})
    filtered: list[Relation] = []
    for relation in relations:
        resolved = relation.metadata.get("resolved") is True
        unresolved_import_or_inherits = relation.kind in {"imports", "inherits"} and not resolved
        if unresolved_import_or_inherits and not profile.include_unresolved_imports:
            continue
        if profile.relation_verbosity == "compact" and relation.kind not in compact_relation_kinds:
            continue
        filtered.append(relation)
    if profile.max_related_symbols is None:
        return filtered
    return filtered[: profile.max_related_symbols]


def filter_uncertainties(
    uncertainties: Sequence[str], *, profile: CompressionProfile
) -> tuple[str, ...]:
    """Apply deterministic profile cap to uncertainty lines."""
    if profile.max_uncertainties is None:
        return tuple(uncertainties)
    return tuple(uncertainties[: profile.max_uncertainties])


def filter_source_citations(
    citations: Sequence[SourceCitation], *, profile: CompressionProfile
) -> list[SourceCitation]:
    """Filter source citations by verbosity tier."""
    if profile.citation_verbosity in {"standard", "full"}:
        return list(citations)
    return [citation for citation in citations if citation.subject_kind == "entity"]


def filter_semantic_components(
    components: Sequence[CompactSemanticComponent], *, profile: CompressionProfile
) -> tuple[CompactSemanticComponent, ...]:
    """Filter compact semantic components by confidence proxy and per-entity caps."""
    filtered = [
        component
        for component in components
        if profile.include_low_confidence_inferred_components
        or component.status == "confirmed"
        or component.status == "inferred"
    ]
    if profile.max_components_per_entity is None:
        return tuple(filtered)

    by_entity: dict[str, list[CompactSemanticComponent]] = defaultdict(list)
    for component in filtered:
        by_entity[component.entity_id].append(component)

    kept: list[CompactSemanticComponent] = []
    for entity_id in sorted(by_entity.keys()):
        entity_components = sorted(
            by_entity[entity_id],
            key=lambda item: (item.component_type, item.status),
        )
        kept.extend(entity_components[: profile.max_components_per_entity])
    return tuple(kept)


def trim_import_names(
    import_names: Sequence[str], *, profile: CompressionProfile
) -> tuple[str, ...]:
    """Apply deterministic import-list trimming for repo-map rendering."""
    if profile.max_imports_per_module is None:
        return tuple(import_names)
    return tuple(import_names[: profile.max_imports_per_module])
