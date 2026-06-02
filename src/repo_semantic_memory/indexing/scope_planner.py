"""Advisory index scope planner.

Cheaply inspects a repository (a single filesystem walk, no parsing, no DB
writes) and recommends a safe indexing scope for large repositories such as
Home Assistant Core.  The planner is purely advisory: it never creates or
modifies an index and never silently applies exclusions.

Usage::

    plan = plan_index_scope("/path/to/repo")
    print(format_scope_plan(plan))          # human-readable text
    print(json.dumps(plan.to_json_dict()))  # machine-readable JSON

Heuristics are deterministic only.  The Home Assistant Core heuristic matches
the ``homeassistant/``, ``homeassistant/components/`` and ``tests/components/``
directory layout and recommends excluding the integration packages.  Generic
large Python repositories list their heaviest subtrees and advise manual
scoping without inventing exclude patterns.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from repo_semantic_memory.extractors.filesystem import (
    DOC_EXTENSIONS,
    MODULE_EXTENSIONS,
    _should_ignore_directory_name,
    _should_ignore_directory_path,
    should_index_repo_path,
)

# Scale classification thresholds (number of Python files).
SMALL_MAX_PYTHON_FILES = 1_000
LARGE_MIN_PYTHON_FILES = 10_000
# A generic repository is considered "large" (and worth scoping advice) once it
# reaches the large-scale Python-file threshold.
GENERIC_LARGE_PYTHON_THRESHOLD = LARGE_MIN_PYTHON_FILES
# Maximum number of subtrees to surface in plan output.
MAX_LARGEST_SUBTREES = 10

_INDEXABLE_EXTENSIONS = MODULE_EXTENSIONS | DOC_EXTENSIONS

# Home Assistant Core detection / recommendation constants.
_HOME_ASSISTANT_KIND = "home-assistant-core"
_HOME_ASSISTANT_EXCLUDES: tuple[str, ...] = (
    "homeassistant/components/**",
    "tests/components/**",
)
_HOME_ASSISTANT_REASON = "Exclude integration packages to index the core architecture quickly."


@dataclass(frozen=True)
class SubtreeCount:
    """File and Python-file counts for one major subtree."""

    path: str
    files: int
    python_files: int

    def to_json_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "files": self.files,
            "python_files": self.python_files,
        }


@dataclass(frozen=True)
class ScopeRecommendation:
    """A recommended indexing scope.

    ``scope_name`` is ``None`` for generic advice (no named preset matched).
    ``include_patterns`` / ``exclude_patterns`` are never invented for generic
    repositories; they are only populated when a known project heuristic matched.
    """

    scope_name: str | None
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    reason: str
    suggested_command: str | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "scope_name": self.scope_name,
            "include_patterns": list(self.include_patterns),
            "exclude_patterns": list(self.exclude_patterns),
            "reason": self.reason,
            "suggested_command": self.suggested_command,
        }


@dataclass(frozen=True)
class ScopePlan:
    """Advisory plan describing repository scale and a recommended scope."""

    repo_root: str
    detected_kind: str | None
    scale: str
    total_files: int
    python_files: int
    largest_subtrees: tuple[SubtreeCount, ...] = field(default_factory=tuple)
    recommendation: ScopeRecommendation | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "detected_kind": self.detected_kind,
            "scale": self.scale,
            "total_files": self.total_files,
            "python_files": self.python_files,
            "largest_subtrees": [s.to_json_dict() for s in self.largest_subtrees],
            "recommendation": (
                self.recommendation.to_json_dict() if self.recommendation is not None else None
            ),
        }


def classify_scale(python_files: int) -> str:
    """Classify a repository as ``small``, ``medium``, or ``large``."""
    if python_files < SMALL_MAX_PYTHON_FILES:
        return "small"
    if python_files < LARGE_MIN_PYTHON_FILES:
        return "medium"
    return "large"


def _subtree_key(rel_path: str) -> str:
    """Group a repo-relative file path into a major subtree key.

    Uses the first two path segments when available (e.g.
    ``homeassistant/components``), otherwise the single top-level segment.
    Files directly at the repository root are grouped under ``"(root)"``.
    """
    parts = rel_path.split("/")
    if len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}"
    if len(parts) == 2:
        return parts[0]
    return "(root)"


def _detect_home_assistant_core(root: Path) -> bool:
    """Deterministic Home Assistant Core layout detection."""
    return (
        (root / "homeassistant").is_dir()
        and (root / "homeassistant" / "components").is_dir()
        and (root / "tests" / "components").is_dir()
    )


def _scan_counts(root: Path) -> tuple[int, int, dict[str, list[int]]]:
    """Cheaply walk the repository counting indexable files.

    Returns ``(total_files, python_files, subtree_counts)`` where
    ``subtree_counts`` maps a subtree key to ``[files, python_files]``.  No file
    contents are read and no entities are constructed.
    """
    total_files = 0
    python_files = 0
    subtrees: dict[str, list[int]] = {}
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        dirnames[:] = [
            name
            for name in dirnames
            if not _should_ignore_directory_name(name)
            and not _should_ignore_directory_path(current_dir / name, root)
        ]
        for filename in filenames:
            suffix = Path(filename).suffix.lower()
            if suffix not in _INDEXABLE_EXTENSIONS:
                continue
            rel_path = (current_dir / filename).relative_to(root).as_posix()
            if not should_index_repo_path(root, rel_path):
                continue
            is_python = suffix in MODULE_EXTENSIONS
            total_files += 1
            if is_python:
                python_files += 1
            bucket = subtrees.setdefault(_subtree_key(rel_path), [0, 0])
            bucket[0] += 1
            if is_python:
                bucket[1] += 1
    return total_files, python_files, subtrees


def _largest_subtrees(subtrees: dict[str, list[int]]) -> tuple[SubtreeCount, ...]:
    """Return the heaviest subtrees in deterministic order."""
    ordered = sorted(
        (
            SubtreeCount(path=key, files=counts[0], python_files=counts[1])
            for key, counts in subtrees.items()
        ),
        key=lambda s: (-s.python_files, -s.files, s.path),
    )
    return tuple(ordered[:MAX_LARGEST_SUBTREES])


def _suggested_command(repo_root: str, exclude_patterns: tuple[str, ...]) -> str:
    parts = ["rsm", "index", repo_root]
    for pattern in exclude_patterns:
        parts.extend(["--exclude", pattern])
    return " ".join(shlex.quote(part) for part in parts)


def _build_recommendation(
    *,
    repo_root: str,
    detected_kind: str | None,
    scale: str,
    largest_subtrees: tuple[SubtreeCount, ...],
) -> ScopeRecommendation | None:
    """Build an advisory recommendation from deterministic heuristics."""
    if detected_kind == _HOME_ASSISTANT_KIND:
        return ScopeRecommendation(
            scope_name=_HOME_ASSISTANT_KIND,
            include_patterns=(),
            exclude_patterns=_HOME_ASSISTANT_EXCLUDES,
            reason=_HOME_ASSISTANT_REASON,
            suggested_command=_suggested_command(repo_root, _HOME_ASSISTANT_EXCLUDES),
        )
    if scale == "large":
        # Generic large repository: advise manual scoping without inventing
        # exclude patterns for an unknown project layout.
        heaviest = ", ".join(s.path for s in largest_subtrees[:3])
        reason = (
            "Large Python repository. Consider scoping indexing manually with --include / --exclude"
        )
        if heaviest:
            reason += f"; heaviest subtrees: {heaviest}"
        reason += "."
        return ScopeRecommendation(
            scope_name=None,
            include_patterns=(),
            exclude_patterns=(),
            reason=reason,
            suggested_command=None,
        )
    return None


def plan_index_scope(repo_root: Path | str) -> ScopePlan:
    """Inspect ``repo_root`` cheaply and produce an advisory :class:`ScopePlan`.

    Raises:
        ValueError: If ``repo_root`` does not exist or is not a directory.
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")

    detected_kind = _HOME_ASSISTANT_KIND if _detect_home_assistant_core(root) else None
    total_files, python_files, subtrees = _scan_counts(root)
    scale = classify_scale(python_files)
    largest = _largest_subtrees(subtrees)
    recommendation = _build_recommendation(
        repo_root=str(root),
        detected_kind=detected_kind,
        scale=scale,
        largest_subtrees=largest,
    )
    return ScopePlan(
        repo_root=str(root),
        detected_kind=detected_kind,
        scale=scale,
        total_files=total_files,
        python_files=python_files,
        largest_subtrees=largest,
        recommendation=recommendation,
    )


