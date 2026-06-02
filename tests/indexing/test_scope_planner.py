"""Tests for the advisory index scope planner (Prompt 57.6).

``rsm index plan <repo>`` inspects a repository cheaply and recommends a safe
indexing scope without creating or modifying an index.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.indexing.scope_planner import (
    GENERIC_LARGE_PYTHON_THRESHOLD,
    LARGE_MIN_PYTHON_FILES,
    SMALL_MAX_PYTHON_FILES,
    ScopePlan,
    ScopeRecommendation,
    classify_scale,
    plan_index_scope,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, text: str = "x = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_home_assistant_like(root: Path) -> None:
    """Create a minimal Home Assistant Core-like layout."""
    _write(root / "homeassistant" / "core.py")
    _write(root / "homeassistant" / "components" / "light" / "__init__.py")
    _write(root / "homeassistant" / "components" / "switch" / "__init__.py")
    _write(root / "homeassistant" / "helpers" / "event.py")
    _write(root / "tests" / "components" / "light" / "test_light.py")
    _write(root / "tests" / "helpers" / "test_event.py")
    _write(root / "README.md", "# Core\n")


def _make_generic_large(root: Path, python_files: int) -> None:
    """Create a generic (non-HA) repository with many Python files."""
    for i in range(python_files):
        _write(root / "pkg" / f"mod_{i}.py")
    _write(root / "lib" / "helper.py")


# ---------------------------------------------------------------------------
# Scale classification
# ---------------------------------------------------------------------------


def test_classify_scale_thresholds() -> None:
    assert classify_scale(0) == "small"
    assert classify_scale(SMALL_MAX_PYTHON_FILES - 1) == "small"
    assert classify_scale(SMALL_MAX_PYTHON_FILES) == "medium"
    assert classify_scale(LARGE_MIN_PYTHON_FILES - 1) == "medium"
    assert classify_scale(LARGE_MIN_PYTHON_FILES) == "large"


# ---------------------------------------------------------------------------
# Home Assistant Core detection + recommendation
# ---------------------------------------------------------------------------


def test_home_assistant_detected(tmp_path: Path) -> None:
    _make_home_assistant_like(tmp_path)
    plan = plan_index_scope(tmp_path)
    assert plan.detected_kind == "home-assistant-core"


def test_home_assistant_recommendation_excludes_exact_patterns(tmp_path: Path) -> None:
    _make_home_assistant_like(tmp_path)
    plan = plan_index_scope(tmp_path)
    assert plan.recommendation is not None
    assert plan.recommendation.scope_name == "home-assistant-core"
    assert plan.recommendation.exclude_patterns == (
        "homeassistant/components/**",
        "tests/components/**",
    )
    assert plan.recommendation.include_patterns == ()


def test_home_assistant_requires_all_marker_directories(tmp_path: Path) -> None:
    # Missing tests/components -> not Home Assistant Core.
    _write(tmp_path / "homeassistant" / "core.py")
    _write(tmp_path / "homeassistant" / "components" / "light" / "__init__.py")
    plan = plan_index_scope(tmp_path)
    assert plan.detected_kind is None


# ---------------------------------------------------------------------------
# Generic repositories
# ---------------------------------------------------------------------------


def test_generic_small_repo_no_recommendation(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.py")
    _write(tmp_path / "src" / "b.py")
    plan = plan_index_scope(tmp_path)
    assert plan.scale == "small"
    assert plan.detected_kind is None
    assert plan.recommendation is None


def test_generic_large_repo_no_fake_preset(tmp_path: Path) -> None:
    _make_generic_large(tmp_path, GENERIC_LARGE_PYTHON_THRESHOLD)
    plan = plan_index_scope(tmp_path)
    assert plan.scale == "large"
    assert plan.detected_kind is None
    # Advisory recommendation may be present but must NOT invent patterns.
    rec = plan.recommendation
    assert isinstance(rec, ScopeRecommendation)
    assert rec.scope_name is None
    assert rec.include_patterns == ()
    assert rec.exclude_patterns == ()
    # Heaviest subtrees are surfaced.
    assert plan.largest_subtrees
    assert plan.largest_subtrees[0].path == "pkg"


# ---------------------------------------------------------------------------
# Counts and determinism
# ---------------------------------------------------------------------------


def test_counts_are_accurate(tmp_path: Path) -> None:
    _write(tmp_path / "a.py")
    _write(tmp_path / "pkg" / "b.py")
    _write(tmp_path / "docs" / "guide.md", "# Guide\n")
    plan = plan_index_scope(tmp_path)
    assert plan.python_files == 2
    assert plan.total_files == 3


def test_largest_subtrees_deterministic_order(tmp_path: Path) -> None:
    plan_a = build_and_plan(tmp_path)
    plan_b = build_and_plan(tmp_path)
    assert plan_a.to_json_dict() == plan_b.to_json_dict()


def build_and_plan(root: Path) -> ScopePlan:
    _make_home_assistant_like(root)
    return plan_index_scope(root)


# ---------------------------------------------------------------------------
# Planner never creates an index
# ---------------------------------------------------------------------------


def test_planner_creates_no_index(tmp_path: Path) -> None:
    _make_home_assistant_like(tmp_path)
    plan_index_scope(tmp_path)
    sqlite_files = list(tmp_path.rglob("*.sqlite"))
    assert sqlite_files == []
    assert not (tmp_path / ".rsm").exists()


def test_invalid_repo_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plan_index_scope(tmp_path / "does-not-exist")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_human_output_includes_suggested_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_home_assistant_like(tmp_path)
    exit_code = main(["index", "plan", str(tmp_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "RSM index plan" in out
    assert "Detected project: home-assistant-core" in out
    assert "Suggested command:" in out
    assert "--exclude 'homeassistant/components/**'" in out
    assert "Scoped indexes are incomplete by design" in out


def test_cli_json_output_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_home_assistant_like(tmp_path)
    assert main(["index", "plan", str(tmp_path), "--json"]) == 0
    first = capsys.readouterr().out
    assert main(["index", "plan", str(tmp_path), "--json"]) == 0
    second = capsys.readouterr().out
    assert first == second
    payload = json.loads(first)
    assert payload["detected_kind"] == "home-assistant-core"
    assert payload["recommendation"]["exclude_patterns"] == [
        "homeassistant/components/**",
        "tests/components/**",
    ]


def test_cli_does_not_create_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "src" / "a.py")
    assert main(["index", "plan", str(tmp_path)]) == 0
    capsys.readouterr()
    assert list(tmp_path.rglob("*.sqlite")) == []
    assert not (tmp_path / ".rsm").exists()


def test_cli_invalid_path_fails_clearly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["index", "plan", str(tmp_path / "missing")])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "error:" in err
