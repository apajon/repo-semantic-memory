"""Regression fixtures for path-role classification.

Tests assert deterministic role assignment for all path categories described in
the source-root classifier design: source roots (src/, top-level package with
marker, ROS 2 package.xml, pyproject.toml, setup.py, setup.cfg, __init__.py),
test, example, doc, ci, tool, config, generated artifacts, and safe false-positive
paths that must NOT be classified as generated.
"""

from __future__ import annotations

import pytest

from repo_semantic_memory.context.path_roles import (
    CI_ROLE,
    CONFIG_ROLE,
    DOC_ROLE,
    EXAMPLE_ROLE,
    GENERATED_ROLE,
    OTHER_ROLE,
    SOURCE_ROLE,
    TEST_ROLE,
    TOOL_ROLE,
    classify_path_role,
    infer_source_roots,
    is_generated_artifact_path,
)
from repo_semantic_memory.model import Entity, SourceRange, StableId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(path: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["file", path]),
        kind="module",
        name=path.rsplit("/", 1)[-1],
        qualified_name=path.replace("/", "."),
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def _classify(path: str, *, source_roots: tuple[str, ...] = ()) -> str:
    return classify_path_role(path=path, source_roots=source_roots)


# ---------------------------------------------------------------------------
# infer_source_roots
# ---------------------------------------------------------------------------


class TestInferSourceRoots:
    def test_src_layout(self) -> None:
        entities = [_entity("src/pkg_a/module.py")]
        roots = infer_source_roots(entities)
        assert "src" in roots

    def test_package_xml_marker(self) -> None:
        entities = [_entity("lifecore_state/package.xml"), _entity("lifecore_state/module.py")]
        roots = infer_source_roots(entities)
        assert "lifecore_state" in roots

    def test_pyproject_toml_marker(self) -> None:
        entities = [_entity("pkg_pyproject/pyproject.toml"), _entity("pkg_pyproject/mod.py")]
        roots = infer_source_roots(entities)
        assert "pkg_pyproject" in roots

    def test_setup_py_marker(self) -> None:
        entities = [_entity("pkg_setup/setup.py"), _entity("pkg_setup/mod.py")]
        roots = infer_source_roots(entities)
        assert "pkg_setup" in roots

    def test_setup_cfg_marker(self) -> None:
        entities = [_entity("pkg_setupcfg/setup.cfg"), _entity("pkg_setupcfg/mod.py")]
        roots = infer_source_roots(entities)
        assert "pkg_setupcfg" in roots

    def test_init_py_package_root(self) -> None:
        entities = [_entity("pkg_b/__init__.py"), _entity("pkg_b/core.py")]
        roots = infer_source_roots(entities)
        assert "pkg_b" in roots

    def test_nested_test_init_not_promoted(self) -> None:
        entities = [_entity("pkg_core/tests/__init__.py")]
        roots = infer_source_roots(entities)
        assert "pkg_core/tests" not in roots

    def test_common_source_root_names(self) -> None:
        for root in ("packages", "libs", "modules"):
            entities = [_entity(f"{root}/foo/module.py")]
            roots = infer_source_roots(entities)
            assert root in roots

    def test_output_is_sorted_and_deterministic(self) -> None:
        entities = [
            _entity("pkg_b/__init__.py"),
            _entity("src/mod.py"),
            _entity("lifecore_state/package.xml"),
        ]
        first = infer_source_roots(entities)
        second = infer_source_roots(list(reversed(entities)))
        assert first == second
        assert list(first) == sorted(first)


# ---------------------------------------------------------------------------
# classify_path_role — source variants
# ---------------------------------------------------------------------------


