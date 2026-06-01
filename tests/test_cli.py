"""CLI behavior tests."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from unittest import mock

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.extractors.git_history import GitRepositorySummary
from repo_semantic_memory.model import Entity, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata


def test_help_flag_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "rsm" in out


def test_version_command_prints_all_versions(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "package_version:" in out
    assert "schema_version:" in out
    assert "context_pack_version:" in out


def test_scan_command_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    exit_code = main(["scan", str(fixture_root), "--json"])
    assert exit_code == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload
    assert payload[0]["path"] == "config/data.json"


def test_index_python_command_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    exit_code = main(["index-python", str(fixture_root), "--json"])
    assert exit_code == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, dict)
    assert "entities" in payload
    assert "relations" in payload
    entity_kinds = {entity["kind"] for entity in payload["entities"]}
    relation_kinds = {relation["kind"] for relation in payload["relations"]}
    assert {"module", "class", "function", "method"}.issubset(entity_kinds)
    assert {"contains", "imports", "inherits"}.issubset(relation_kinds)
    qnames = {entity["qualified_name"] for entity in payload["entities"]}
    assert "python_symbols" in qnames
    inherits_relations = [
        relation for relation in payload["relations"] if relation["kind"] == "inherits"
    ]
    assert inherits_relations
    assert inherits_relations[0]["target_entity_id"] == "unresolved:python:basething"
    assert inherits_relations[0]["metadata"]["resolved"] is False


def test_index_command_creates_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(fixture_root), "--db", str(db_path)])
    assert exit_code == 0
    assert db_path.exists()

    out = capsys.readouterr().out
    assert "entities=" in out
    assert "relations=" in out


def test_index_command_with_git_unavailable_remains_graceful(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    monkeypatch.setattr(
        "repo_semantic_memory.cli.get_git_repository_summary",
        lambda path: GitRepositorySummary(
            path=str(path),
            in_git_repo=False,
            repository_root=None,
            current_commit=None,
            is_dirty=None,
            tracked_file_count=None,
            unavailable_reason="path is not inside a Git repository",
        ),
    )
    exit_code = main(["index", str(fixture_root), "--db", str(db_path), "--with-git"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "entities=" in captured.out
    assert "relations=" in captured.out
    assert "git_metadata=unavailable" in captured.out
    assert "git metadata:" in captured.err


def test_git_summary_command_non_repo_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["git", "summary", str(tmp_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "not inside a Git repository" in out


def test_git_summary_command_json_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.cli.get_git_repository_summary",
        lambda path: GitRepositorySummary(
            path=str(path),
            in_git_repo=True,
            repository_root="/repo",
            current_commit="abc123",
            is_dirty=False,
            tracked_file_count=5,
        ),
    )
    exit_code = main(["git", "summary", ".", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["in_git_repo"] is True
    assert payload["repository_root"] == "/repo"
    assert payload["current_commit"] == "abc123"
    assert payload["tracked_file_count"] == 5


def test_inspect_entities_command_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    index_exit = main(["index", str(fixture_root), "--db", str(db_path)])
    assert index_exit == 0
    capsys.readouterr()

    inspect_exit = main(["inspect", "entities", "--db", str(db_path), "--json"])
    assert inspect_exit == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload
    assert "id" in payload[0]
    assert "kind" in payload[0]


def test_inspect_relations_command_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    index_exit = main(["index", str(fixture_root), "--db", str(db_path)])
    assert index_exit == 0
    capsys.readouterr()

    inspect_exit = main(["inspect", "relations", "--db", str(db_path), "--json"])
    assert inspect_exit == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload
    assert "source_entity_id" in payload[0]
    assert "target_entity_id" in payload[0]


def test_index_command_uses_ast_as_python_module_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    index_exit = main(["index", str(fixture_root), "--db", str(db_path)])
    assert index_exit == 0
    capsys.readouterr()

    inspect_exit = main(["inspect", "entities", "--db", str(db_path), "--json"])
    assert inspect_exit == 0
    payload = json.loads(capsys.readouterr().out)

    module_entities = [entity for entity in payload if entity["kind"] == "module"]
    assert module_entities
    assert all(not entity["id"].startswith("file:") for entity in module_entities)
    assert any(entity["id"].startswith("python:") for entity in module_entities)


def test_repo_map_command_with_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    index_exit = main(["index", str(fixture_root), "--db", str(db_path)])
    assert index_exit == 0
    capsys.readouterr()

    repo_map_exit = main(["repo-map", "--db", str(db_path), "--budget", "4000"])
    assert repo_map_exit == 0

    output = capsys.readouterr().out
    assert output.startswith("# Repo map")
    assert "## src/python_symbols.py" in output
    assert "- module `python_symbols`" in output


def test_repo_map_command_with_path(capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"

    repo_map_exit = main(["repo-map", "--path", str(fixture_root), "--budget", "4000"])
    assert repo_map_exit == 0

    output = capsys.readouterr().out
    assert output.startswith("# Repo map")
    assert "## src/python_symbols.py" in output
    assert "- module `python_symbols`" in output


def test_repo_map_command_accepts_profile(capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    repo_map_exit = main(
        [
            "repo-map",
            "--path",
            str(fixture_root),
            "--budget",
            "4000",
            "--profile",
            "agent_brief",
        ]
    )
    assert repo_map_exit == 0
    output = capsys.readouterr().out
    assert output.startswith("# Repo map")


def test_repo_map_command_with_path_creates_no_persistent_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    target_repo = tmp_path / "repo"
    shutil.copytree(fixture_root, target_repo)

    repo_map_exit = main(["repo-map", "--path", str(target_repo), "--budget", "4000"])
    assert repo_map_exit == 0
    capsys.readouterr()

    assert not (target_repo / ".rsm").exists()
    assert list(target_repo.rglob("*.sqlite")) == []


def test_eval_retrieval_command_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: eval_001",
                "    category: code_localization",
                '    prompt: "Where is DerivedThing defined?"',
                "    gold:",
                "      files:",
                "        - src/python_symbols.py",
                "      symbols:",
                "        - python_symbols.DerivedThing",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "eval",
            "retrieval",
            "--db",
            str(db_path),
            "--dataset",
            str(dataset_path),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dataset_path"] == str(dataset_path)
    assert payload["db_path"] == str(db_path)
    assert payload["tasks"][0]["task_id"] == "eval_001"


def test_eval_retrieval_empty_dataset_fails_clearly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text("tasks:\n", encoding="utf-8")

    exit_code = main(
        ["eval", "retrieval", "--db", str(db_path), "--dataset", str(dataset_path), "--json"]
    )
    assert exit_code == 2
    assert "contains no tasks" in capsys.readouterr().err


def test_eval_compare_command_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: compare_001",
                "    category: code_localization",
                '    prompt: "Where is DerivedThing defined?"',
                "    gold:",
                "      files:",
                "        - src/python_symbols.py",
                "      symbols:",
                "        - python_symbols.DerivedThing",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "eval",
            "compare",
            "--db",
            str(db_path),
            "--dataset",
            str(dataset_path),
            "--budget",
            "4000",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dataset_path"] == str(dataset_path)
    assert payload["db_path"] == str(db_path)
    assert payload["budget"] == 4000
    assert payload["tasks"][0]["task_id"] == "compare_001"
    assert payload["tasks"][0]["winner"] in {
        "repo_map",
        "lexical_context_pack",
        "tie",
        "inconclusive",
    }
    assert "savings" in payload["aggregate"]
    savings = payload["tasks"][0]["savings_metrics"]
    assert "raw_baseline_chars" in savings
    assert "selected_context_chars" in savings
    assert "estimated_raw_tokens" in savings
    assert "estimated_selected_tokens" in savings
    assert "estimated_tokens_saved" in savings
    assert "compression_ratio" in savings
    assert "gold_file_coverage_preserved" in savings
    assert "gold_symbol_coverage_preserved" in savings
    assert "coverage_per_1k_tokens" in savings


def test_eval_compare_command_markdown_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    report_path = tmp_path / "compare_report.md"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: compare_002",
                "    category: code_localization",
                '    prompt: "Where is DerivedThing defined?"',
                "    gold:",
                "      files:",
                "        - src/python_symbols.py",
                "      symbols:",
                "        - python_symbols.DerivedThing",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "eval",
            "compare",
            "--db",
            str(db_path),
            "--dataset",
            str(dataset_path),
            "--budget",
            "4000",
            "--markdown-report",
            str(report_path),
        ]
    )
    assert exit_code == 0
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "# Baseline comparison report" in report
    assert "## Aggregate results" in report


def test_pack_command_markdown_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "pack",
            "--task",
            "DerivedThing",
            "--db",
            str(db_path),
            "--budget",
            "4000",
        ]
    )
    assert exit_code == 0

    output = capsys.readouterr().out
    assert output.startswith("# Context pack")
    assert "## Selected symbols" in output
    assert "python_symbols.DerivedThing" in output


def test_pack_command_yaml_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "pack",
            "--task",
            "DerivedThing",
            "--db",
            str(db_path),
            "--budget",
            "4000",
            "--format",
            "yaml",
        ]
    )
    assert exit_code == 0

    # Output is JSON-formatted for deterministic YAML 1.2-compatible serialization.
    parsed_yaml = json.loads(capsys.readouterr().out)
    assert parsed_yaml["task"] == "DerivedThing"
    assert parsed_yaml["selected_entities"]
    assert "ranking_breakdowns" not in parsed_yaml
    selected_qnames = {entity["qualified_name"] for entity in parsed_yaml["selected_entities"]}
    assert "python_symbols.DerivedThing" in selected_qnames


def test_pack_command_yaml_output_with_explain_ranking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "pack",
            "--task",
            "DerivedThing implementation",
            "--db",
            str(db_path),
            "--budget",
            "4000",
            "--format",
            "yaml",
            "--explain-ranking",
        ]
    )
    assert exit_code == 0

    parsed_yaml = json.loads(capsys.readouterr().out)
    assert parsed_yaml["ranking_breakdowns"]
    first_breakdown = next(iter(parsed_yaml["ranking_breakdowns"].values()))
    assert "matched_fields" in first_breakdown
    assert "reasons" in first_breakdown


def test_pack_command_markdown_explain_ranking_includes_score_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "pack",
            "--task",
            "DerivedThing implementation",
            "--db",
            str(db_path),
            "--budget",
            "4000",
            "--explain-ranking",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Score: total=" in output
    assert "Reason:" in output


def test_pack_command_agent_debug_profile_includes_ranking_without_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "pack",
            "--task",
            "DerivedThing implementation",
            "--db",
            str(db_path),
            "--budget",
            "4000",
            "--profile",
            "agent_debug",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Score: total=" in output


def test_pack_command_invalid_profile_fails_clearly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["pack", "--task", "x", "--profile", "unknown_profile"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_components_infer_command_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(["components", "infer", "--db", str(db_path), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert all(item["status"] in {"confirmed", "inferred", "needs_review"} for item in payload)
    assert all(
        item["status"] == "needs_review" or item["evidence"] or item.get("inference_note")
        for item in payload
    )


def test_components_list_command_is_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["components", "list", "--db", str(db_path), "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["components", "list", "--db", str(db_path), "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first == second


def test_components_list_matches_infer_derived_view(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["components", "infer", "--db", str(db_path), "--json"]) == 0
    inferred = json.loads(capsys.readouterr().out)

    assert main(["components", "list", "--db", str(db_path), "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == inferred


def test_invariants_export_import_commands_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    invariants_path = tmp_path / "invariants.yaml"

    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    components_exit = main(["components", "infer", "--db", str(db_path), "--json"])
    assert components_exit == 0
    components_payload = json.loads(capsys.readouterr().out)
    assert isinstance(components_payload, list)
    assert all(item["status"] != "confirmed" for item in components_payload)

    export_exit = main(
        ["invariants", "export", "--db", str(db_path), "--out", str(invariants_path)]
    )
    assert export_exit == 0
    export_out = capsys.readouterr().out
    assert "exported invariants document" in export_out
    assert invariants_path.exists()
    exported_payload = json.loads(invariants_path.read_text(encoding="utf-8"))
    assert exported_payload["claims"] == []
    assert exported_payload["invariants"] == []
    assert (
        exported_payload["note"] == "No claims or invariants are inferred automatically by default."
    )

    import_exit = main(["invariants", "import", "--db", str(db_path), str(invariants_path)])
    assert import_exit == 0
    import_out = capsys.readouterr().out
    assert "validated invariants document" in import_out


def test_export_jsonl_command_creates_expected_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    out_dir = tmp_path / ".rsm" / "export"
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(["export-jsonl", "--db", str(db_path), "--out", str(out_dir)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "exported jsonl to" in out
    assert (out_dir / "entities.jsonl").exists()
    assert (out_dir / "relations.jsonl").exists()
    assert (out_dir / "metadata.json").exists()


def test_import_jsonl_command_reconstructs_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_db_path = tmp_path / ".rsm" / "index.sqlite"
    export_dir = tmp_path / ".rsm" / "export"
    imported_db_path = tmp_path / ".rsm" / "imported.sqlite"
    source_db_path.parent.mkdir(parents=True, exist_ok=True)

    store = SQLiteStore(source_db_path)
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("test",),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        lifecycle_entity = Entity(
            id=StableId("python:src/example.py:class:example.lifecyclemanager"),
            kind="class",
            name="LifecycleManager",
            qualified_name="example.LifecycleManager",
            source_range=SourceRange(path="src/example.py", start_line=1, end_line=20),
        )
        store.persist_index(entities=[lifecycle_entity], relations=[], metadata=metadata)
    finally:
        store.close()

    assert main(["export-jsonl", "--db", str(source_db_path), "--out", str(export_dir)]) == 0
    export_capture = capsys.readouterr()
    assert "components=1" in export_capture.out

    exit_code = main(["import-jsonl", "--in", str(export_dir), "--db", str(imported_db_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "imported jsonl from" in out
    assert "ignored components.jsonl" in captured.err

    inspect_exit = main(["inspect", "entities", "--db", str(imported_db_path), "--json"])
    assert inspect_exit == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload


# ---------------------------------------------------------------------------
# Index Store resolution for reader commands (Prompt 50.5 dogfooding fix)
# ---------------------------------------------------------------------------


def test_pack_resolves_db_from_index_store(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """rsm pack without --db should use the registered Index Store DB."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    store_home = tmp_path / "rsm_home"
    store_home.mkdir()
    db_path = store_home / "indexes" / "test_pack" / "index.sqlite"
    db_path.parent.mkdir(parents=True)

    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    from repo_semantic_memory.store_home import IndexRegistry

    IndexRegistry(store_home).register(fixture_root, db_path, indexed=True)

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        with mock.patch("pathlib.Path.cwd", return_value=fixture_root):
            exit_code = main(["pack", "--task", "DerivedThing", "--budget", "4000"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "# Context pack" in output
    assert "DerivedThing" in output


def test_pack_explicit_db_overrides_index_store(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explicit --db must take priority over Index Store lookup."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / "explicit.sqlite"

    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(["pack", "--task", "DerivedThing", "--budget", "4000", "--db", str(db_path)])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "# Context pack" in output


def test_repo_map_resolves_db_from_index_store(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """rsm repo-map without --db or --path should use the Index Store DB."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    store_home = tmp_path / "rsm_home"
    store_home.mkdir()
    db_path = store_home / "indexes" / "test_map" / "index.sqlite"
    db_path.parent.mkdir(parents=True)

    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0
    capsys.readouterr()

    from repo_semantic_memory.store_home import IndexRegistry

    IndexRegistry(store_home).register(fixture_root, db_path, indexed=True)

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        with mock.patch("pathlib.Path.cwd", return_value=fixture_root):
            exit_code = main(["repo-map", "--budget", "2000"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "# Repo map" in output


def test_resolve_reader_db_fallback_when_no_store_entry(
    tmp_path: Path,
) -> None:
    """_resolve_reader_db returns .rsm/index.sqlite when no Index Store entry exists."""
    from repo_semantic_memory.cli import _resolve_reader_db

    store_home = tmp_path / "empty_rsm_home"
    store_home.mkdir()

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        with mock.patch("pathlib.Path.cwd", return_value=tmp_path / "repo"):
            result = _resolve_reader_db(None)

    assert result == ".rsm/index.sqlite"


def test_resolve_reader_db_returns_explicit_db_unchanged(tmp_path: Path) -> None:
    """_resolve_reader_db returns the explicit path unchanged."""
    from repo_semantic_memory.cli import _resolve_reader_db

    explicit = str(tmp_path / "my.sqlite")
    assert _resolve_reader_db(explicit) == explicit


# ---------------------------------------------------------------------------
# Indexing progress feedback
# ---------------------------------------------------------------------------


def test_index_command_emits_stage_progress_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """rsm index prints per-stage progress messages to stderr so large repos don't appear hung."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(fixture_root), "--db", str(db_path)])
    assert exit_code == 0

    err = capsys.readouterr().err
    assert "indexing: scanning files" in err
    assert "indexing: discovered files:" in err
    assert "indexing: extracting Markdown" in err
    assert "indexing: Markdown complete:" in err
    assert "indexing: parsing Python" in err
    assert "indexing: Python complete:" in err
    assert "indexing: extracting exports" in err
    assert "indexing: exports complete:" in err
    assert "indexing: computing test relationships" in err
    assert "indexing: test relationships complete:" in err
    assert "indexing: writing index" in err
    assert "indexing: writing index complete:" in err
    assert "indexing: complete:" in err


def test_index_command_scan_summary_contains_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The scan summary line reports python=, markdown=, other=, total= counts."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(fixture_root), "--db", str(db_path)])
    assert exit_code == 0

    err = capsys.readouterr().err
    assert "indexing: discovered files: python=" in err
    assert "markdown=" in err
    assert "other=" in err
    assert "total=" in err


def test_index_command_completion_lines_contain_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Completion lines include file/entity/relation counts and an elapsed= field."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(fixture_root), "--db", str(db_path)])
    assert exit_code == 0

    err = capsys.readouterr().err
    # Markdown completion includes N/N files and elapsed.
    assert "indexing: Markdown complete:" in err
    assert "elapsed=" in err
    # Python completion includes N/N files.
    assert "indexing: Python complete:" in err
    # exports completion includes N/N files.
    assert "indexing: exports complete:" in err
    # test relationships completion includes added= and total_relations=.
    assert "added=" in err
    assert "total_relations=" in err
    # Final summary includes entities= and relations=.
    assert "indexing: complete: entities=" in err


def test_index_command_relation_context_includes_entity_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test-relationship banner includes entity and relation counts."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(fixture_root), "--db", str(db_path)])
    assert exit_code == 0

    err = capsys.readouterr().err
    assert "indexing: computing test relationships from entities=" in err
    assert "relations=" in err


def test_index_command_progress_does_not_pollute_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Progress messages must not appear on stdout; the summary line stays clean."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(fixture_root), "--db", str(db_path)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "indexing:" not in captured.out
    assert "entities=" in captured.out
    assert "relations=" in captured.out


def test_should_emit_progress_helper() -> None:
    """should_emit_progress returns False below min_total, True at milestones."""
    from repo_semantic_memory.cli import should_emit_progress

    # Silent below threshold.
    assert not should_emit_progress(1, 50, min_total=100)
    assert not should_emit_progress(50, 50, min_total=100)

    # First file.
    assert should_emit_progress(1, 200)
    # Every interval-th file.
    assert should_emit_progress(100, 200)
    assert should_emit_progress(200, 200)
    # Non-milestone files.
    assert not should_emit_progress(2, 200)
    assert not should_emit_progress(99, 200)
    assert not should_emit_progress(101, 200)


def test_progress_callback_fires_at_milestones(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_make_progress_callback emits lines at first, interval, but not at done==total."""
    from repo_semantic_memory.cli import _PROGRESS_INTERVAL, _make_progress_callback

    total = _PROGRESS_INTERVAL * 2
    cb = _make_progress_callback("TestPhase")
    for i in range(1, total + 1):
        cb(i, total)

    err = capsys.readouterr().err
    assert f"indexing: TestPhase 1/{total}" in err
    assert f"indexing: TestPhase {_PROGRESS_INTERVAL}/{total}" in err
    # Completion line is NOT emitted by the callback (caller does it).
    assert f"indexing: TestPhase {total}/{total}" not in err


def test_progress_callback_silent_below_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_make_progress_callback emits nothing when total < min_total."""
    from repo_semantic_memory.cli import _PROGRESS_MIN_TOTAL, _make_progress_callback

    total = _PROGRESS_MIN_TOTAL - 1
    cb = _make_progress_callback("TestPhase")
    for i in range(1, total + 1):
        cb(i, total)

    assert capsys.readouterr().err == ""


def test_python_progress_callback_fires_for_large_file_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Per-file progress lines are emitted when total >= _PYTHON_PROGRESS_INTERVAL."""
    from repo_semantic_memory.cli import _PYTHON_PROGRESS_INTERVAL, _make_python_progress_callback

    total = _PYTHON_PROGRESS_INTERVAL * 2
    cb = _make_python_progress_callback()
    for i in range(1, total + 1):
        cb(i, total)

    err = capsys.readouterr().err
    assert f"indexing: Python 1/{total}" in err
    assert f"indexing: Python {_PYTHON_PROGRESS_INTERVAL}/{total}" in err
    # done==total is suppressed in callback; completion line is printed by caller.
    assert f"indexing: Python {total}/{total} files..." not in err


def test_python_progress_callback_silent_for_small_file_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No per-file lines are emitted when total < _PYTHON_PROGRESS_INTERVAL."""
    from repo_semantic_memory.cli import _PYTHON_PROGRESS_INTERVAL, _make_python_progress_callback

    total = _PYTHON_PROGRESS_INTERVAL - 1
    cb = _make_python_progress_callback()
    for i in range(1, total + 1):
        cb(i, total)

    assert capsys.readouterr().err == ""


def test_markdown_progress_callback_fires_for_large_file_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Markdown progress callback emits milestone lines for large totals."""
    from repo_semantic_memory.cli import _PROGRESS_INTERVAL, _make_progress_callback

    total = _PROGRESS_INTERVAL * 3
    cb = _make_progress_callback("Markdown")
    for i in range(1, total + 1):
        cb(i, total)

    err = capsys.readouterr().err
    assert f"indexing: Markdown 1/{total}" in err
    assert f"indexing: Markdown {_PROGRESS_INTERVAL}/{total}" in err
    assert f"indexing: Markdown {_PROGRESS_INTERVAL * 2}/{total}" in err
    assert f"indexing: Markdown {total}/{total}" not in err  # suppressed; caller prints completion


def test_markdown_progress_callback_silent_below_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Markdown progress callback is silent when total < threshold."""
    from repo_semantic_memory.cli import _PROGRESS_MIN_TOTAL, _make_progress_callback

    total = _PROGRESS_MIN_TOTAL - 1
    cb = _make_progress_callback("Markdown")
    for i in range(1, total + 1):
        cb(i, total)

    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# --profile flag (Prompt 57.1)
# ---------------------------------------------------------------------------

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "simple_repo"


def test_index_profile_writes_to_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """rsm index --profile must write the profiling summary to stderr."""
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(_FIXTURE_ROOT), "--db", str(db_path), "--profile"])
    assert exit_code == 0

    err = capsys.readouterr().err
    assert "indexing profile:" in err


def test_index_profile_contains_phase_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The profiling summary must include all expected phase rows."""
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(_FIXTURE_ROOT), "--db", str(db_path), "--profile"])
    assert exit_code == 0

    err = capsys.readouterr().err
    for phase in (
        "file_discovery",
        "markdown_extraction",
        "python_ast",
        "exports_extraction",
        "test_relationships",
        "sqlite_persist",
        "metadata_write",
    ):
        assert phase in err, f"Expected phase '{phase}' in profiling output"


def test_index_profile_stdout_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--profile must not add or remove anything from stdout."""
    db_path_no_profile = tmp_path / "no_profile" / "index.sqlite"
    db_path_profile = tmp_path / "profile" / "index.sqlite"

    main(["index", str(_FIXTURE_ROOT), "--db", str(db_path_no_profile)])
    out_no_profile = capsys.readouterr().out

    main(["index", str(_FIXTURE_ROOT), "--db", str(db_path_profile), "--profile"])
    out_profile = capsys.readouterr().out

    assert out_profile == out_no_profile


def test_index_no_profile_flag_omits_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --profile, the profiling summary must not appear on stderr."""
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(_FIXTURE_ROOT), "--db", str(db_path)])
    assert exit_code == 0

    err = capsys.readouterr().err
    assert "indexing profile:" not in err


def test_index_profile_db_output_identical_with_and_without(
    tmp_path: Path,
) -> None:
    """The DB entity/relation counts must be the same with or without --profile."""
    import sqlite3

    db_no_profile = tmp_path / "no_profile" / "index.sqlite"
    db_profile = tmp_path / "profile" / "index.sqlite"

    main(["index", str(_FIXTURE_ROOT), "--db", str(db_no_profile)])
    main(["index", str(_FIXTURE_ROOT), "--db", str(db_profile), "--profile"])

    def _get_db_counts(db: Path) -> tuple[int, int]:
        with sqlite3.connect(db) as conn:
            (entities,) = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
            (relations,) = conn.execute("SELECT COUNT(*) FROM relations").fetchone()
        return int(entities), int(relations)

    assert _get_db_counts(db_no_profile) == _get_db_counts(db_profile)
