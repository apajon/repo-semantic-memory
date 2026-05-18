"""Tests for AiDirectoryExporter and export-ai CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repo_semantic_memory.cli import main
from repo_semantic_memory.exporters import AiDirectoryExporter
from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.model.ids import StableId
from repo_semantic_memory.model.source_range import SourceRange

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "simple_repo"


def _make_entity(entity_id: str, kind: str, name: str, path: str) -> Entity:
    return Entity(
        id=StableId(entity_id),
        kind=kind,
        name=name,
        qualified_name=name,
        source_range=SourceRange(path=path, start_line=1, end_line=10),
    )


def _build_db(tmp_path: Path) -> Path:
    """Index the fixture repo into a SQLite db and return its path."""
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(FIXTURE_ROOT), "--db", str(db_path)])
    assert exit_code == 0
    return db_path


def _make_exporter(
    tmp_path: Path, entities: list[Entity], relations: list[Relation]
) -> AiDirectoryExporter:
    return AiDirectoryExporter(
        db_path=Path(".rsm/index.sqlite"),
        output_dir=tmp_path / ".ai",
        entities=entities,
        relations=relations,
        metadata={"schema_version": "0.1.0"},
        generated_at="2026-01-01T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# AiDirectoryExporter unit tests
# ---------------------------------------------------------------------------


def test_export_creates_expected_files(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    result = exporter.export()

    ai_dir = tmp_path / ".ai"
    assert ai_dir.is_dir()
    for name in (
        "README.md",
        "INDEX.yaml",
        "repo_map.md",
        "symbols.yaml",
        "relations.yaml",
        "context_policy.md",
    ):
        assert (ai_dir / name).exists(), f"Expected {name} to be created"
    # No components or invariants → those files should NOT exist
    assert not (ai_dir / "components.yaml").exists()
    assert not (ai_dir / "invariants.yaml").exists()
    assert set(result.files_written) >= {
        "README.md",
        "INDEX.yaml",
        "repo_map.md",
        "symbols.yaml",
        "relations.yaml",
        "context_policy.md",
    }


def test_export_no_overwrite_without_force(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    result1 = exporter.export(force=False)
    assert result1.files_skipped == ()

    # Second export without force → all existing files skipped
    result2 = exporter.export(force=False)
    assert set(result2.files_skipped) == set(result1.files_written)
    assert result2.files_written == ()


def test_export_overwrite_with_force(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export(force=False)

    # Mutate a file to verify it gets overwritten
    readme = tmp_path / ".ai" / "README.md"
    readme.write_text("MODIFIED", encoding="utf-8")

    exporter.export(force=True)
    assert "MODIFIED" not in readme.read_text(encoding="utf-8")


def test_index_yaml_parses_as_valid_yaml(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    content = (tmp_path / ".ai" / "INDEX.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert "generated_at" in parsed
    assert "source_db" in parsed
    assert "versions" in parsed
    assert "counts" in parsed
    assert parsed["counts"]["entities"] == 1


def test_symbols_yaml_parses_and_contains_citations(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    content = (tmp_path / ".ai" / "symbols.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert "symbols" in parsed
    symbols = parsed["symbols"]
    assert len(symbols) == 1
    assert symbols[0]["id"] == "python:mymod"
    assert symbols[0]["kind"] == "module"
    # Source citation must include path and line
    assert "src/mymod.py:1" in symbols[0]["source"]


def test_relations_yaml_parses(tmp_path: Path) -> None:
    entities = [
        _make_entity("python:mod_a", "module", "mod_a", "src/a.py"),
        _make_entity("python:mod_b", "module", "mod_b", "src/b.py"),
    ]
    relations = [
        Relation(
            source_entity_id=StableId("python:mod_a"),
            target_entity_id=StableId("python:mod_b"),
            kind="imports",
        )
    ]
    exporter = _make_exporter(tmp_path, entities, relations)
    exporter.export()

    content = (tmp_path / ".ai" / "relations.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert "relations" in parsed
    rels = parsed["relations"]
    assert len(rels) == 1
    assert rels[0]["kind"] == "imports"
    assert rels[0]["source"] == "python:mod_a"
    assert rels[0]["target"] == "python:mod_b"


def test_components_yaml_created_when_components_inferred(tmp_path: Path) -> None:
    # A class entity with 'tests' relation triggers TestTarget/TestFile components
    entities = [
        _make_entity("python:mymod", "module", "mymod", "src/mymod.py"),
        _make_entity("python:mymod.myclass", "class", "MyClass", "src/mymod.py"),
    ]
    exporter = _make_exporter(tmp_path, entities, [])
    # Components may or may not be generated depending on inference rules.
    # Just ensure the file exists iff components are non-empty.
    from repo_semantic_memory.memory.ecs_components import infer_semantic_components

    components = infer_semantic_components(entities=entities, relations=[])
    result = exporter.export()

    ai_dir = tmp_path / ".ai"
    if components:
        assert (ai_dir / "components.yaml").exists()
        content = (ai_dir / "components.yaml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)
        assert "components" in parsed
    else:
        assert not (ai_dir / "components.yaml").exists()
    assert result.component_count == len(components)


def test_invariants_yaml_created_for_invariant_entities(tmp_path: Path) -> None:
    entities = [
        _make_entity("python:mymod", "module", "mymod", "src/mymod.py"),
        Entity(
            id=StableId("invariant:schema-v1"),
            kind="invariant",
            name="SchemaV1",
            qualified_name="SchemaV1",
            source_range=SourceRange(path="src/schema.py", start_line=5, end_line=5),
        ),
    ]
    exporter = _make_exporter(tmp_path, entities, [])
    result = exporter.export()

    ai_dir = tmp_path / ".ai"
    assert (ai_dir / "invariants.yaml").exists()
    content = (ai_dir / "invariants.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert "invariants" in parsed
    assert parsed["invariants"][0]["id"] == "invariant:schema-v1"
    assert "src/schema.py:5" in parsed["invariants"][0]["source"]
    assert result.invariant_count == 1


def test_readme_contains_source_of_truth_warning(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    content = (tmp_path / ".ai" / "README.md").read_text(encoding="utf-8")
    assert "Source of truth" in content or "source of truth" in content
    assert "stale" in content
    assert "rsm export-ai" in content
    assert "coding agents" in content


def test_generated_files_include_regenerate_warning(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    for fname in ("INDEX.yaml", "symbols.yaml", "relations.yaml"):
        content = (tmp_path / ".ai" / fname).read_text(encoding="utf-8")
        assert "WARNING" in content, f"{fname} should contain regeneration warning"
        assert "rsm export-ai" in content, f"{fname} should reference regenerate command"


def test_rsm_directory_not_exported(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    ai_dir = tmp_path / ".ai"
    all_files = list(ai_dir.rglob("*"))
    assert not any(".rsm" in str(f) for f in all_files)
    assert not any(".sqlite" in str(f) for f in all_files)


def test_output_is_deterministic_with_fixed_timestamp(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    out1 = tmp_path / "ai1"
    out2 = tmp_path / "ai2"
    for out in (out1, out2):
        e = AiDirectoryExporter(
            db_path=Path(".rsm/index.sqlite"),
            output_dir=out,
            entities=entities,
            relations=[],
            metadata={"schema_version": "0.1.0"},
            generated_at="2026-01-01T00:00:00+00:00",
        )
        e.export()

    for fname in ("INDEX.yaml", "symbols.yaml", "relations.yaml"):
        assert (out1 / fname).read_text() == (out2 / fname).read_text(), (
            f"{fname} output should be deterministic"
        )


def test_index_yaml_contains_versions(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    content = (tmp_path / ".ai" / "INDEX.yaml").read_text(encoding="utf-8")
    assert "package_version" in content
    assert "schema_version" in content
    assert "context_pack_version" in content
    assert "source_db" in content
    assert "generated_at" in content


def test_index_yaml_contains_source_db_path(tmp_path: Path) -> None:
    entities = [_make_entity("python:mymod", "module", "mymod", "src/mymod.py")]
    exporter = _make_exporter(tmp_path, entities, [])
    exporter.export()

    content = (tmp_path / ".ai" / "INDEX.yaml").read_text(encoding="utf-8")
    assert ".rsm/index.sqlite" in content


def test_export_ai_cli_command_creates_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _build_db(tmp_path)
    capsys.readouterr()

    ai_dir = tmp_path / ".ai"
    exit_code = main(["export-ai", "--db", str(db_path), "--out", str(ai_dir)])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "exported to" in out
    assert "entities=" in out
    assert "files_written=" in out

    for fname in ("README.md", "INDEX.yaml", "repo_map.md", "symbols.yaml", "relations.yaml"):
        assert (ai_dir / fname).exists(), f"Expected {fname} in .ai/"


def test_export_ai_cli_skips_existing_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _build_db(tmp_path)
    ai_dir = tmp_path / ".ai"
    capsys.readouterr()

    main(["export-ai", "--db", str(db_path), "--out", str(ai_dir)])
    capsys.readouterr()

    # Modify README to detect if it gets overwritten
    readme = ai_dir / "README.md"
    readme.write_text("CUSTOM CONTENT", encoding="utf-8")

    exit_code = main(["export-ai", "--db", str(db_path), "--out", str(ai_dir)])
    assert exit_code == 0
    err = capsys.readouterr().err
    assert "README.md" in err
    assert "force" in err.lower()
    assert readme.read_text(encoding="utf-8") == "CUSTOM CONTENT"


def test_export_ai_cli_force_overwrites(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _build_db(tmp_path)
    ai_dir = tmp_path / ".ai"
    capsys.readouterr()

    main(["export-ai", "--db", str(db_path), "--out", str(ai_dir)])
    capsys.readouterr()

    readme = ai_dir / "README.md"
    readme.write_text("CUSTOM CONTENT", encoding="utf-8")

    exit_code = main(["export-ai", "--db", str(db_path), "--out", str(ai_dir), "--force"])
    assert exit_code == 0
    assert readme.read_text(encoding="utf-8") != "CUSTOM CONTENT"
