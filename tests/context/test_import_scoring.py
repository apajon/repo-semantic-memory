"""Tests for deterministic import classification and weights."""

from __future__ import annotations

from repo_semantic_memory.context.import_scoring import (
    IMPORT_CLASS_WEIGHTS,
    build_import_scoring_context,
    classify_import,
)
from repo_semantic_memory.model import Entity, SourceRange, StableId

_PRIMARY_STRUCTURAL_RELATION_WEIGHT = 0.9


def _module(path: str, qname: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["python", path, "module", qname]),
        kind="module",
        name=qname.rsplit(".", 1)[-1],
        qualified_name=qname,
        source_range=SourceRange(path=path, start_line=1, end_line=5),
    )


def test_stdlib_import_classified_as_stdlib() -> None:
    context = build_import_scoring_context([_module("src/pkg/core.py", "pkg.core")])

    assert classify_import("pathlib.Path", context=context) == "stdlib"
    assert classify_import("json", context=context) == "stdlib"


def test_common_third_party_import_classified_as_common() -> None:
    context = build_import_scoring_context([_module("src/pkg/core.py", "pkg.core")])

    assert classify_import("numpy", context=context) == "third_party_common"
    assert classify_import("pytest", context=context) == "third_party_common"


def test_unknown_third_party_import_classified_as_unknown_third_party() -> None:
    context = build_import_scoring_context([_module("src/pkg/core.py", "pkg.core")])

    assert classify_import("vendor_package.feature", context=context) == "third_party_unknown"


def test_local_package_absolute_import_classified_as_local_package() -> None:
    context = build_import_scoring_context(
        [
            _module(
                "src/repo_semantic_memory/context/pack_builder.py",
                "repo_semantic_memory.context.pack_builder",
            )
        ]
    )

    assert (
        classify_import(
            "repo_semantic_memory.context.pack_builder.build_context_pack", context=context
        )
        == "local_package"
    )


def test_relative_import_classified_as_relative_local() -> None:
    context = build_import_scoring_context([_module("src/pkg/core.py", "pkg.core")])

    assert classify_import(".helpers.Helper", context=context) == "relative_local"


def test_test_source_import_classified_as_test_local() -> None:
    context = build_import_scoring_context([_module("src/pkg/core.py", "pkg.core")])

    assert (
        classify_import("pkg.core.Core", source_path="tests/test_core.py", context=context)
        == "test_local"
    )


def test_fallback_classification_is_deterministic() -> None:
    first = classify_import("not_a_known_dependency.plugin")
    second = classify_import("not_a_known_dependency.plugin")

    assert first == second == "third_party_unknown"


def test_import_weights_keep_local_imports_below_primary_structural_relations() -> None:
    assert IMPORT_CLASS_WEIGHTS["local_package"] > IMPORT_CLASS_WEIGHTS["third_party_common"]
    assert IMPORT_CLASS_WEIGHTS["local_package"] < _PRIMARY_STRUCTURAL_RELATION_WEIGHT
    assert IMPORT_CLASS_WEIGHTS["stdlib"] == 0.0
