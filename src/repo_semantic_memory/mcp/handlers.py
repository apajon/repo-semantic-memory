"""Pure deterministic MCP-style handlers over existing local core logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from repo_semantic_memory.context import (
    build_context_pack,
    render_context_pack_markdown,
    resolve_profile,
)
from repo_semantic_memory.context.bm25 import (
    BM25Score,
    FieldedBM25Index,
    FieldedDocument,
    tokenize_text,
)
from repo_semantic_memory.context.context_pack import relation_key
from repo_semantic_memory.context.graph_selection import (
    GraphSelectionConfig,
    select_graph_neighbors,
)
from repo_semantic_memory.context.path_roles import classify_path_role, infer_source_roots
from repo_semantic_memory.exporters.ai_directory import AiDirectoryExporter
from repo_semantic_memory.extractors.git_history import get_git_repository_summary
from repo_semantic_memory.mcp.tools import (
    BudgetEnvelope,
    BuildContextPackRequest,
    BuildContextPackResponse,
    Citation,
    ExplainEntityRequest,
    ExplainEntityResponse,
    ExportAiMemoryRequest,
    ExportAiMemoryResponse,
    GetGitSummaryRequest,
    GetGitSummaryResponse,
    McpToolName,
    QueryGraphRequest,
    QueryGraphResponse,
    SearchSymbolsRequest,
    SearchSymbolsResponse,
    Uncertainty,
    ValidatePatchContextRequest,
    ValidatePatchContextResponse,
)
from repo_semantic_memory.memory import infer_semantic_components
from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.store import SQLiteStore

_MAX_SEARCH_LIMIT = 100
_MAX_GRAPH_DEPTH = 3
_MAX_GRAPH_ENTITIES = 100
_MAX_CONTEXT_BUDGET = 20_000
_MAX_DIRECT_RELATIONS = 10

# Short, stable instructions included in every agent-facing MCP result.
# Agents should print these fields verbatim before summarizing tool output.
_AGENT_INSTRUCTIONS: tuple[str, ...] = (
    "Use only paths listed in this response.",
    "Do not infer missing paths, symbols, or class names.",
    "Verify edits against cited source ranges.",
)

# Instructions used specifically for ``rsm_build_context_pack`` results. The
# third instruction encourages progressive disclosure via the focused
# ``rsm_explain_entity`` tool rather than re-fetching the full pack with
# rendered output.
_CONTEXT_PACK_AGENT_INSTRUCTIONS: tuple[str, ...] = (
    "Use only paths listed in this response.",
    "Do not infer missing paths, symbols, or class names.",
    "Call rsm_explain_entity for details about a selected entity.",
)


def _compact_entity_dict(item: object) -> dict[str, object]:
    """Flatten a ``selected_entities`` payload entry to a compact MCP shape.

    The full payload dict produced by :meth:`ContextPack.to_dict` nests
    ``source_range`` under each entity. Agents consuming compact MCP results
    expect ``path``/``start_line``/``end_line`` at the top level and a stable
    ``entity_id`` key matching :class:`Entity` IDs surfaced by other tools.
    """

    if not isinstance(item, dict):
        return {}
    source_range = item.get("source_range") if isinstance(item.get("source_range"), dict) else {}
    assert isinstance(source_range, dict)  # for type narrowing
    compact: dict[str, object] = {
        "entity_id": item.get("id"),
        "kind": item.get("kind"),
        "name": item.get("name"),
        "qualified_name": item.get("qualified_name"),
        "path": source_range.get("path"),
        "start_line": source_range.get("start_line"),
        "end_line": source_range.get("end_line"),
    }
    return compact


def _compact_relation_dict(item: object) -> dict[str, object]:
    """Flatten a ``selected_relations`` payload entry to a compact MCP shape."""

    if not isinstance(item, dict):
        return {}
    return {
        "kind": item.get("kind"),
        "source_entity_id": item.get("source_entity_id"),
        "target_entity_id": item.get("target_entity_id"),
    }


def handle_search_symbols(
    request: SearchSymbolsRequest,
    *,
    repo_root: Path | str | None = None,
    require_db_inside_repo: bool = True,
) -> SearchSymbolsResponse:
    entities, relations = _load_index(
        request.db_path, repo_root=repo_root, require_db_inside_repo=require_db_inside_repo
    )
    source_roots = infer_source_roots(entities)

    kind_filter = set(request.entity_kinds)
    role_filter = set(request.path_roles)
    filtered_entities = [
        entity
        for entity in entities
        if (not kind_filter or entity.kind in kind_filter)
        and (
            not role_filter
            or classify_path_role(path=entity.source_range.path, source_roots=source_roots)
            in role_filter
        )
    ]

    relation_labels_by_entity: dict[str, list[str]] = {}
    if request.include_relations:
        for relation in relations:
            relation_labels_by_entity.setdefault(relation.source_entity_id.value, []).append(
                relation.kind
            )
            relation_labels_by_entity.setdefault(relation.target_entity_id.value, []).append(
                relation.kind
            )

    documents = [
        FieldedDocument(
            doc_id=entity.id.value,
            fields={
                "id": entity.id.value,
                "kind": entity.kind,
                "name": entity.name,
                "qualified_name": entity.qualified_name,
                "source_path": entity.source_range.path,
                "metadata": json.dumps(entity.metadata, sort_keys=True, separators=(",", ":")),
                "relation_labels": " ".join(
                    sorted(relation_labels_by_entity.get(entity.id.value, []))
                ),
                "semantic_components": "",
            },
        )
        for entity in filtered_entities
    ]
    index = FieldedBM25Index(documents)
    tokens = tokenize_text(request.query)

    uncertainties: list[Uncertainty] = []
    if not tokens:
        uncertainties.append(
            Uncertainty(
                code="empty_query_tokens",
                message="Query contains no searchable tokens after normalization.",
            )
        )
        return SearchSymbolsResponse(
            matches=(),
            results=(),
            citations=(),
            uncertainties=tuple(uncertainties),
            budget=BudgetEnvelope(requested_chars=1, used_chars=0, truncated=False),
        )

    scored: list[tuple[float, str, Entity, BM25Score]] = []
    for entity in filtered_entities:
        score = index.score(entity.id.value, tokens)
        if score.score <= 0:
            continue
        scored.append((score.score, entity.id.value, entity, score))
    scored.sort(key=lambda item: (-item[0], item[1]))

    bounded_limit = min(request.limit, _MAX_SEARCH_LIMIT)
    if request.limit > _MAX_SEARCH_LIMIT:
        uncertainties.append(
            Uncertainty(
                code="search_limit_capped",
                message=(
                    f"Requested limit {request.limit} exceeds max {_MAX_SEARCH_LIMIT}; "
                    "results capped."
                ),
            )
        )
    if len(scored) > bounded_limit:
        uncertainties.append(
            Uncertainty(
                code="search_results_truncated",
                message="Results were truncated by the requested limit.",
            )
        )

    results: list[dict[str, object]] = []
    matches: list[str] = []
    citations: list[Citation] = []
    for _, _entity_id, entity_obj, score_obj in scored[:bounded_limit]:
        entity = entity_obj
        score = score_obj
        result: dict[str, object] = {
            "entity_id": entity.id.value,
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "kind": entity.kind,
            "path": entity.source_range.path,
            "start_line": entity.source_range.start_line,
            "end_line": entity.source_range.end_line,
            "score": score.score,
            "source_range": {
                "path": entity.source_range.path,
                "start_line": entity.source_range.start_line,
                "end_line": entity.source_range.end_line,
                "start_col": entity.source_range.start_col,
                "end_col": entity.source_range.end_col,
            },
            "path_role": classify_path_role(
                path=entity.source_range.path, source_roots=source_roots
            ),
            "ranking_reasons": [
                f"score={score.score:.6f}",
                f"matched_terms={','.join(score.matched_terms)}",
                f"matched_fields={','.join(score.matched_fields)}",
            ],
        }
        if request.include_relations:
            direct_relations = _direct_relations_for_entity(entity.id.value, relations)
            result["direct_relations"] = direct_relations
        results.append(result)
        matches.append(entity.id.value)
        citations.append(_entity_citation(entity.id.value, entity))

    used_chars = len(json.dumps(results, sort_keys=True, separators=(",", ":")))
    return SearchSymbolsResponse(
        matches=tuple(matches),
        results=tuple(results),
        citations=tuple(citations),
        uncertainties=tuple(uncertainties),
        agent_instructions=_AGENT_INSTRUCTIONS,
        budget=BudgetEnvelope(
            requested_chars=max(1, used_chars),
            used_chars=used_chars,
            truncated=len(scored) > bounded_limit,
        ),
    )


def handle_explain_entity(
    request: ExplainEntityRequest,
    *,
    repo_root: Path | str | None = None,
    require_db_inside_repo: bool = True,
) -> ExplainEntityResponse:
    entities, relations = _load_index(
        request.db_path, repo_root=repo_root, require_db_inside_repo=require_db_inside_repo
    )
    entity_by_id = {entity.id.value: entity for entity in entities}
    target = entity_by_id.get(request.entity_id)
    if target is None:
        return ExplainEntityResponse(
            entity_id=request.entity_id,
            uncertainties=(
                Uncertainty(
                    code="entity_not_found",
                    message="Requested entity ID is not present in the index.",
                    subject_id=request.entity_id,
                    recoverable=True,
                ),
            ),
        )

    relation_rows: list[dict[str, object]] = []
    related_ids: set[str] = set()
    uncertainties: list[Uncertainty] = []
    for relation in relations:
        is_outgoing = relation.source_entity_id.value == request.entity_id
        is_incoming = relation.target_entity_id.value == request.entity_id
        if is_outgoing and not request.include_outgoing_relations:
            continue
        if is_incoming and not request.include_incoming_relations:
            continue
        if not is_incoming and not is_outgoing:
            continue
        related_id = (
            relation.target_entity_id.value if is_outgoing else relation.source_entity_id.value
        )
        related_ids.add(related_id)
        relation_rows.append(
            {
                "kind": relation.kind,
                "source_entity_id": relation.source_entity_id.value,
                "target_entity_id": relation.target_entity_id.value,
                "metadata": dict(sorted(relation.metadata.items())),
                "evidence": relation.evidence.to_dict() if relation.evidence is not None else None,
            }
        )
        if relation.evidence is None:
            uncertainties.append(
                Uncertainty(
                    code="relation_without_evidence",
                    message="Relation has no direct evidence payload.",
                    subject_id=relation_key(relation),
                )
            )

    components_payload: list[dict[str, object]] = []
    if request.include_components:
        for component in infer_semantic_components(entities=entities, relations=relations):
            if component.entity_id.value != request.entity_id:
                continue
            components_payload.append(component.to_dict())
            if component.status != "confirmed":
                uncertainties.append(
                    Uncertainty(
                        code="inferred_component",
                        message=(
                            "Semantic component is inferred and should be treated as uncertain."
                        ),
                        subject_id=component.entity_id.value,
                    )
                )

    if not request.include_claims:
        relation_rows = [
            row for row in relation_rows if row.get("kind") not in {"violates", "requires"}
        ]

    relation_rows.sort(
        key=lambda row: (
            str(row["kind"]),
            str(row["source_entity_id"]),
            str(row["target_entity_id"]),
        )
    )
    components_payload.sort(
        key=lambda item: (
            str(item.get("component_type", "")),
            str(item.get("status", "")),
        )
    )

    citations = [_entity_citation(target.id.value, target)]
    citations.extend(_relation_citations(relation_rows))

    return ExplainEntityResponse(
        entity_id=request.entity_id,
        entity=_entity_payload(target),
        relations=tuple(relation_rows),
        semantic_components=tuple(components_payload),
        related_entity_ids=tuple(sorted(related_ids)),
        citations=tuple(citations),
        uncertainties=tuple(_dedupe_uncertainties(uncertainties)),
    )


def handle_build_context_pack(
    request: BuildContextPackRequest,
    *,
    repo_root: Path | str | None = None,
    require_db_inside_repo: bool = True,
) -> BuildContextPackResponse:
    entities, relations = _load_index(
        request.db_path, repo_root=repo_root, require_db_inside_repo=require_db_inside_repo
    )
    bounded_budget = min(request.budget_chars, _MAX_CONTEXT_BUDGET)
    uncertainties: list[Uncertainty] = []
    if request.budget_chars > _MAX_CONTEXT_BUDGET:
        uncertainties.append(
            Uncertainty(
                code="budget_capped",
                message=(
                    f"Requested budget {request.budget_chars} exceeded max {_MAX_CONTEXT_BUDGET}."
                ),
            )
        )

    profile = resolve_profile(request.profile)
    include_ranking = request.explain_ranking or profile.include_ranking_breakdown
    pack = build_context_pack(
        task=request.task,
        entities=entities,
        relations=relations,
        budget_chars=bounded_budget,
        explain_ranking=include_ranking,
        profile=profile,
    )

    full_payload = pack.to_dict(include_ranking=include_ranking)
    if not request.include_semantic_components:
        full_payload["semantic_components"] = []

    # Render only when explicitly requested. Default MCP output stays compact
    # and avoids large Markdown/YAML payloads that clients spill into
    # temporary content files.
    if request.include_rendered:
        if request.format == "markdown":
            rendered = render_context_pack_markdown(pack, explain_ranking=include_ranking)
        else:
            rendered = pack.to_yaml(include_ranking=include_ranking)
    else:
        rendered = ""

    # Decide which payload variant to expose. ``include_ranking_breakdowns``
    # gates the heaviest extra field. If neither full payload nor ranking
    # details are requested, expose an empty dict to keep the response shape
    # stable while signaling omission via ``omitted_sections``.
    if request.include_payload:
        payload_out: dict[str, object] = dict(full_payload)
        if not request.include_ranking_breakdowns:
            payload_out.pop("ranking_breakdowns", None)
    elif request.include_ranking_breakdowns and "ranking_breakdowns" in full_payload:
        payload_out = {"ranking_breakdowns": full_payload["ranking_breakdowns"]}
    else:
        payload_out = {}

    raw_citations = tuple(
        Citation(
            subject_kind=_normalize_subject_kind(citation.subject_kind),
            subject_id=citation.subject_id,
            path=citation.path,
            start_line=citation.start_line,
            end_line=citation.end_line,
            start_col=citation.start_col,
            end_col=citation.end_col,
            note=citation.note,
        )
        for citation in pack.source_citations
    )
    uncertainties.extend(
        Uncertainty(code="context_uncertainty", message=item, recoverable=True)
        for item in pack.uncertainties
    )

    # Budget accounting reflects rendered output when produced; the compact
    # response is intentionally small and reported as 0 used chars so that
    # ``budget_capped`` uncertainties remain the sole signal for over-budget
    # requests.
    used_chars = len(rendered)
    # Derive selected_files from suggested_files_to_inspect when available,
    # falling back to the source paths of selected entities.
    if pack.suggested_files_to_inspect:
        selected_files: tuple[str, ...] = tuple(sorted(set(pack.suggested_files_to_inspect)))
    else:
        selected_files = tuple(
            sorted({entity.source_range.path for entity in pack.selected_entities})
        )

    # Serialize selected entities and relations as agent-readable dicts using
    # the compact, flattened shape. Bound them by ``max_entities`` and
    # ``max_relations`` so MCP responses stay small by default.
    raw_entities = full_payload.get("selected_entities")
    if isinstance(raw_entities, list):
        compact_entities = tuple(_compact_entity_dict(item) for item in raw_entities)
    else:
        compact_entities = ()
    selected_entities = compact_entities[: request.max_entities]

    raw_relations = full_payload.get("selected_relations")
    if isinstance(raw_relations, list):
        compact_relations = tuple(_compact_relation_dict(item) for item in raw_relations)
    else:
        compact_relations = ()
    selected_relations = compact_relations[: request.max_relations]

    citations = raw_citations[: request.max_citations]

    omitted: list[str] = []
    if not request.include_rendered:
        omitted.append("rendered")
    if not request.include_payload:
        omitted.append("payload")
    if not request.include_ranking_breakdowns:
        omitted.append("ranking_breakdowns")

    how_to_get_more: tuple[str, ...] = (
        "Call rsm_build_context_pack with include_rendered=true for Markdown output.",
        "Call rsm_build_context_pack with include_payload=true for the full payload.",
        "Call rsm_build_context_pack with include_ranking_breakdowns=true for ranking details.",
        "Call rsm_explain_entity with an entity_id for focused details.",
    )

    truncated_flag = pack.truncated or request.budget_chars > _MAX_CONTEXT_BUDGET
    return BuildContextPackResponse(
        rendered=rendered,
        payload=payload_out,
        selected_entity_ids=tuple(entity.id.value for entity in pack.selected_entities),
        selected_relation_keys=tuple(relation_key(item) for item in pack.selected_relations),
        citations=citations,
        uncertainties=tuple(_dedupe_uncertainties(uncertainties)),
        budget=BudgetEnvelope(
            requested_chars=request.budget_chars,
            used_chars=min(used_chars, request.budget_chars),
            truncated=truncated_flag,
        ),
        selected_files=selected_files,
        selected_entities=selected_entities,
        selected_relations=selected_relations,
        agent_instructions=_CONTEXT_PACK_AGENT_INSTRUCTIONS,
        truncated=truncated_flag,
        omitted_sections=tuple(omitted),
        how_to_get_more=how_to_get_more,
    )


def handle_query_graph(
    request: QueryGraphRequest,
    *,
    repo_root: Path | str | None = None,
    require_db_inside_repo: bool = True,
) -> QueryGraphResponse:
    entities, relations = _load_index(
        request.db_path, repo_root=repo_root, require_db_inside_repo=require_db_inside_repo
    )
    entity_by_id = {entity.id.value: entity for entity in entities}
    known_ids = frozenset(entity_by_id.keys())

    uncertainties: list[Uncertainty] = []
    missing_seed_ids = sorted(
        entity_id for entity_id in request.entity_ids if entity_id not in known_ids
    )
    for missing in missing_seed_ids:
        uncertainties.append(
            Uncertainty(
                code="missing_seed_entity",
                message="Seed entity ID is not present in the current index.",
                subject_id=missing,
            )
        )

    seeds = tuple(sorted(entity_id for entity_id in request.entity_ids if entity_id in known_ids))
    if not seeds:
        return QueryGraphResponse(
            uncertainties=tuple(uncertainties),
            budget=BudgetEnvelope(requested_chars=1, used_chars=0, truncated=False),
        )

    max_depth = min(request.max_hops, _MAX_GRAPH_DEPTH)
    max_entities = min(request.limit, _MAX_GRAPH_ENTITIES)
    if request.max_hops > _MAX_GRAPH_DEPTH:
        uncertainties.append(
            Uncertainty(
                code="graph_depth_capped",
                message=f"Requested max_hops {request.max_hops} exceeded max {_MAX_GRAPH_DEPTH}.",
            )
        )
    if request.limit > _MAX_GRAPH_ENTITIES:
        uncertainties.append(
            Uncertainty(
                code="graph_entity_limit_capped",
                message=f"Requested limit {request.limit} exceeded max {_MAX_GRAPH_ENTITIES}.",
            )
        )

    graph_result = select_graph_neighbors(
        seed_ids=seeds,
        entity_id_set=known_ids,
        relations=relations,
        config=GraphSelectionConfig(
            max_depth=max_depth,
            max_entities=max_entities,
            direction=request.direction,
            kind_filters=frozenset(request.relation_kinds),
        ),
        exclude_ids=frozenset(seeds),
    )

    selected_ids = tuple(sorted(set(seeds) | set(graph_result.selected_ids)))
    selected_set = set(selected_ids)
    selected_relations = [
        relation
        for relation in relations
        if relation.source_entity_id.value in selected_set
        and relation.target_entity_id.value in selected_set
        and (not request.relation_kinds or relation.kind in request.relation_kinds)
    ]
    selected_relations.sort(
        key=lambda relation: (
            relation.kind,
            relation.source_entity_id.value,
            relation.target_entity_id.value,
        )
    )

    for uncertain_id in sorted(graph_result.uncertainty_ids):
        uncertainties.append(
            Uncertainty(
                code="unresolved_graph_neighbor",
                message="Graph neighbor reached via unresolved relation metadata.",
                subject_id=uncertain_id,
            )
        )

    entity_payloads = tuple(_entity_payload(entity_by_id[entity_id]) for entity_id in selected_ids)
    relation_payloads: tuple[dict[str, object], ...] = tuple(
        {
            "kind": relation.kind,
            "source_entity_id": relation.source_entity_id.value,
            "target_entity_id": relation.target_entity_id.value,
            "metadata": dict(sorted(relation.metadata.items())),
            "evidence": relation.evidence.to_dict() if relation.evidence is not None else None,
        }
        for relation in selected_relations
    )
    citations = [_entity_citation(entity_id, entity_by_id[entity_id]) for entity_id in selected_ids]
    citations.extend(_relation_citations(relation_payloads))

    used_chars = len(
        json.dumps(
            {
                "entities": entity_payloads,
                "relations": relation_payloads,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return QueryGraphResponse(
        entity_ids=selected_ids,
        entities=entity_payloads,
        relations=relation_payloads,
        relation_keys=tuple(relation_key(item) for item in selected_relations),
        citations=tuple(citations),
        uncertainties=tuple(_dedupe_uncertainties(uncertainties)),
        budget=BudgetEnvelope(
            requested_chars=max(1, used_chars),
            used_chars=used_chars,
            truncated=len(graph_result.selected_ids) >= max_entities,
        ),
    )


def handle_export_ai_memory(
    request: ExportAiMemoryRequest,
    *,
    repo_root: Path | str | None = None,
) -> ExportAiMemoryResponse:
    entities, relations = _load_index(request.db_path, repo_root=repo_root)
    db_path = _resolve_bounded_path(
        request.db_path, repo_root=repo_root, must_exist=True, label="db_path"
    )
    output_dir = _resolve_bounded_path(
        request.output_dir,
        repo_root=repo_root,
        must_exist=False,
        label="output_dir",
    )

    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = store.get_metadata()
    finally:
        store.close()

    exporter = AiDirectoryExporter(
        db_path=db_path,
        output_dir=output_dir,
        entities=entities,
        relations=relations,
        metadata=metadata,
    )
    result = exporter.export(force=request.force)

    warnings: list[str] = []
    if result.files_skipped:
        warnings.append("Some files already existed and were skipped.")
    return ExportAiMemoryResponse(
        files_written=result.files_written,
        files_skipped=result.files_skipped,
        entity_count=result.entity_count,
        relation_count=result.relation_count,
        component_count=result.component_count,
        invariant_count=result.invariant_count,
        warnings=tuple(warnings),
    )


def handle_validate_patch_context(
    request: ValidatePatchContextRequest,
    *,
    repo_root: Path | str | None = None,
    require_db_inside_repo: bool = True,
) -> ValidatePatchContextResponse:
    entities, _relations = _load_index(
        request.db_path, repo_root=repo_root, require_db_inside_repo=require_db_inside_repo
    )

    changed_paths = tuple(_normalize_changed_path(path) for path in request.changed_paths)
    referenced_ids = tuple(sorted(set(request.referenced_entity_ids)))

    entity_by_id = {entity.id.value: entity for entity in entities}
    entities_by_path: dict[str, list[str]] = {}
    for entity in entities:
        path = entity.source_range.path.replace("\\", "/")
        entities_by_path.setdefault(path, []).append(entity.id.value)

    covered_paths: list[str] = []
    missing_paths: list[str] = []
    covered_entity_ids: set[str] = set()
    missing_entity_ids: set[str] = set()
    uncertainties: list[Uncertainty] = []

    referenced_set = set(referenced_ids)
    for changed_path in changed_paths:
        path_entity_ids = set(entities_by_path.get(changed_path, []))
        if not path_entity_ids:
            missing_paths.append(changed_path)
            uncertainties.append(
                Uncertainty(
                    code="path_not_indexed",
                    message="Changed path was not found in indexed entities.",
                    subject_id=changed_path,
                )
            )
            continue
        overlap = sorted(path_entity_ids & referenced_set)
        if overlap:
            covered_paths.append(changed_path)
            covered_entity_ids.update(overlap)
        else:
            missing_paths.append(changed_path)
            missing_entity_ids.update(path_entity_ids)

    invalid_references = sorted(
        entity_id for entity_id in referenced_ids if entity_id not in entity_by_id
    )
    for missing in invalid_references:
        uncertainties.append(
            Uncertainty(
                code="referenced_entity_missing",
                message="Referenced entity ID is not present in the index.",
                subject_id=missing,
            )
        )

    suggested_query: str | None = None
    suggested_tools: tuple[McpToolName, ...] = ()
    if missing_paths:
        path_terms = " ".join(sorted(set(missing_paths)))
        suggested_query = f"{request.task} {path_terms}".strip()
        suggested_tools = ("build_context_pack", "search_symbols")

    used_chars = len(suggested_query) if suggested_query is not None else 0
    requested_budget = (
        request.budget_chars if request.budget_chars is not None else max(1, used_chars)
    )

    return ValidatePatchContextResponse(
        covered_paths=tuple(sorted(set(covered_paths))),
        missing_paths=tuple(sorted(set(missing_paths))),
        covered_entity_ids=tuple(sorted(covered_entity_ids)),
        missing_entity_ids=tuple(sorted(missing_entity_ids)),
        suggested_context_query=suggested_query,
        suggested_follow_up_tools=suggested_tools,
        uncertainties=tuple(_dedupe_uncertainties(uncertainties)),
        budget=BudgetEnvelope(
            requested_chars=max(1, requested_budget),
            used_chars=min(used_chars, max(1, requested_budget)),
            truncated=used_chars > max(1, requested_budget),
        ),
    )


def handle_get_git_summary(
    request: GetGitSummaryRequest,
    *,
    repo_root: Path | str | None = None,
) -> GetGitSummaryResponse:
    target_path = _resolve_bounded_path(
        request.path, repo_root=repo_root, must_exist=True, label="path"
    )
    summary = get_git_repository_summary(target_path)

    uncertainties: list[Uncertainty] = []
    if not summary.in_git_repo:
        uncertainties.append(
            Uncertainty(
                code="not_in_git_repo",
                message=summary.unavailable_reason or "Path is not inside a Git repository.",
                recoverable=True,
            )
        )

    citation = Citation(
        subject_kind="git_summary",
        subject_id=summary.repository_root or summary.path,
        path=summary.path,
        start_line=1,
        end_line=1,
        note="Repository-level Git summary (no source range).",
    )
    return GetGitSummaryResponse(
        repository_root=summary.repository_root,
        branch=None,
        head_commit=summary.current_commit,
        dirty=bool(summary.is_dirty),
        citations=(citation,),
        uncertainties=tuple(_dedupe_uncertainties(uncertainties)),
    )


def _load_index(
    db_path: str,
    *,
    repo_root: Path | str | None,
    require_db_inside_repo: bool = True,
) -> tuple[list[Entity], list[Relation]]:
    # When `require_db_inside_repo=False` the DB lives outside the repo root
    # (e.g. Index Store mode where DBs are stored under RSM_HOME).  Pass
    # `repo_root=None` so `_resolve_bounded_path` skips the containment
    # check while still resolving and existence-checking the path.
    bounds_root = repo_root if require_db_inside_repo else None
    resolved_db = _resolve_bounded_path(
        db_path, repo_root=bounds_root, must_exist=True, label="db_path"
    )
    store = SQLiteStore(resolved_db)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
    finally:
        store.close()
    return entities, relations


def _resolve_bounded_path(
    path_value: str | None,
    *,
    repo_root: Path | str | None,
    must_exist: bool,
    label: str,
) -> Path:
    if path_value is None or not path_value.strip():
        raise ValueError(f"{label} must be provided")

    base = Path(repo_root).resolve() if repo_root is not None else None
    candidate = Path(path_value)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (base / candidate).resolve()
        if base
        else candidate.resolve()
    )

    if base is not None:
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"{label} must stay within repo_root") from exc
    if must_exist and not resolved.exists():
        raise ValueError(f"{label} does not exist: {resolved}")
    return resolved


def _entity_payload(entity: Entity) -> dict[str, object]:
    return {
        "entity_id": entity.id.value,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "kind": entity.kind,
        "metadata": dict(sorted(entity.metadata.items())),
        "source_range": {
            "path": entity.source_range.path,
            "start_line": entity.source_range.start_line,
            "end_line": entity.source_range.end_line,
            "start_col": entity.source_range.start_col,
            "end_col": entity.source_range.end_col,
        },
    }


def _entity_citation(subject_id: str, entity: Entity) -> Citation:
    return Citation(
        subject_kind="entity",
        subject_id=subject_id,
        path=entity.source_range.path,
        start_line=entity.source_range.start_line,
        end_line=entity.source_range.end_line,
        start_col=entity.source_range.start_col,
        end_col=entity.source_range.end_col,
    )


def _relation_citations(
    relations: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> list[Citation]:
    citations: list[Citation] = []
    for relation in relations:
        evidence = relation.get("evidence")
        if not isinstance(evidence, dict):
            continue
        source_range = evidence.get("source_range")
        if not isinstance(source_range, dict):
            continue
        path = source_range.get("path")
        start_line = source_range.get("start_line")
        end_line = source_range.get("end_line")
        if (
            not isinstance(path, str)
            or not isinstance(start_line, int)
            or not isinstance(end_line, int)
        ):
            continue
        citations.append(
            Citation(
                subject_kind="relation",
                subject_id=f"relation:{relation.get('kind')}:{relation.get('source_entity_id')}->{relation.get('target_entity_id')}",
                path=path,
                start_line=start_line,
                end_line=end_line,
                extractor=evidence.get("extractor")
                if isinstance(evidence.get("extractor"), str)
                else None,
                confidence=float(evidence["confidence"])
                if isinstance(evidence.get("confidence"), (int, float))
                else None,
            )
        )
    return citations


def _normalize_changed_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise ValueError("changed_paths entries must be repository-relative and bounded")
    if Path(normalized).is_absolute():
        raise ValueError("changed_paths entries must be repository-relative and bounded")
    return normalized


def _direct_relations_for_entity(
    entity_id: str, relations: list[Relation]
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = [
        {
            "kind": relation.kind,
            "source_entity_id": relation.source_entity_id.value,
            "target_entity_id": relation.target_entity_id.value,
        }
        for relation in relations
        if relation.source_entity_id.value == entity_id
        or relation.target_entity_id.value == entity_id
    ]
    items.sort(
        key=lambda row: (
            str(row["kind"]),
            str(row["source_entity_id"]),
            str(row["target_entity_id"]),
        )
    )
    return items[:_MAX_DIRECT_RELATIONS]


def _dedupe_uncertainties(uncertainties: list[Uncertainty]) -> tuple[Uncertainty, ...]:
    seen: set[tuple[str, str, bool, str | None]] = set()
    deduped: list[Uncertainty] = []
    for item in uncertainties:
        key = (item.code, item.message, item.recoverable, item.subject_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda item: (item.code, item.subject_id or "", item.message))
    return tuple(deduped)


def _normalize_subject_kind(
    subject_kind: str,
) -> Literal["entity", "relation", "claim", "git_summary"]:
    if subject_kind == "relation":
        return "relation"
    if subject_kind == "claim":
        return "claim"
    if subject_kind == "git_summary":
        return "git_summary"
    return "entity"
