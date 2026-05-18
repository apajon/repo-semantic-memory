"""CLI behavior tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
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
    selected_qnames = {entity["qualified_name"] for entity in parsed_yaml["selected_entities"]}
    assert "python_symbols.DerivedThing" in selected_qnames


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
