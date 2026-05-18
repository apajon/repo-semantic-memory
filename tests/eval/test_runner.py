"""Runner behavior tests for retrieval benchmark evaluation."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.cli import main
from repo_semantic_memory.eval.runner import run_retrieval_benchmark


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
