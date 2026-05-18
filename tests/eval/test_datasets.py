"""Dataset parser tests for retrieval benchmark tasks."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.eval.datasets import load_retrieval_dataset


def test_load_retrieval_dataset_parses_yaml(tmp_path: Path) -> None:
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: example_001",
                "    category: code_localization",
                '    prompt: "Where is inactive publish gating enforced?"',
                "    gold:",
                "      files:",
                "        - src/example.py",
                "      symbols:",
                "        - example.Symbol",
                "      invariants:",
                "        - inactive_outgoing_calls_forbidden",
            ]
        ),
        encoding="utf-8",
    )

    dataset = load_retrieval_dataset(dataset_path)

    assert len(dataset.tasks) == 1
    task = dataset.tasks[0]
    assert task.id == "example_001"
    assert task.category == "code_localization"
    assert task.prompt == "Where is inactive publish gating enforced?"
    assert task.gold.files == ("src/example.py",)
    assert task.gold.symbols == ("example.Symbol",)
    assert task.gold.invariants == ("inactive_outgoing_calls_forbidden",)


def test_load_retrieval_dataset_fails_clearly_for_empty_tasks(tmp_path: Path) -> None:
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text("tasks:\n", encoding="utf-8")

    with pytest.raises(ValueError, match="contains no tasks"):
        load_retrieval_dataset(dataset_path)


def test_load_retrieval_dataset_rejects_non_posix_gold_file_paths(tmp_path: Path) -> None:
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: bad_path",
                "    category: code_localization",
                '    prompt: "locate thing"',
                "    gold:",
                "      files:",
                r"        - src\example.py",
                "      symbols:",
                "        - example.Symbol",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="POSIX separators"):
        load_retrieval_dataset(dataset_path)
