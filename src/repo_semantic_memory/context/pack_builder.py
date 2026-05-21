"""Deterministic lexical context pack builder."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from repo_semantic_memory.context.bm25 import FieldedBM25Index, FieldedDocument, tokenize_text
from repo_semantic_memory.context.compression import (
    CompressionProfile,
    filter_related_relations,
    filter_semantic_components,
    filter_source_citations,
    filter_uncertainties,
    resolve_profile,
)
from repo_semantic_memory.context.context_pack import ContextPack, SourceCitation, relation_key
from repo_semantic_memory.context.graph_selection import (
    GraphSelectionConfig,
    select_graph_neighbors,
)
from repo_semantic_memory.context.path_roles import (
    DOC_ROLE,
    SOURCE_ROLE,
    TOOL_ROLE,
    classify_path_role,
    infer_source_roots,
    is_generated_artifact_path,
)
from repo_semantic_memory.context.ranking import (
    RankingBreakdown,
    RankingCategory,
    RankingReason,
    append_reason,
    build_breakdown,
    dedupe_stable,
)
from repo_semantic_memory.memory import compact_component_labels, infer_semantic_components
from repo_semantic_memory.model import Entity, JsonValue, Relation, SemanticComponent

_CODE_ENTITY_KINDS = frozenset({"module", "class", "function", "method", "field", "test"})
_COARSE_ENTITY_KINDS = frozenset({"doc", "concept", "invariant"})
_CODE_TASK_TOKENS = frozenset(
    {
        "code",
        "class",
        "function",
        "method",
        "module",
        "import",
        "inherit",
        "refactor",
        "bug",
        "fix",
        "python",
        "py",
        "src",
    }
)
_IMPLEMENTATION_TASK_TOKENS = frozenset(
    {"implementation", "implemented", "source", "ownership", "cleanup"}
)
_IMPLEMENTATION_CORE_LOGIC_TOKENS = frozenset({"core", "logic"})
_IMPLEMENTATION_PRIORITIZED_ENTITY_KINDS = frozenset({"module", "class", "function", "method"})
_TEST_TASK_TOKENS = frozenset({"test", "tests", "behavior", "coverage", "pytest", "regression"})
_PUBLIC_API_TASK_TOKENS = frozenset({"public", "api", "export", "exports", "__init__", "init"})
_FORBIDDEN_ASSUMPTIONS = (
    (
        "Do not assume inheritance targets are resolved unless relation metadata says "
        "`resolved: true`."
    ),
    "Do not assume imports are resolved unless relation metadata says `resolved: true`.",
)
# Approximate output scaffold overhead for:
# - title/task lines
# - fixed section headings
# - uncertainty/forbidden-assumptions labels
# - minimum list-marker punctuation across sections
_PACK_FIXED_OVERHEAD_CHARS = 300
_CODE_PATH_SUFFIXES = (".py",)
_EXACT_FIELD_MATCH_BOOST = 6.0
# Scoring weights — all scoring/penalty constants remain here because they are
# ranking concerns specific to pack_builder, not path classification concerns.
_SOURCE_CITATION_BONUS = 2
_AST_BACKED_BONUS = 10
_CODE_ENTITY_KIND_BONUS = 6
_COARSE_ENTITY_PENALTY = -6
_CITATION_RANGE_OVERHEAD_CHARS = 24
_IMPLEMENTATION_PATH_ROLE_BONUS = 14
_IMPLEMENTATION_TASK_INTENT_BONUS = 6
_IMPLEMENTATION_SOURCE_ENTITY_KIND_BONUS = 6
_IMPLEMENTATION_TEST_SUPPORT_PATH_BONUS = 2
_IMPLEMENTATION_TEST_SUPPORT_TASK_INTENT_BONUS = 1
_TEST_PATH_ROLE_BONUS = 14
_TEST_TASK_INTENT_BONUS = 6
_PUBLIC_API_PATH_ROLE_BONUS = 16
_PUBLIC_API_TASK_INTENT_BONUS = 8
_PUBLIC_API_COMPONENT_BONUS = 16
# Public-API ranking hierarchy:
# - explicit package surfaces (`__init__.py`, confirmed PublicAPI, exports source) get
#   the strongest boosts so source-defined import surfaces lead public-api tasks;
# - export targets are boosted, but less than export sources, to keep package surfaces first;
# - source package roots receive a smaller boost for contextual support;
# - docs/tooling receive mild penalties so they remain selectable supporting context.
_PUBLIC_API_EXPORT_SOURCE_BONUS = 14
_PUBLIC_API_EXPORT_TARGET_BONUS = 6
_PUBLIC_API_SOURCE_PACKAGE_BONUS = 8
_PUBLIC_API_DOC_DOWNRANK = -5
_PUBLIC_API_TOOLING_DOWNRANK = -6
_PUBLIC_API_COPILOT_TOOLING_DOWNRANK = -8
# Boost for test files that test public imports (e.g. test_*.py with public/api/import tokens).
# Applied when public_api task hint is active and entity is in a tests/ path.
_PUBLIC_API_IMPORT_TEST_BOOST = 4
# Detection of generated artifacts is delegated to path_roles.is_generated_artifact_path.
_GENERATED_ARTIFACT_PENALTY = -80
_PRIORITIZED_BREAKDOWN_REASON_CATEGORIES = frozenset(
    {"task_intent", "path_role", "component", "penalty"}
)
_RANKING_REASON_PRIORITY = {
    "task_intent": 0,
    "path_role": 1,
    "component": 2,
    "graph": 3,
    "penalty": 4,
    "lexical": 5,
}
_DEFAULT_RANKING_REASON_PRIORITY = 6


def build_context_pack(
    *,
    task: str,
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    budget_chars: int,
    explain_ranking: bool = False,
    profile: CompressionProfile | str | None = None,
) -> ContextPack:
    """Build a compact context pack for a task from indexed entities and relations."""
    if budget_chars < 1:
        raise ValueError("budget_chars must be >= 1")

    resolved_profile = resolve_profile(profile)
    normalized_entities = sorted(entities, key=lambda entity: entity.id.value)
    normalized_relations = sorted(
        relations,
        key=lambda relation: (
            relation.kind,
            relation.source_entity_id.value,
            relation.target_entity_id.value,
        ),
    )
    entity_by_id = {entity.id.value: entity for entity in normalized_entities}
    task_tokens = _tokenize(task)
    is_code_task = _is_code_task(task_tokens)
    task_hints = _task_hints(task_tokens)
    inferred_components = infer_semantic_components(
        entities=normalized_entities,
        relations=normalized_relations,
    )
    source_roots = infer_source_roots(normalized_entities)
    public_api_entity_ids = {
        component.entity_id.value
        for component in inferred_components
        if component.component_type == "PublicAPI"
    }
    export_source_entity_ids = {
        relation.source_entity_id.value
        for relation in normalized_relations
        if relation.kind == "exports"
    }
    export_target_entity_ids = {
        relation.target_entity_id.value
        for relation in normalized_relations
        if relation.kind == "exports"
    }

    ranked = _rank_entities(
        entities=normalized_entities,
        relations=normalized_relations,
        inferred_components=inferred_components,
        task_tokens=task_tokens,
        is_code_task=is_code_task,
        task_hints=task_hints,
        public_api_entity_ids=public_api_entity_ids,
        export_source_entity_ids=export_source_entity_ids,
        export_target_entity_ids=export_target_entity_ids,
        source_roots=source_roots,
    )

    selected_entity_ids: list[str] = []
    selected_entity_set: set[str] = set()
    # List (not set) to preserve deterministic insertion order for graph seed_ids.
    graph_seed_ids: list[str] = []
    reasons_by_key: dict[str, list[str]] = defaultdict(list)
    ranking_breakdowns_by_id: dict[str, RankingBreakdown] = {}
    for entity, breakdown in ranked:
        reason_messages = tuple(reason.message for reason in breakdown.reasons)
        if reason_messages:
            _add_entity(entity.id.value, selected_entity_ids, selected_entity_set)
            reasons_by_key[entity.id.value].extend(reason_messages)
            if explain_ranking or resolved_profile.include_ranking_breakdown:
                ranking_breakdowns_by_id[entity.id.value] = breakdown
            if _is_graph_seed_eligible(breakdown):
                graph_seed_ids.append(entity.id.value)

    if not selected_entity_ids and normalized_entities:
        fallback = normalized_entities[0]
        _add_entity(fallback.id.value, selected_entity_ids, selected_entity_set)
        reasons_by_key[fallback.id.value].append("fallback deterministic seed")
        graph_seed_ids.append(fallback.id.value)
        if explain_ranking or resolved_profile.include_ranking_breakdown:
            ranking_breakdowns_by_id[fallback.id.value] = build_breakdown(
                lexical=0,
                path_role=0,
                task_intent=0,
                component=0,
                graph=0,
                penalty=0,
                matched_terms=(),
                matched_fields=(),
                reasons=(dedupe_stable_reasons((("graph", "fallback deterministic seed", 0.0),))),
            )

    # Weighted graph neighbor selection using only task-relevant seeds.
    # exclude_ids is scoped to graph seeds (not all selected) so that entities which
    # passed the inclusion threshold via structural bonuses alone can still be
    # discovered as graph-scored neighbors of genuinely task-relevant seeds.
    graph_result = select_graph_neighbors(
        seed_ids=tuple(graph_seed_ids),
        entity_id_set=frozenset(entity_by_id.keys()),
        relations=normalized_relations,
        config=GraphSelectionConfig(),
        exclude_ids=frozenset(graph_seed_ids),
    )
    for neighbor_id in graph_result.selected_ids:
        is_new = _add_entity(neighbor_id, selected_entity_ids, selected_entity_set)
        graph_score = graph_result.scores_by_id[neighbor_id]
        neighbor_reasons = graph_result.reasons_by_id.get(neighbor_id, ())
        # Only add graph reasons to reasons_by_key for newly selected entities.
        # Already-selected entities already have lexical/structural reasons; adding
        # graph reasons would inflate their estimated character cost in the output
        # (reasons are rendered verbatim), consuming budget that would otherwise
        # accommodate more entities and relations.
        if is_new:
            for reason_msg in neighbor_reasons:
                reasons_by_key[neighbor_id].append(reason_msg)
        if explain_ranking or resolved_profile.include_ranking_breakdown:
            reason_tuples: tuple[tuple[RankingCategory, str, float], ...]
            if neighbor_reasons:
                reason_tuples = tuple(("graph", msg, graph_score) for msg in neighbor_reasons)
            else:
                reason_tuples = (
                    ("graph", f"graph neighbor (score={graph_score:.3f})", graph_score),
                )
            if neighbor_id not in ranking_breakdowns_by_id:
                ranking_breakdowns_by_id[neighbor_id] = build_breakdown(
                    lexical=0,
                    path_role=0,
                    task_intent=0,
                    component=0,
                    graph=graph_score,
                    penalty=0,
                    matched_terms=(),
                    matched_fields=(),
                    reasons=dedupe_stable_reasons(reason_tuples),
                )
            elif graph_score > ranking_breakdowns_by_id[neighbor_id].graph:
                # Entity was already selected via structural bonuses; update its
                # breakdown to reflect the graph contribution from this expansion.
                existing = ranking_breakdowns_by_id[neighbor_id]
                existing_reason_tuples = tuple(
                    (r.category, r.message, r.score_delta) for r in existing.reasons
                )
                ranking_breakdowns_by_id[neighbor_id] = build_breakdown(
                    lexical=existing.lexical,
                    path_role=existing.path_role,
                    task_intent=existing.task_intent,
                    component=existing.component,
                    graph=graph_score,
                    penalty=existing.penalty,
                    matched_terms=existing.matched_terms,
                    matched_fields=existing.matched_fields,
                    reasons=dedupe_stable_reasons(existing_reason_tuples + reason_tuples),
                )

    # Collect all relations incident to any selected entity.
    relations_by_entity_id = _relations_by_entity_id(normalized_relations)
    selected_relations: list[Relation] = []
    selected_relation_keys: set[tuple[str, str, str]] = set()
    for entity_id in selected_entity_ids:
        for relation in relations_by_entity_id.get(entity_id, ()):
            relation_tuple = (
                relation.source_entity_id.value,
                relation.target_entity_id.value,
                relation.kind,
            )
            if relation_tuple in selected_relation_keys:
                continue
            selected_relation_keys.add(relation_tuple)
            selected_relations.append(relation)
            reasons_by_key[relation_key(relation)].append("incident to selected entity")

    selected_entities = [
        entity_by_id[entity_id] for entity_id in selected_entity_ids if entity_id in entity_by_id
    ]
    selected_relations = sorted(
        selected_relations,
        key=lambda relation: (
            relation.kind,
            relation.source_entity_id.value,
            relation.target_entity_id.value,
        ),
    )
    selected_relations = filter_related_relations(selected_relations, profile=resolved_profile)
    score_capped_reasons_by_key = _cap_reasons_per_item(
        reasons_by_key,
        max_reasons_per_item=resolved_profile.max_score_reasons_per_item,
    )

    (
        budgeted_entities,
        budgeted_relations,
        truncated,
    ) = _truncate_to_budget(
        task=task,
        budget_chars=budget_chars,
        selected_entities=selected_entities,
        selected_relations=selected_relations,
        reasons_by_key=score_capped_reasons_by_key,
        prefer_structural_relations=explain_ranking or resolved_profile.include_ranking_breakdown,
    )

    suggested_files = _suggested_files(budgeted_entities)
    uncertainties = _collect_uncertainties(
        selected_relations=budgeted_relations,
        entity_by_id=entity_by_id,
    )
    uncertainties = list(filter_uncertainties(uncertainties, profile=resolved_profile))
    citations = _build_citations(
        selected_entities=budgeted_entities,
        selected_relations=budgeted_relations,
        entity_by_id=entity_by_id,
    )
    citations = filter_source_citations(citations, profile=resolved_profile)
    semantic_components = filter_semantic_components(
        compact_component_labels(
            infer_semantic_components(entities=budgeted_entities, relations=budgeted_relations)
        ),
        profile=resolved_profile,
    )
    include_compact_reasons = explain_ranking or resolved_profile.include_compact_score_reasons
    why_selected = {}
    if include_compact_reasons:
        included_reason_keys = {
            *(entity.id.value for entity in budgeted_entities),
            *(relation_key(relation) for relation in budgeted_relations),
        }
        for key in sorted(included_reason_keys):
            reasons = score_capped_reasons_by_key.get(key, ())
            if not reasons:
                continue
            why_selected[key] = reasons
    include_ranking_breakdown = explain_ranking or resolved_profile.include_ranking_breakdown
    budgeted_breakdowns = _select_ranking_breakdowns(
        budgeted_entities=budgeted_entities,
        ranking_breakdowns_by_id=ranking_breakdowns_by_id,
        max_breakdowns=resolved_profile.max_ranking_breakdowns,
        max_reasons_per_item=resolved_profile.max_ranking_reasons_per_item,
    )

    return ContextPack(
        task=task,
        budget=budget_chars,
        selected_entities=tuple(budgeted_entities),
        selected_relations=tuple(budgeted_relations),
        source_citations=tuple(citations),
        why_selected=why_selected,
        ranking_breakdowns=budgeted_breakdowns if include_ranking_breakdown else {},
        semantic_components=semantic_components,
        uncertainties=tuple(uncertainties),
        suggested_files_to_inspect=tuple(suggested_files),
        forbidden_assumptions=_FORBIDDEN_ASSUMPTIONS,
        truncated=truncated,
    )


def _rank_entities(
    *,
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    inferred_components: Sequence[SemanticComponent],
    task_tokens: tuple[str, ...],
    is_code_task: bool,
    task_hints: set[str],
    public_api_entity_ids: set[str],
    export_source_entity_ids: set[str],
    export_target_entity_ids: set[str],
    source_roots: Sequence[str],
) -> list[tuple[Entity, RankingBreakdown]]:
    # Ranked by deterministic breakdown.total, then stable entity id.
    component_labels_by_entity = _component_labels_by_entity(inferred_components)
    relation_labels_by_entity = _relation_labels_by_entity(relations)
    bm25_index = _build_bm25_index(
        entities=entities,
        component_labels_by_entity=component_labels_by_entity,
        relation_labels_by_entity=relation_labels_by_entity,
    )
    ranked: list[tuple[Entity, RankingBreakdown]] = []
    for entity in entities:
        breakdown = _score_entity(
            entity,
            task_tokens,
            bm25_index=bm25_index,
            is_code_task=is_code_task,
            task_hints=task_hints,
            public_api_entity_ids=public_api_entity_ids,
            export_source_entity_ids=export_source_entity_ids,
            export_target_entity_ids=export_target_entity_ids,
            source_roots=source_roots,
        )
        if breakdown.total < 1:
            continue
        ranked.append((entity, breakdown))
    return sorted(ranked, key=lambda item: (-item[1].total, item[0].id.value))


def _score_entity(
    entity: Entity,
    task_tokens: tuple[str, ...],
    *,
    bm25_index: FieldedBM25Index,
    is_code_task: bool,
    task_hints: set[str],
    public_api_entity_ids: set[str],
    export_source_entity_ids: set[str],
    export_target_entity_ids: set[str],
    source_roots: Sequence[str],
) -> RankingBreakdown:
    name = entity.name.lower()
    qualified_name = entity.qualified_name.lower()
    source_path = entity.source_range.path.replace("\\", "/").lower()
    path_role = classify_path_role(path=source_path, source_roots=source_roots)
    entity_id = entity.id.value.lower()
    bm25_score = bm25_index.score(entity.id.value, task_tokens)
    lexical_score = bm25_score.score
    matched_terms: list[str] = list(bm25_score.matched_terms)
    matched_fields: list[str] = list(bm25_score.matched_fields)
    reasons: list[tuple[RankingCategory, str, float]] = []
    for matched_field in matched_fields:
        reasons.append(
            (
                "lexical",
                f'lexical match on {matched_field.replace("_", " ")} "{entity.qualified_name}"',
                0.0,
            )
        )

    exact_hits = sum(
        1
        for token in task_tokens
        if token == name or token == qualified_name or token == source_path or token == entity_id
    )
    lexical_score += exact_hits * _EXACT_FIELD_MATCH_BOOST
    if entity.source_range.path:
        lexical_score += _SOURCE_CITATION_BONUS

    component_score = 0
    if is_code_task:
        if entity.id.value.startswith("python:"):
            component_score += _AST_BACKED_BONUS
        if entity.kind in _CODE_ENTITY_KINDS:
            component_score += _CODE_ENTITY_KIND_BONUS
        if entity.kind in _COARSE_ENTITY_KINDS:
            component_score += _COARSE_ENTITY_PENALTY

    penalty_score = 0
    if is_generated_artifact_path(source_path):
        penalty_score += _GENERATED_ARTIFACT_PENALTY
        reasons.append(
            (
                "penalty",
                "generated/build artifact downrank",
                _GENERATED_ARTIFACT_PENALTY,
            )
        )

    path_role_score = 0
    task_intent_score = 0
    if "implementation" in task_hints and path_role == SOURCE_ROLE:
        path_role_score += _IMPLEMENTATION_PATH_ROLE_BONUS
        task_intent_score += _IMPLEMENTATION_TASK_INTENT_BONUS
        if (
            entity.kind in _IMPLEMENTATION_PRIORITIZED_ENTITY_KINDS
            # Must beat the citation-only lexical floor to count as task-relevant.
            and lexical_score > _SOURCE_CITATION_BONUS
        ):
            # Require lexical relevance beyond the default source-citation floor
            # so low-relevance source entities are not broadly boosted.
            component_score += _IMPLEMENTATION_SOURCE_ENTITY_KIND_BONUS
            reasons.append(
                (
                    "component",
                    "implementation task hint -> boosted source entity kind",
                    _IMPLEMENTATION_SOURCE_ENTITY_KIND_BONUS,
                )
            )
        reasons.append(
            (
                "path_role",
                "implementation task hint -> boosted source/package root",
                _IMPLEMENTATION_PATH_ROLE_BONUS,
            )
        )
        reasons.append(
            (
                "task_intent",
                "implementation task intent boost",
                _IMPLEMENTATION_TASK_INTENT_BONUS,
            )
        )

    if "tests" in task_hints and source_path.startswith("tests/"):
        if "implementation" in task_hints:
            path_role_score += _IMPLEMENTATION_TEST_SUPPORT_PATH_BONUS
            task_intent_score += _IMPLEMENTATION_TEST_SUPPORT_TASK_INTENT_BONUS
            reasons.append(
                (
                    "path_role",
                    'implementation + test task hints -> kept "tests/" as supporting context',
                    _IMPLEMENTATION_TEST_SUPPORT_PATH_BONUS,
                )
            )
            reasons.append(
                (
                    "task_intent",
                    "implementation + test task hints -> supporting test context boost",
                    _IMPLEMENTATION_TEST_SUPPORT_TASK_INTENT_BONUS,
                )
            )
        else:
            path_role_score += _TEST_PATH_ROLE_BONUS
            task_intent_score += _TEST_TASK_INTENT_BONUS
            reasons.append(
                ("path_role", 'test task hint -> boosted "tests/"', _TEST_PATH_ROLE_BONUS)
            )
            reasons.append(("task_intent", "test-like task intent boost", _TEST_TASK_INTENT_BONUS))

    if "public_api" in task_hints:
        if path_role == SOURCE_ROLE and source_path.endswith(".py"):
            path_role_score += _PUBLIC_API_SOURCE_PACKAGE_BONUS
            reasons.append(
                (
                    "path_role",
                    "public API task hint -> boosted source package/module path",
                    _PUBLIC_API_SOURCE_PACKAGE_BONUS,
                )
            )
        if source_path.endswith("/__init__.py") or source_path == "__init__.py":
            path_role_score += _PUBLIC_API_PATH_ROLE_BONUS
            task_intent_score += _PUBLIC_API_TASK_INTENT_BONUS
            reasons.append(
                (
                    "path_role",
                    'public API task hint -> boosted "__init__.py"',
                    _PUBLIC_API_PATH_ROLE_BONUS,
                )
            )
            reasons.append(
                (
                    "task_intent",
                    "public API task intent boost",
                    _PUBLIC_API_TASK_INTENT_BONUS,
                )
            )
        if entity.id.value in public_api_entity_ids:
            component_score += _PUBLIC_API_COMPONENT_BONUS
            task_intent_score += _PUBLIC_API_TASK_INTENT_BONUS
            reasons.append(
                (
                    "component",
                    "public API task hint -> boosted PublicAPI component entity",
                    _PUBLIC_API_COMPONENT_BONUS,
                )
            )
            reasons.append(
                (
                    "task_intent",
                    "public API task intent boost",
                    _PUBLIC_API_TASK_INTENT_BONUS,
                )
            )
        if entity.id.value in export_source_entity_ids:
            component_score += _PUBLIC_API_EXPORT_SOURCE_BONUS
            task_intent_score += _PUBLIC_API_TASK_INTENT_BONUS
            reasons.append(
                (
                    "component",
                    "public API task hint -> boosted explicit exports source",
                    _PUBLIC_API_EXPORT_SOURCE_BONUS,
                )
            )
            reasons.append(
                (
                    "task_intent",
                    "public API task intent boost",
                    _PUBLIC_API_TASK_INTENT_BONUS,
                )
            )
        if entity.id.value in export_target_entity_ids:
            component_score += _PUBLIC_API_EXPORT_TARGET_BONUS
            reasons.append(
                (
                    "component",
                    "public API task hint -> boosted explicit exports target",
                    _PUBLIC_API_EXPORT_TARGET_BONUS,
                )
            )
        if path_role == DOC_ROLE:
            penalty_score += _PUBLIC_API_DOC_DOWNRANK
            reasons.append(
                (
                    "penalty",
                    "public API task hint -> downranked docs/prose context",
                    _PUBLIC_API_DOC_DOWNRANK,
                )
            )
        if path_role == TOOL_ROLE:
            if source_path.startswith("tools/copilot/"):
                tooling_penalty = _PUBLIC_API_COPILOT_TOOLING_DOWNRANK
            else:
                tooling_penalty = _PUBLIC_API_TOOLING_DOWNRANK
            penalty_score += tooling_penalty
            reasons.append(
                (
                    "penalty",
                    "public API task hint -> downranked tooling context",
                    tooling_penalty,
                )
            )
        # Boost test files that test public imports (e.g. public_api_checks.py).
        # These are useful supporting evidence even when no explicit "tests" hint fires.
        _in_tests = "/tests/" in f"/{source_path}" or source_path.startswith("tests/")
        if _in_tests and entity.kind in {"module", "test", "function", "method"}:
            task_intent_score += _PUBLIC_API_IMPORT_TEST_BOOST
            reasons.append(
                (
                    "task_intent",
                    "public API task hint -> boosted public-import test",
                    _PUBLIC_API_IMPORT_TEST_BOOST,
                )
            )

    if lexical_score > 0:
        reasons.append(("lexical", "lexical baseline relevance", float(lexical_score)))

    graph_score = 0
    normalized_reasons = dedupe_stable_reasons(tuple(reasons))
    if not normalized_reasons and (
        lexical_score + path_role_score + task_intent_score + component_score + penalty_score > 0
    ):
        normalized_reasons = dedupe_stable_reasons(
            (("lexical", "lexical baseline relevance", 0.0),)
        )
    return build_breakdown(
        lexical=float(lexical_score),
        path_role=float(path_role_score),
        task_intent=float(task_intent_score),
        component=float(component_score),
        graph=float(graph_score),
        penalty=float(penalty_score),
        matched_terms=dedupe_stable(tuple(matched_terms)),
        matched_fields=dedupe_stable(tuple(matched_fields)),
        reasons=normalized_reasons,
    )


def _tokenize(text: str) -> tuple[str, ...]:
    return tokenize_text(text)


def _is_code_task(task_tokens: tuple[str, ...]) -> bool:
    return any(
        token in _CODE_TASK_TOKENS
        or token in _IMPLEMENTATION_TASK_TOKENS
        or any(token.endswith(suffix) for suffix in _CODE_PATH_SUFFIXES)
        for token in task_tokens
    )


def _task_hints(task_tokens: tuple[str, ...]) -> set[str]:
    hints: set[str] = set()
    # Token co-occurrence is sufficient; terms need not be adjacent.
    has_core_logic_phrase = _IMPLEMENTATION_CORE_LOGIC_TOKENS.issubset(task_tokens)
    if (
        any(
            token in _CODE_TASK_TOKENS or token in _IMPLEMENTATION_TASK_TOKENS
            for token in task_tokens
        )
        or has_core_logic_phrase
    ):
        hints.add("implementation")
    if any(token in _TEST_TASK_TOKENS for token in task_tokens):
        hints.add("tests")
    if any(token in _PUBLIC_API_TASK_TOKENS for token in task_tokens):
        hints.add("public_api")
    return hints


def dedupe_stable_reasons(
    raw_reasons: tuple[tuple[RankingCategory, str, float], ...],
) -> tuple[RankingReason, ...]:
    reasons: list[RankingReason] = []
    for category, message, score_delta in raw_reasons:
        append_reason(
            reasons,
            category=category,
            message=message,
            score_delta=score_delta,
        )
    deduped: dict[tuple[str, str, float], RankingReason] = {}
    for reason in reasons:
        key = (reason.category, reason.message, reason.score_delta)
        if key in deduped:
            continue
        deduped[key] = reason
    return tuple(deduped.values())


def _cap_reasons_per_item(
    reasons_by_key: dict[str, list[str]],
    *,
    max_reasons_per_item: int | None,
) -> dict[str, tuple[str, ...]]:
    capped_reasons: dict[str, tuple[str, ...]] = {}
    for key in sorted(reasons_by_key.keys()):
        unique_reasons = tuple(dict.fromkeys(reasons_by_key[key]))
        if max_reasons_per_item is None:
            capped_reasons[key] = unique_reasons
            continue
        capped_reasons[key] = unique_reasons[:max_reasons_per_item]
    return capped_reasons


def _select_ranking_breakdowns(
    *,
    budgeted_entities: Sequence[Entity],
    ranking_breakdowns_by_id: dict[str, RankingBreakdown],
    max_breakdowns: int | None,
    max_reasons_per_item: int | None,
) -> dict[str, RankingBreakdown]:
    selected_ids = [
        entity.id.value
        for entity in budgeted_entities
        if entity.id.value in ranking_breakdowns_by_id
    ]
    selected_ids = _prioritize_breakdown_ids(
        selected_ids,
        ranking_breakdowns_by_id=ranking_breakdowns_by_id,
    )
    if max_breakdowns is not None:
        selected_ids = selected_ids[:max_breakdowns]
    return {
        entity_id: _trim_ranking_breakdown(
            ranking_breakdowns_by_id[entity_id],
            max_reasons_per_item=max_reasons_per_item,
        )
        for entity_id in selected_ids
    }


def _prioritize_breakdown_ids(
    entity_ids: Sequence[str],
    *,
    ranking_breakdowns_by_id: dict[str, RankingBreakdown],
) -> list[str]:
    prioritized_ids: list[str] = []
    seen: set[str] = set()
    for predicate in (
        _has_graph_signal,
        _has_prioritized_breakdown_reason,
        lambda _breakdown: True,
    ):
        for entity_id in entity_ids:
            if entity_id in seen:
                continue
            breakdown = ranking_breakdowns_by_id[entity_id]
            if not predicate(breakdown):
                continue
            prioritized_ids.append(entity_id)
            seen.add(entity_id)
    return prioritized_ids


def _has_graph_signal(breakdown: RankingBreakdown) -> bool:
    return breakdown.graph > 0


def _has_prioritized_breakdown_reason(breakdown: RankingBreakdown) -> bool:
    return any(
        reason.category in _PRIORITIZED_BREAKDOWN_REASON_CATEGORIES for reason in breakdown.reasons
    )


def _trim_ranking_breakdown(
    breakdown: RankingBreakdown,
    *,
    max_reasons_per_item: int | None,
) -> RankingBreakdown:
    reasons = breakdown.reasons
    if max_reasons_per_item is not None and len(reasons) > max_reasons_per_item:
        ranked_reasons = sorted(
            enumerate(reasons),
            key=lambda enum_item: (
                _ranking_reason_priority(enum_item[1]),
                enum_item[0],
            ),
        )
        reasons = tuple(reason for _, reason in ranked_reasons[:max_reasons_per_item])
    return build_breakdown(
        lexical=breakdown.lexical,
        path_role=breakdown.path_role,
        task_intent=breakdown.task_intent,
        component=breakdown.component,
        graph=breakdown.graph,
        penalty=breakdown.penalty,
        matched_terms=breakdown.matched_terms,
        matched_fields=breakdown.matched_fields,
        reasons=reasons,
    )


def _ranking_reason_priority(reason: RankingReason) -> int:
    return _RANKING_REASON_PRIORITY.get(reason.category, _DEFAULT_RANKING_REASON_PRIORITY)


def _relations_by_entity_id(relations: Sequence[Relation]) -> dict[str, tuple[Relation, ...]]:
    grouped: dict[str, list[Relation]] = defaultdict(list)
    for relation in relations:
        grouped[relation.source_entity_id.value].append(relation)
        grouped[relation.target_entity_id.value].append(relation)
    return {key: tuple(value) for key, value in grouped.items()}


def _add_entity(entity_id: str, selected_ids: list[str], selected_set: set[str]) -> bool:
    """Add entity_id to selection; return True if newly added, False if already present."""
    if entity_id in selected_set:
        return False
    selected_ids.append(entity_id)
    selected_set.add(entity_id)
    return True


def _is_graph_seed_eligible(breakdown: RankingBreakdown) -> bool:
    """True when the entity has task-relevant signal beyond structural bonuses.

    The source-citation bonus (_SOURCE_CITATION_BONUS = 2, awarded to every entity
    with a source path) must NOT be the sole reason an entity is treated as a graph
    seed, or the seed set becomes the entire index and graph expansion produces no
    new neighbors.

    An entity qualifies as a seed when it has at least one of:
    - Lexical score above the citation-bonus floor (BM25 match or exact token hit)
    - A path-role boost (e.g. source/test/init file matched a task hint)
    - A task-intent boost (task hint matched this entity's role or component)
    """
    return (
        breakdown.lexical > _SOURCE_CITATION_BONUS
        or breakdown.path_role > 0
        or breakdown.task_intent > 0
    )


def _truncate_to_budget(
    *,
    task: str,
    budget_chars: int,
    selected_entities: Sequence[Entity],
    selected_relations: Sequence[Relation],
    reasons_by_key: Mapping[str, Sequence[str]],
    prefer_structural_relations: bool = False,
) -> tuple[list[Entity], list[Relation], bool]:
    # Reserve fixed space for markdown/yaml section scaffolding and uncertainty headings.
    used = len(task) + _PACK_FIXED_OVERHEAD_CHARS
    kept_entities: list[Entity] = []
    kept_entity_ids: set[str] = set()
    truncated = False

    for entity in selected_entities:
        estimate = _estimate_entity_chars(entity, reasons_by_key.get(entity.id.value, ()))
        if used + estimate > budget_chars:
            truncated = True
            break
        kept_entities.append(entity)
        kept_entity_ids.add(entity.id.value)
        used += estimate

    ordered_relations = sorted(
        selected_relations,
        key=lambda relation: _relation_budget_priority(
            relation,
            prefer_structural_relations=prefer_structural_relations,
        ),
    )
    kept_relations: list[Relation] = []
    for relation in ordered_relations:
        if (
            relation.source_entity_id.value not in kept_entity_ids
            and relation.target_entity_id.value not in kept_entity_ids
        ):
            continue
        estimate = _estimate_relation_chars(
            relation, reasons_by_key.get(relation_key(relation), ())
        )
        if used + estimate > budget_chars:
            truncated = True
            break
        kept_relations.append(relation)
        used += estimate

    return kept_entities, kept_relations, truncated


def _relation_budget_priority(
    relation: Relation,
    *,
    prefer_structural_relations: bool = False,
) -> tuple[int, str, str, str]:
    resolved = relation.metadata.get("resolved") is True
    if (
        not prefer_structural_relations
        and relation.kind in {"imports", "inherits"}
        and not resolved
    ):
        priority = 0
    elif prefer_structural_relations and relation.kind in {"tests", "exports"}:
        priority = 0
    elif prefer_structural_relations and relation.kind in {
        "contains",
        "calls",
        "uses",
        "owns",
        "requires",
    }:
        priority = 1
    elif prefer_structural_relations and relation.kind in {"documents", "violates"}:
        priority = 2
    elif prefer_structural_relations and relation.kind in {"imports", "inherits"} and resolved:
        priority = 3
    else:
        priority = 1 if not prefer_structural_relations else 4
    return (
        priority,
        relation.kind,
        relation.source_entity_id.value,
        relation.target_entity_id.value,
    )


def _estimate_entity_chars(entity: Entity, reasons: Sequence[str]) -> int:
    citation_len = len(entity.source_range.path) + _CITATION_RANGE_OVERHEAD_CHARS
    reason_len = sum(len(reason) for reason in reasons)
    return 40 + len(entity.qualified_name) + citation_len + reason_len


def _estimate_relation_chars(relation: Relation, reasons: Sequence[str]) -> int:
    reason_len = sum(len(reason) for reason in reasons)
    return (
        40
        + len(relation.kind)
        + len(relation.source_entity_id.value)
        + len(relation.target_entity_id.value)
        + reason_len
    )


def _suggested_files(entities: Sequence[Entity]) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    for entity in entities:
        path = entity.source_range.path.replace("\\", "/")
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _collect_uncertainties(
    *,
    selected_relations: Sequence[Relation],
    entity_by_id: dict[str, Entity],
) -> list[str]:
    uncertainties: set[str] = set()
    for relation in selected_relations:
        source_id = relation.source_entity_id.value
        target_id = relation.target_entity_id.value
        resolved = relation.metadata.get("resolved")
        if relation.kind in {"imports", "inherits"} and resolved is not True:
            uncertainties.add(f"Relation {relation.kind} {source_id} -> {target_id} is unresolved")
        if relation.kind == "tests" and relation.metadata.get("status") == "inferred":
            confidence = relation.metadata.get("confidence")
            if confidence == "low":
                uncertainties.add(
                    f"Relation tests {source_id} -> {target_id} is inferred with low confidence"
                )
        if target_id not in entity_by_id:
            uncertainties.add(f"Relation target not indexed in entities: {target_id}")
    return sorted(uncertainties)


def _build_citations(
    *,
    selected_entities: Sequence[Entity],
    selected_relations: Sequence[Relation],
    entity_by_id: dict[str, Entity],
) -> list[SourceCitation]:
    citations: list[SourceCitation] = []
    for entity in selected_entities:
        source = entity.source_range
        citations.append(
            SourceCitation(
                subject_kind="entity",
                subject_id=entity.id.value,
                path=source.path.replace("\\", "/"),
                start_line=source.start_line,
                end_line=source.end_line,
                start_col=source.start_col,
                end_col=source.end_col,
            )
        )
    for relation in selected_relations:
        if relation.evidence is not None:
            source = relation.evidence.source_range
            citations.append(
                SourceCitation(
                    subject_kind="relation",
                    subject_id=relation_key(relation),
                    path=source.path.replace("\\", "/"),
                    start_line=source.start_line,
                    end_line=source.end_line,
                    start_col=source.start_col,
                    end_col=source.end_col,
                    note=f"evidence:{relation.evidence.extractor}",
                )
            )
            continue
        source_entity = entity_by_id.get(relation.source_entity_id.value)
        if source_entity is None:
            continue
        source = source_entity.source_range
        citations.append(
            SourceCitation(
                subject_kind="relation",
                subject_id=relation_key(relation),
                path=source.path.replace("\\", "/"),
                start_line=source.start_line,
                end_line=source.end_line,
                start_col=source.start_col,
                end_col=source.end_col,
                note="derived_from_source_entity",
            )
        )
    return sorted(citations, key=lambda citation: (citation.subject_kind, citation.subject_id))


def _metadata_strings(value: JsonValue) -> list[str]:
    strings: list[str] = []
    _collect_metadata_strings(value, strings)
    return strings


def _collect_metadata_strings(value: JsonValue, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_metadata_strings(item, out)
        return
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            out.append(key)
            _collect_metadata_strings(item, out)


def _build_bm25_index(
    *,
    entities: Sequence[Entity],
    component_labels_by_entity: dict[str, tuple[str, ...]],
    relation_labels_by_entity: dict[str, tuple[str, ...]],
) -> FieldedBM25Index:
    documents = [
        FieldedDocument(
            doc_id=entity.id.value,
            fields={
                "id": entity.id.value,
                "name": entity.name,
                "qualified_name": entity.qualified_name,
                "source_path": entity.source_range.path.replace("\\", "/"),
                "kind": entity.kind,
                "semantic_components": " ".join(
                    component_labels_by_entity.get(entity.id.value, ())
                ),
                "relation_labels": " ".join(relation_labels_by_entity.get(entity.id.value, ())),
                "metadata": " ".join(_metadata_strings(entity.metadata)),
            },
        )
        for entity in sorted(entities, key=lambda item: item.id.value)
    ]
    return FieldedBM25Index(documents)


def _component_labels_by_entity(
    components: Sequence[SemanticComponent],
) -> dict[str, tuple[str, ...]]:
    labels_by_entity: dict[str, list[str]] = defaultdict(list)
    for component in components:
        entity_id = component.entity_id.value
        component_type = component.component_type
        status = component.status
        if not entity_id:
            continue
        labels_by_entity[entity_id].append(component_type)
        labels_by_entity[entity_id].append(status)
    return {
        entity_id: tuple(dict.fromkeys(labels))
        for entity_id, labels in sorted(labels_by_entity.items())
    }


def _relation_labels_by_entity(relations: Sequence[Relation]) -> dict[str, tuple[str, ...]]:
    labels_by_entity: dict[str, list[str]] = defaultdict(list)
    for relation in sorted(
        relations,
        key=lambda item: (item.kind, item.source_entity_id.value, item.target_entity_id.value),
    ):
        source_id = relation.source_entity_id.value
        target_id = relation.target_entity_id.value
        labels_by_entity[source_id].append(relation.kind)
        labels_by_entity[source_id].append(f"outgoing_{relation.kind}")
        labels_by_entity[target_id].append(relation.kind)
        labels_by_entity[target_id].append(f"incoming_{relation.kind}")
    return {
        entity_id: tuple(dict.fromkeys(labels))
        for entity_id, labels in sorted(labels_by_entity.items())
    }