class TestClassifySourceRole:
    def test_src_layout_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("src/pkg_a/module.py")])
        assert _classify("src/pkg_a/module.py", source_roots=roots) == SOURCE_ROLE

    def test_top_level_package_root_with_init_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_b/__init__.py")])
        assert _classify("pkg_b/core.py", source_roots=roots) == SOURCE_ROLE

    def test_ros_package_xml_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("lifecore_state/package.xml")])
        assert _classify("lifecore_state/state_component.py", source_roots=roots) == SOURCE_ROLE

    def test_pyproject_toml_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_pyproject/pyproject.toml")])
        assert _classify("pkg_pyproject/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_setup_py_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_setup/setup.py")])
        assert _classify("pkg_setup/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_setup_cfg_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_setupcfg/setup.cfg")])
        assert _classify("pkg_setupcfg/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_packages_common_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("packages/foo/mod.py")])
        assert _classify("packages/foo/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_libs_common_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("libs/bar/mod.py")])
        assert _classify("libs/bar/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_modules_common_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("modules/baz/mod.py")])
        assert _classify("modules/baz/mod.py", source_roots=roots) == SOURCE_ROLE


# ---------------------------------------------------------------------------
# classify_path_role — non-source roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # tests
        ("tests/test_core.py", TEST_ROLE),
        ("test/unit/test_utils.py", TEST_ROLE),
        # examples
        ("examples/example_usage.py", EXAMPLE_ROLE),
        ("example/demo.py", EXAMPLE_ROLE),
        # docs
        ("docs/guide.md", DOC_ROLE),
        ("doc/api.rst", DOC_ROLE),
        # ci
        (".github/workflows/ci.yml", CI_ROLE),
        (".gitlab/ci.yml", CI_ROLE),
        (".circleci/config.yml", CI_ROLE),
        ("ci/pipeline.yaml", CI_ROLE),
        # tools
        ("tools/codegen.py", TOOL_ROLE),
        ("scripts/release.sh", TOOL_ROLE),
        # config
        ("config/settings.yaml", CONFIG_ROLE),
        # other
        ("misc/last.py", OTHER_ROLE),
        ("README.md", OTHER_ROLE),
    ],
)
def test_path_roles_non_source(path: str, expected: str) -> None:
    assert _classify(path, source_roots=()) == expected


# ---------------------------------------------------------------------------
# classify_path_role — generated artifacts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "docs/_build/api.html",
        "_build/output.py",
        "dist/package-0.1.tar.gz",
        "build/lib/module.py",
        "htmlcov/index.html",
        ".pytest_cache/v/cache/nodeids",
        ".mypy_cache/3.12/module.json",
        ".ruff_cache/content",
        "mypackage.egg-info/PKG-INFO",
    ],
)
def test_generated_artifact_paths_classified_as_generated(path: str) -> None:
    assert _classify(path, source_roots=()) == GENERATED_ROLE


# ---------------------------------------------------------------------------
# is_generated_artifact_path — segment safety (false-positive guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/build_tools.py",
        "src/package/distances.py",
        "src/project/rebuilder.py",
        "tools/build_helper.py",
        "scripts/dist_check.sh",
    ],
)
def test_legitimate_paths_not_classified_as_generated(path: str) -> None:
    """Paths that merely contain build-related words must not be flagged as generated."""
    assert not is_generated_artifact_path(path)
    assert _classify(path, source_roots=("src",)) != GENERATED_ROLE


# ---------------------------------------------------------------------------
# PathRole literal coverage
# ---------------------------------------------------------------------------


def test_all_defined_roles_are_reachable() -> None:
    """Smoke test: every PathRole constant is reachable via classify_path_role."""
    roots = ("pkg_b",)
    role_samples = [
        ("pkg_b/core.py", SOURCE_ROLE),
        ("tests/test_x.py", TEST_ROLE),
        ("examples/demo.py", EXAMPLE_ROLE),
        ("docs/guide.md", DOC_ROLE),
        (".github/ci.yml", CI_ROLE),
        ("tools/gen.py", TOOL_ROLE),
        ("config/app.yaml", CONFIG_ROLE),
        ("dist/wheel.whl", GENERATED_ROLE),
        ("misc/other.py", OTHER_ROLE),
    ]
    for path, expected_role in role_samples:
        assert _classify(path, source_roots=roots) == expected_role, (
            f"{path!r} expected {expected_role!r}"
        )
