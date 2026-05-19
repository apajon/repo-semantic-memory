"""BM25 field-weighted lexical retrieval tests."""

from __future__ import annotations

from repo_semantic_memory.context.bm25 import (
    BM25Config,
    FieldedBM25Index,
    FieldedDocument,
    tokenize_text,
)


def _rank_ids(index: FieldedBM25Index, query: str, doc_ids: tuple[str, ...]) -> list[str]:
    query_tokens = tokenize_text(query)
    return sorted(
        doc_ids,
        key=lambda doc_id: (-index.score(doc_id, query_tokens).score, doc_id),
    )


def test_tokenize_text_handles_identifiers_paths_and_dotted_names() -> None:
    tokens = tokenize_text(
        "CamelCase snake_case src/repo-semantic-memory/context.pack_builder.py pkg.module-name"
    )

    assert "camel" in tokens
    assert "case" in tokens
    assert "snake" in tokens
    assert "src" in tokens
    assert "repo" in tokens
    assert "semantic" in tokens
    assert "memory" in tokens
    assert "context" in tokens
    assert "pack" in tokens
    assert "builder" in tokens
    assert "pkg" in tokens
    assert "module" in tokens
    assert "name" in tokens


def test_bm25_prefers_exact_name_match_over_metadata_only_match() -> None:
    index = FieldedBM25Index(
        (
            FieldedDocument(
                doc_id="entity:name",
                fields={"name": "LifecycleComponent", "metadata": ""},
            ),
            FieldedDocument(
                doc_id="entity:metadata",
                fields={"name": "OtherThing", "metadata": "lifecyclecomponent details"},
            ),
        )
    )

    ranked = _rank_ids(index, "LifecycleComponent", ("entity:name", "entity:metadata"))
    assert ranked == ["entity:name", "entity:metadata"]


def test_bm25_qualified_name_match_outranks_generic_docs_text() -> None:
    index = FieldedBM25Index(
        (
            FieldedDocument(
                doc_id="entity:qualified",
                fields={"qualified_name": "repo.context.pack_builder.build_context_pack"},
            ),
            FieldedDocument(
                doc_id="entity:docs",
                fields={
                    "metadata": "The docs discuss build context pack behavior in general terms."
                },
            ),
        )
    )

    ranked = _rank_ids(
        index,
        "repo.context.pack_builder.build_context_pack",
        ("entity:qualified", "entity:docs"),
    )
    assert ranked == ["entity:qualified", "entity:docs"]


def test_bm25_source_path_field_supports_path_oriented_queries() -> None:
    index = FieldedBM25Index(
        (
            FieldedDocument(
                doc_id="entity:path",
                fields={"source_path": "src/repo_semantic_memory/context/pack_builder.py"},
            ),
            FieldedDocument(
                doc_id="entity:other",
                fields={"name": "pack_builder", "metadata": "mentions context selection"},
            ),
        )
    )

    ranked = _rank_ids(
        index,
        "src/repo_semantic_memory/context/pack_builder.py",
        ("entity:path", "entity:other"),
    )
    assert ranked == ["entity:path", "entity:other"]


def test_bm25_field_weights_change_ranking_predictably() -> None:
    documents = (
        FieldedDocument(doc_id="entity:name", fields={"name": "LifecycleComponent"}),
        FieldedDocument(doc_id="entity:meta", fields={"metadata": "lifecyclecomponent"}),
    )
    default_index = FieldedBM25Index(documents)
    metadata_weighted_index = FieldedBM25Index(
        documents,
        config=BM25Config(
            field_weights={
                "qualified_name": 0.2,
                "name": 0.2,
                "source_path": 0.2,
                "kind": 0.2,
                "semantic_components": 0.2,
                "relation_labels": 0.2,
                "metadata": 4.0,
                "id": 0.2,
            }
        ),
    )

    default_ranked = _rank_ids(default_index, "LifecycleComponent", ("entity:name", "entity:meta"))
    metadata_ranked = _rank_ids(
        metadata_weighted_index, "LifecycleComponent", ("entity:name", "entity:meta")
    )

    assert default_ranked == ["entity:name", "entity:meta"]
    assert metadata_ranked == ["entity:meta", "entity:name"]


def test_bm25_ranking_is_stable_for_ties() -> None:
    index = FieldedBM25Index(
        (
            FieldedDocument(doc_id="entity:b", fields={"name": "alpha"}),
            FieldedDocument(doc_id="entity:a", fields={"name": "alpha"}),
        )
    )

    ranked = _rank_ids(index, "no-match-token", ("entity:b", "entity:a"))
    assert ranked == ["entity:a", "entity:b"]
