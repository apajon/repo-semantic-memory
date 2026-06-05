"""Dataset parser tests for retrieval benchmark tasks."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.eval.datasets import load_benchmark_dataset, load_retrieval_dataset


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


# ---------------------------------------------------------------------------
# 59.1 — Benchmark harness schema tests
# ---------------------------------------------------------------------------


def _write_benchmark_yaml(path: Path, tasks: str) -> None:
    path.write_text(f"tasks:\n{tasks}\n", encoding="utf-8")


class TestLoadBenchmarkDataset:
    """Tests for load_benchmark_dataset (59.0 enriched schema)."""

    def test_valid_case_loads(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find the resolver implementation."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/resolver.py\n"
                "      support_files:\n"
                "        - src/utils.py\n"
                "      test_files:\n"
                "        - tests/test_resolver.py\n"
                "      forbidden_files:\n"
                "        - src/noise.py\n"
                "    tags:\n"
                "      - ranking_v2\n"
                "      - regression\n"
                '    notes: "Regression case from 58.6."\n'
            ),
        )
        dataset = load_benchmark_dataset(tmp_path / "tasks.yaml")
        assert len(dataset.cases) == 1
        c = dataset.cases[0]
        assert c.id == "case_001"
        assert c.fixture == "simple_repo"
        assert c.query == "Find the resolver implementation."
        assert c.mode == "ci_fixture"
        assert c.expected.central_files == ("src/resolver.py",)
        assert c.expected.support_files == ("src/utils.py",)
        assert c.expected.test_files == ("tests/test_resolver.py",)
        assert c.expected.forbidden_files == ("src/noise.py",)
        assert c.tags == ("ranking_v2", "regression")
        assert c.notes == "Regression case from 58.6."

    def test_valid_case_empty_support_test_forbidden(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: minimal\n"
                "    fixture: simple_repo\n"
                "    mode: manual_external\n"
                '    query: "Find the resolver."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/resolver.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        dataset = load_benchmark_dataset(tmp_path / "tasks.yaml")
        c = dataset.cases[0]
        assert c.expected.support_files == ()
        assert c.expected.test_files == ()
        assert c.expected.forbidden_files == ()
        assert c.tags == ()
        assert c.notes == ""

    def test_missing_id_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/a.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="id"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_missing_fixture_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/a.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="fixture"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_missing_query_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                "    expected:\n"
                "      central_files:\n"
                "        - src/a.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="query"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_missing_expected_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="expected"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_missing_central_files_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="central_files"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_empty_central_files_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "      support_files:\n"
                "        - src/util.py\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="central_files"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_invalid_mode_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: invalid_mode\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/a.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="mode"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_absolute_path_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - /absolute/path.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="absolute"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_backslash_path_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                r"        - src\example.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="POSIX"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_parent_traversal_path_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/../escape.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="parent-traversal"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_unknown_expected_key_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/a.py\n"
                "      unknown_key:\n"
                "        - x.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                '    notes: ""\n'
            ),
        )
        with pytest.raises(ValueError, match="Unknown expected key"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")

    def test_deterministic_ordering_tuples(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: order_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/b.py\n"
                "        - src/a.py\n"
                "      support_files:\n"
                "        - src/z.py\n"
                "        - src/m.py\n"
                "      test_files:\n"
                "        - tests/test_b.py\n"
                "        - tests/test_a.py\n"
                "      forbidden_files:\n"
                "        - noise/z.py\n"
                "        - noise/a.py\n"
                "    tags:\n"
                "      - beta\n"
                "      - alpha\n"
                '    notes: ""\n'
            ),
        )
        d1 = load_benchmark_dataset(tmp_path / "tasks.yaml")
        d2 = load_benchmark_dataset(tmp_path / "tasks.yaml")
        c1, c2 = d1.cases[0], d2.cases[0]
        assert c1.expected.central_files == c2.expected.central_files
        assert c1.expected.support_files == c2.expected.support_files
        assert c1.expected.test_files == c2.expected.test_files
        assert c1.expected.forbidden_files == c2.expected.forbidden_files
        assert c1.tags == c2.tags

    def test_folded_notes_parsed(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(
            tmp_path / "tasks.yaml",
            (
                "  - id: case_001\n"
                "    fixture: simple_repo\n"
                "    mode: ci_fixture\n"
                '    query: "Find."\n'
                "    expected:\n"
                "      central_files:\n"
                "        - src/a.py\n"
                "      support_files:\n"
                "      test_files:\n"
                "      forbidden_files:\n"
                "    tags:\n"
                "    notes: >\n"
                "      Line one continuation.\n"
                "      Line two continuation.\n"
            ),
        )
        dataset = load_benchmark_dataset(tmp_path / "tasks.yaml")
        assert dataset.cases[0].notes == "Line one continuation. Line two continuation."

    def test_empty_dataset_fails(self, tmp_path: Path) -> None:
        _write_benchmark_yaml(tmp_path / "tasks.yaml", "")
        with pytest.raises(ValueError, match="contains no cases"):
            load_benchmark_dataset(tmp_path / "tasks.yaml")


# ---------------------------------------------------------------------------
# 59.6 — Manual external dataset tests
# ---------------------------------------------------------------------------

_MANUAL_DATASET = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "manual_external_benchmark_cases.yaml"
)


class TestManualExternalDataset:
    """Tests for benchmarks/manual_external_benchmark_cases.yaml."""

    def test_dataset_loads(self) -> None:
        """Manual external dataset loads with load_benchmark_dataset()."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        assert len(dataset.cases) == 4
        for case in dataset.cases:
            assert case.mode == "manual_external"
            assert case.expected.central_files

    def test_fixture_labels_match_known_repos(self) -> None:
        """Fixture labels correspond to known public repo names."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        fixtures = {case.fixture for case in dataset.cases}
        assert fixtures == {"django", "ansible", "httpx", "typer"}

    def test_all_cases_have_58_6_migration_tag(self) -> None:
        """Every case is tagged 58.6_migration for provenance."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        for case in dataset.cases:
            assert "58.6_migration" in case.tags, f"Case {case.id} missing 58.6_migration tag"

    def test_django_case_has_forbidden_files(self) -> None:
        """Django case includes the 12+ .url method noise files."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        django_case = next(c for c in dataset.cases if c.id == "django_url_resolution")
        assert len(django_case.expected.forbidden_files) >= 12
        assert "django/core/files/storage/base.py" in django_case.expected.forbidden_files

    def test_ansible_case_has_test_files(self) -> None:
        """Ansible case expects test_plugins.py as a test file."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        ansible_case = next(c for c in dataset.cases if c.id == "ansible_loader_discovery")
        assert "test/units/plugins/test_plugins.py" in ansible_case.expected.test_files

    def test_httpx_case_has_empty_test_files(self) -> None:
        """HTTPX case has no expected test files (not indexed in 58.6)."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        httpx_case = next(c for c in dataset.cases if c.id == "httpx_public_client_api")
        assert httpx_case.expected.test_files == ()

    def test_typer_case_has_docs_src_forbidden(self) -> None:
        """Typer case forbids docs_src/ tutorial files."""
        dataset = load_benchmark_dataset(_MANUAL_DATASET)
        typer_case = next(c for c in dataset.cases if c.id == "typer_command_registration")
        forbidden = typer_case.expected.forbidden_files
        assert any("docs_src/" in f for f in forbidden)
