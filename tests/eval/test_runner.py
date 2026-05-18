"""Runner behavior tests for retrieval benchmark evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from repo_semantic_memory.cli import main
from repo_semantic_memory.eval.runner import run_retrieval_benchmark
from repo_semantic_memory.model import Entity, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata


def test_runner_is_deterministic_and_reports_missing_gold(tmp_path: Path) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: deterministic_001",
                "    category: code_localization",
                '    prompt: "Where are python symbols defined?"',
                "    gold:",
                "      files:",
                "        - src/python_symbols.py",
                "        - src/does_not_exist.py",
                "      symbols:",
                "        - python_symbols.DerivedThing",
                "        - python_symbols.Missing",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0

    first = run_retrieval_benchmark(db_path=db_path, dataset_path=dataset_path)
    second = run_retrieval_benchmark(db_path=db_path, dataset_path=dataset_path)

    assert first.outcomes == second.outcomes
    outcome = first.outcomes[0]
    assert "src/python_symbols.py" in outcome.ranked_files
    assert "python_symbols.DerivedThing" in outcome.ranked_symbols
    assert outcome.missing_gold_files == ("src/does_not_exist.py",)
    assert outcome.missing_gold_symbols == ("python_symbols.Missing",)


def test_runner_tie_breaks_rankings_by_entity_id(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: tie_break_001",
                "    category: code_localization",
                '    prompt: "alpha"',
                "    gold:",
                "      files:",
                "        - b.py",
                "      symbols:",
                "        - alpha.two",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )

    entities = [
        Entity(
            id=StableId("id:z"),
            kind="module",
            name="alpha",
            qualified_name="alpha.one",
            source_range=SourceRange(path="a.py", start_line=1, end_line=1),
            metadata={},
        ),
        Entity(
            id=StableId("id:a"),
            kind="module",
            name="alpha",
            qualified_name="alpha.two",
            source_range=SourceRange(path="b.py", start_line=1, end_line=1),
            metadata={},
        ),
    ]
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("test",),
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        store.persist_index(entities=entities, relations=[], metadata=metadata)
    finally:
        store.close()

    result = run_retrieval_benchmark(
        db_path=db_path, dataset_path=dataset_path, max_ranked_results=2
    )

    outcome = result.outcomes[0]
    assert outcome.ranked_files[:2] == ("b.py", "a.py")
    assert outcome.ranked_symbols[:2] == ("alpha.two", "alpha.one")