def format_scope_plan(plan: ScopePlan) -> str:
    """Render a deterministic human-readable summary of a :class:`ScopePlan`."""
    lines: list[str] = []
    lines.append("RSM index plan")
    lines.append("")
    lines.append(f"Repository: {plan.repo_root}")
    lines.append(f"Detected project: {plan.detected_kind or 'none'}")
    lines.append(f"Scale: {plan.scale}")
    lines.append(f"Files: {plan.total_files}")
    lines.append(f"Python files: {plan.python_files}")

    if plan.largest_subtrees:
        lines.append("")
        lines.append("Largest subtrees:")
        width = max(len(s.path) for s in plan.largest_subtrees)
        for subtree in plan.largest_subtrees:
            lines.append(
                f"  {subtree.path.ljust(width)}  files={subtree.files} "
                f"python={subtree.python_files}"
            )

    recommendation = plan.recommendation
    if recommendation is None:
        lines.append("")
        lines.append("Recommended scope: none")
        lines.append("Reason: repository is small enough to index fully.")
    elif recommendation.scope_name is not None:
        lines.append("")
        lines.append(f"Recommended scope: {recommendation.scope_name}")
        lines.append(f"Reason: {recommendation.reason}")
        if recommendation.suggested_command:
            lines.append("")
            lines.append("Suggested command:")
            lines.append(f"  {recommendation.suggested_command}")
    else:
        lines.append("")
        lines.append("Recommended scope: manual scoping advised")
        lines.append(f"Reason: {recommendation.reason}")

    lines.append("")
    lines.append("Warning:")
    lines.append(
        "  Scoped indexes are incomplete by design. Use full indexing for "
        "integration-specific tasks."
    )
    return "\n".join(lines)
