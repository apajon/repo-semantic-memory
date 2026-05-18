"""Deterministic lexical context pack builder."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from repo_semantic_memory.context.context_pack import ContextPack, SourceCitation, relation_key
from repo_semantic_memory.memory import compact_component_labels, infer_semantic_components
from repo_semantic_memory.model import Entity, JsonValue, Relation

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./:-]+")
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
    {"implementation", "source", "ownership", "component", "cleanup"}
)
_TEST_TASK_TOKENS = frozenset({"test", "tests", "behavior", "coverage", "pytest"})
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
_EXACT_TOKEN_WEIGHT = 12
_SUBSTRING_TOKEN_WEIGHT = 4
_SOURCE_CITATION_BONUS = 2
_AST_BACKED_BONUS = 10
_CODE_ENTITY_KIND_BONUS = 6
_COARSE_ENTITY_PENALTY = -6
_CITATION_RANGE_OVERHEAD_CHARS = 24
_IMPLEMENTATION_PATH_BONUS = 20
_TEST_PATH_BONUS = 20
_PUBLIC_API_HINT_BONUS = 24
_GENERATED_ARTIFACT_PENALTY = -80


def build_context_pack(
    *,
    task: str,
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    budget_chars: int,
) -> ContextPack:
    """Build a compact context pack for a task from indexed entities and relations."""
    if budget_chars < 1:
        raise ValueError("budget_chars must be >= 1")

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
    public_api_entity_ids = {
        component.entity_id.value
        for component in inferred_components
        if component.component_type == "PublicAPI"
    }

    ranked = _rank_entities(
        entities=normalized_entities,
        task_tokens=task_tokens,
        is_code_task=is_code_task,
        task_hints=task_hints,
        public_api_entity_ids=public_api_entity_ids,
    )

    selected_entity_ids: list[str] = []
    selected_entity_set: set[str] = set()
    reasons_by_key: dict[str, list[str]] = defaultdict(list)
    for entity, _, reasons in ranked:
        if reasons:
            _add_entity(entity.id.value, selected_entity_ids, selected_entity_set)
            reasons_by_key[entity.id.value].extend(reasons)

    if not selected_entity_ids and normalized_entities:
        fallback = normalized_entities[0]
        _add_entity(fallback.id.value, selected_entity_ids, selected_entity_set)
        reasons_by_key[fallback.id.value].append("fallback deterministic seed")

    relations_by_entity_id = _relations_by_entity_id(normalized_relations)
    selected_relations: list[Relation] = []
    selected_relation_keys: set[tuple[str, str, str]] = set()
    queue = list(selected_entity_ids)
    while queue:
        current_id = queue.pop(0)
        for relation in relations_by_entity_id.get(current_id, ()):
            relation_tuple = (
                relation.source_entity_id.value,
                relation.target_entity_id.value,
                relation.kind,
            )
            if relation_tuple in selected_relation_keys:
                continue
            selected_relation_keys.add(relation_tuple)
            selected_relations.append(relation)
            reasons_by_key[relation_key(relation)].append("direct graph neighbor")

            neighbor_id = _other_endpoint(current_id=current_id, relation=relation)
            neighbor = entity_by_id.get(neighbor_id)
            if neighbor is None or neighbor_id in selected_entity_set:
                continue
            _add_entity(neighbor_id, selected_entity_ids, selected_entity_set)
            reasons_by_key[neighbor_id].append(
                f"direct neighbor via {relation.kind} from {current_id}"
            )
            queue.append(neighbor_id)

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

    (
        budgeted_entities,
        budgeted_relations,
        truncated,
    ) = _truncate_to_budget(
        task=task,
        budget_chars=budget_chars,
        selected_entities=selected_entities,
        selected_relations=selected_relations,
        reasons_by_key=reasons_by_key,
    )

    suggested_files = _suggested_files(budgeted_entities)
    uncertainties = _collect_uncertainties(
        selected_relations=budgeted_relations,
        entity_by_id=entity_by_id,
    )
    citations = _build_citations(
        selected_entities=budgeted_entities,
        selected_relations=budgeted_relations,
        entity_by_id=entity_by_id,
    )
    semantic_components = compact_component_labels(
        infer_semantic_components(entities=budgeted_entities, relations=budgeted_relations)
    )
    why_selected = {
        key: tuple(dict.fromkeys(reasons_by_key[key]))
        for key in sorted(reasons_by_key.keys())
        if reasons_by_key[key]
    }

    return ContextPack(
        task=task,
        budget=budget_chars,
        selected_entities=tuple(budgeted_entities),
        selected_relations=tuple(budgeted_relations),
        source_citations=tuple(citations),
        why_selected=why_selected,
        semantic_components=semantic_components,
        uncertainties=tuple(uncertainties),
        suggested_files_to_inspect=tuple(suggested_files),
        forbidden_assumptions=_FORBIDDEN_ASSUMPTIONS,
        truncated=truncated,
    )


def _rank_entities(
    *,
    entities: Sequence[Entity],
    task_tokens: tuple[str, ...],
    is_code_task: bool,
    task_hints: set[str],
    public_api_entity_ids: set[str],
) -> list[tuple[Entity, int, tuple[str, ...]]]:
    ranked: list[tuple[Entity, int, tuple[str, ...]]] = []
    for entity in entities:
        score, reasons = _score_entity(
            entity,
            task_tokens,
            is_code_task=is_code_task,
            task_hints=task_hints,
            public_api_entity_ids=public_api_entity_ids,
        )
        if score < 1:
            continue
        ranked.append((entity, score, reasons))
    return sorted(ranked, key=lambda item: (-item[1], item[0].id.value))


def _score_entity(
    entity: Entity,
    task_tokens: tuple[str, ...],
    *,
    is_code_task: bool,
    task_hints: set[str],
    public_api_entity_ids: set[str],
) -> tuple[int, tuple[str, ...]]:
    name = entity.name.lower()
    qualified_name = entity.qualified_name.lower()
    source_path = entity.source_range.path.replace("\\", "/").lower()
    entity_id = entity.id.value.lower()
    metadata_strings = [value.lower() for value in _metadata_strings(entity.metadata)]
    haystacks = [name, qualified_name, source_path, entity_id, *metadata_strings]

    exact_hits = 0
    substring_hits = 0
    reasons: list[str] = []
    for token in task_tokens:
        if token in name:
            reasons.append(f'lexical match on name "{entity.name}"')
        elif token in qualified_name:
            reasons.append(f'lexical match on qualified name "{entity.qualified_name}"')
        elif token in source_path:
            reasons.append(f'lexical match on source path "{entity.source_range.path}"')
        elif token in entity_id:
            reasons.append(f'lexical match on id "{entity.id.value}"')
        elif any(token in value for value in metadata_strings):
            reasons.append(f'lexical match on metadata for "{entity.qualified_name}"')

        for haystack in haystacks:
            if not haystack:
                continue
            if token == haystack:
                exact_hits += 1
                break
            if token in haystack:
                substring_hits += 1
                break

    score = exact_hits * _EXACT_TOKEN_WEIGHT + substring_hits * _SUBSTRING_TOKEN_WEIGHT
    score += _SOURCE_CITATION_BONUS if entity.source_range.path else 0

    if is_code_task:
        if entity.id.value.startswith("python:"):
            score += _AST_BACKED_BONUS
        if entity.kind in _CODE_ENTITY_KINDS:
            score += _CODE_ENTITY_KIND_BONUS
        if entity.kind in _COARSE_ENTITY_KINDS:
            score += _COARSE_ENTITY_PENALTY

    if _is_generated_artifact_path(source_path):
        score += _GENERATED_ARTIFACT_PENALTY
        reasons.append("generated/build artifact downrank")

    if "implementation" in task_hints and source_path.startswith("src/"):
        score += _IMPLEMENTATION_PATH_BONUS
        reasons.append('implementation task hint -> boosted "src/"')

    if "tests" in task_hints and source_path.startswith("tests/"):
        score += _TEST_PATH_BONUS
        reasons.append('test task hint -> boosted "tests/"')

    if "public_api" in task_hints:
        if source_path.endswith("/__init__.py") or source_path == "__init__.py":
            score += _PUBLIC_API_HINT_BONUS
            reasons.append('public API task hint -> boosted "__init__.py"')
        if entity.id.value in public_api_entity_ids:
            score += _PUBLIC_API_HINT_BONUS
            reasons.append("public API task hint -> boosted PublicAPI component entity")

    if not reasons and score > 0:
        reasons.append("lexical baseline relevance")
    return score, tuple(dict.fromkeys(reasons))


def _tokenize(text: str) -> tuple[str, ...]:
    ordered_tokens = dict.fromkeys(token.lower() for token in _TOKEN_PATTERN.findall(text))
    return tuple(ordered_tokens.keys())


def _is_code_task(task_tokens: tuple[str, ...]) -> bool:
    return any(
        token in _CODE_TASK_TOKENS or any(token.endswith(suffix) for suffix in _CODE_PATH_SUFFIXES)
        for token in task_tokens
    )


def _task_hints(task_tokens: tuple[str, ...]) -> set[str]:
    hints: set[str] = set()
    if any(
        token in _CODE_TASK_TOKENS or token in _IMPLEMENTATION_TASK_TOKENS for token in task_tokens
    ):
        hints.add("implementation")
    if any(token in _TEST_TASK_TOKENS for token in task_tokens):
        hints.add("tests")
    if any(token in _PUBLIC_API_TASK_TOKENS for token in task_tokens):
        hints.add("public_api")
    return hints


def _is_generated_artifact_path(path: str) -> bool:
    generated_tokens = (
        "/docs/_build/",
        "/_build/",
        "/dist/",
        "/build/",
        "/htmlcov/",
        "/.pytest_cache/",
        "/.mypy_cache/",
        "/.ruff_cache/",
        ".egg-info/",
    )
    normalized = f"/{path.strip('/')}/"
    return any(token in normalized for token in generated_tokens)


def _relations_by_entity_id(relations: Sequence[Relation]) -> dict[str, tuple[Relation, ...]]:
    grouped: dict[str, list[Relation]] = defaultdict(list)
    for relation in relations:
        grouped[relation.source_entity_id.value].append(relation)
        grouped[relation.target_entity_id.value].append(relation)
    return {key: tuple(value) for key, value in grouped.items()}


def _other_endpoint(*, current_id: str, relation: Relation) -> str:
    source = relation.source_entity_id.value
    target = relation.target_entity_id.value
    return target if source == current_id else source


def _add_entity(entity_id: str, selected_ids: list[str], selected_set: set[str]) -> None:
    if entity_id in selected_set:
        return
    selected_ids.append(entity_id)
    selected_set.add(entity_id)


def _truncate_to_budget(
    *,
    task: str,
    budget_chars: int,
    selected_entities: Sequence[Entity],
    selected_relations: Sequence[Relation],
    reasons_by_key: dict[str, list[str]],
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

    ordered_relations = sorted(selected_relations, key=_relation_budget_priority)
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


def _relation_budget_priority(relation: Relation) -> tuple[int, str, str, str]:
    resolved = relation.metadata.get("resolved") is True
    unresolved_import_or_inherits = relation.kind in {"imports", "inherits"} and not resolved
    priority = 0 if unresolved_import_or_inherits else 1
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
