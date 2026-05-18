"""CLI behavior tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main


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
