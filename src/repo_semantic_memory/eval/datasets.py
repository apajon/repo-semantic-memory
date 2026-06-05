"""Dataset parsing for deterministic retrieval benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BenchmarkMode = Literal["ci_fixture", "manual_external"]
_VALID_MODES: frozenset[str] = frozenset({"ci_fixture", "manual_external"})
_EXPECTED_KEYS: frozenset[str] = frozenset(
    {"central_files", "support_files", "test_files", "forbidden_files"}
)


@dataclass(frozen=True)
class GoldTargets:
    """Gold retrieval targets for a benchmark task.

    ``files`` entries must be repository-relative POSIX paths.
    """

    files: tuple[str, ...]
    symbols: tuple[str, ...]
    invariants: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalTask:
    """Single retrieval benchmark task."""

    id: str
    category: str
    prompt: str
    gold: GoldTargets


@dataclass(frozen=True)
class RetrievalDataset:
    """Collection of deterministic benchmark tasks."""

    tasks: tuple[RetrievalTask, ...]


def load_retrieval_dataset(path: Path | str) -> RetrievalDataset:
    """Load retrieval tasks from a constrained YAML dataset file."""
    dataset_path = Path(path)
    content = dataset_path.read_text(encoding="utf-8")
    parsed = _parse_yaml_mapping(content)
    tasks_payload = parsed.get("tasks")
    if not isinstance(tasks_payload, list):
        raise ValueError(f"Dataset {dataset_path} must define a top-level 'tasks' list")

    tasks: list[RetrievalTask] = []
    for index, task_payload in enumerate(tasks_payload):
        if not isinstance(task_payload, dict):
            raise ValueError(f"Task #{index + 1} must be a mapping")
        task_id = _expect_string(task_payload.get("id"), f"tasks[{index}].id")
        category = _expect_string(task_payload.get("category"), f"tasks[{index}].category")
        prompt = _expect_string(task_payload.get("prompt"), f"tasks[{index}].prompt")
        gold_payload = task_payload.get("gold")
        if not isinstance(gold_payload, dict):
            raise ValueError(f"tasks[{index}].gold must be a mapping")
        gold_files = _expect_string_list(gold_payload.get("files"), f"tasks[{index}].gold.files")
        for gold_file in gold_files:
            _validate_gold_file_path(gold_file, f"tasks[{index}].gold.files")
        tasks.append(
            RetrievalTask(
                id=task_id,
                category=category,
                prompt=prompt,
                gold=GoldTargets(
                    files=gold_files,
                    symbols=_expect_string_list(
                        gold_payload.get("symbols"), f"tasks[{index}].gold.symbols"
                    ),
                    invariants=_expect_string_list(
                        gold_payload.get("invariants"),
                        f"tasks[{index}].gold.invariants",
                    ),
                ),
            )
        )
    if not tasks:
        raise ValueError(f"Dataset {dataset_path} contains no tasks")
    return RetrievalDataset(tasks=tuple(tasks))


def _expect_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _expect_string_list(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return tuple(value)


def _validate_gold_file_path(path: str, field: str) -> None:
    if path.startswith("/") or path.startswith("./"):
        raise ValueError(f"{field} must contain repository-relative POSIX paths: {path}")
    if "\\" in path:
        raise ValueError(f"{field} must use POSIX separators ('/'): {path}")


def _parse_yaml_mapping(content: str) -> dict[str, object]:
    """Parse a minimal YAML subset used by retrieval benchmark datasets."""
    root: dict[str, object] = {}
    lines = _clean_lines(content)
    if not lines:
        return root
    if lines[0] != "tasks:":
        raise ValueError("Dataset YAML must start with 'tasks:'")
    tasks: list[dict[str, object]] = []
    root["tasks"] = tasks

    index = 1
    while index < len(lines):
        line = lines[index]
        if not line.startswith("  - "):
            raise ValueError(f"Expected task entry at line: {line}")
        task_payload: dict[str, object] = {}
        _parse_inline_key_value(task_payload, line[4:])
        index += 1
        while index < len(lines) and not lines[index].startswith("  - "):
            detail = lines[index]
            if detail.startswith("    gold:"):
                index = _parse_gold(lines, index, task_payload)
                continue
            if not detail.startswith("    "):
                raise ValueError(f"Invalid indentation in task entry: {detail}")
            _parse_inline_key_value(task_payload, detail[4:])
            index += 1
        tasks.append(task_payload)
    return root


def _parse_gold(lines: list[str], index: int, task_payload: dict[str, object]) -> int:
    gold: dict[str, object] = {}
    task_payload["gold"] = gold
    index += 1
    while index < len(lines):
        line = lines[index]
        if line.startswith("  - ") or line.startswith("    ") and not line.startswith("      "):
            break
        if not line.startswith("      "):
            raise ValueError(f"Invalid gold indentation: {line}")
        if not line.endswith(":"):
            raise ValueError(f"Gold section key must end with ':': {line}")
        list_key = line[6:-1].strip()
        values: list[str] = []
        index += 1
        while index < len(lines):
            list_line = lines[index]
            if list_line.startswith("        - "):
                values.append(_parse_scalar(list_line[10:]))
                index += 1
                continue
            break
        gold[list_key] = values
    return index


def _parse_inline_key_value(target: dict[str, object], line: str) -> None:
    if ":" not in line:
        raise ValueError(f"Expected key/value pair, got: {line}")
    key, raw = line.split(":", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"Missing key in line: {line}")
    target[key] = _parse_scalar(raw.strip())


def _parse_scalar(raw: str) -> str:
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    return raw


def _clean_lines(content: str) -> list[str]:
    lines: list[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.rstrip()
        if not stripped:
            continue
        if stripped.lstrip().startswith("#"):
            continue
        lines.append(stripped)
    return lines


# ---------------------------------------------------------------------------
# 59.1 — Benchmark harness schema (enriched, backward-compatible)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BenchmarkExpected:
    """Expected and forbidden file sets for a benchmark case (59.0 schema).

    All paths are repository-relative POSIX paths.
    """

    central_files: tuple[str, ...]
    support_files: tuple[str, ...]
    test_files: tuple[str, ...]
    forbidden_files: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkCase:
    """Single benchmark case in the 59.0 harness schema."""

    id: str
    fixture: str
    query: str
    expected: BenchmarkExpected
    tags: tuple[str, ...]
    notes: str
    mode: str  # "ci_fixture" | "manual_external"


@dataclass(frozen=True)
class BenchmarkDataset:
    """Collection of benchmark cases in the 59.0 harness schema."""

    cases: tuple[BenchmarkCase, ...]


def load_benchmark_dataset(path: Path | str) -> BenchmarkDataset:
    """Load benchmark cases from a YAML dataset file (59.0 enriched schema)."""
    dataset_path = Path(path)
    content = dataset_path.read_text(encoding="utf-8")
    parsed = _parse_benchmark_yaml_mapping(content, dataset_path)
    cases_payload = parsed.get("tasks")
    if not isinstance(cases_payload, list):
        raise ValueError(f"Dataset {dataset_path} must define a top-level 'tasks' list")

    cases: list[BenchmarkCase] = []
    for index, case_payload in enumerate(cases_payload):
        if not isinstance(case_payload, dict):
            raise ValueError(f"Case #{index + 1} must be a mapping")
        case = _build_benchmark_case(case_payload, index, dataset_path)
        cases.append(case)

    if not cases:
        raise ValueError(f"Dataset {dataset_path} contains no cases")
    return BenchmarkDataset(cases=tuple(cases))


def _build_benchmark_case(
    payload: dict[str, object],
    index: int,
    dataset_path: Path,
) -> BenchmarkCase:
    prefix = f"tasks[{index}]"

    case_id = _expect_string(payload.get("id"), f"{prefix}.id")
    fixture = _expect_string(payload.get("fixture"), f"{prefix}.fixture")
    query = _expect_string(payload.get("query"), f"{prefix}.query")
    notes = _expect_string_allow_empty(payload.get("notes"), f"{prefix}.notes")

    mode_raw = _expect_string(payload.get("mode"), f"{prefix}.mode")
    if mode_raw not in _VALID_MODES:
        raise ValueError(f"{prefix}.mode must be one of {sorted(_VALID_MODES)}, got: {mode_raw!r}")

    tags = _expect_string_list(payload.get("tags"), f"{prefix}.tags")

    expected_payload = payload.get("expected")
    if not isinstance(expected_payload, dict):
        raise ValueError(f"{prefix}.expected must be a mapping")

    central_files = _expect_string_list(
        expected_payload.get("central_files"), f"{prefix}.expected.central_files"
    )
    if not central_files:
        raise ValueError(f"{prefix}.expected.central_files must be non-empty")

    support_files = _expect_string_list(
        expected_payload.get("support_files"), f"{prefix}.expected.support_files"
    )
    test_files = _expect_string_list(
        expected_payload.get("test_files"), f"{prefix}.expected.test_files"
    )
    forbidden_files = _expect_string_list(
        expected_payload.get("forbidden_files"), f"{prefix}.expected.forbidden_files"
    )

    all_files: list[tuple[str, str]] = []
    all_files.extend((f, f"{prefix}.expected.central_files") for f in central_files)
    all_files.extend((f, f"{prefix}.expected.support_files") for f in support_files)
    all_files.extend((f, f"{prefix}.expected.test_files") for f in test_files)
    all_files.extend((f, f"{prefix}.expected.forbidden_files") for f in forbidden_files)
    for file_path, field in all_files:
        _validate_benchmark_file_path(file_path, field)

    expected = BenchmarkExpected(
        central_files=central_files,
        support_files=support_files,
        test_files=test_files,
        forbidden_files=forbidden_files,
    )
    return BenchmarkCase(
        id=case_id,
        fixture=fixture,
        query=query,
        expected=expected,
        tags=tags,
        notes=notes,
        mode=mode_raw,
    )


def _expect_string_allow_empty(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _validate_benchmark_file_path(path: str, field: str) -> None:
    """Reject absolute paths, backslashes, and parent-traversal segments."""
    if path.startswith("/"):
        raise ValueError(f"{field} must be a repository-relative path, got absolute: {path!r}")
    if "\\" in path:
        raise ValueError(f"{field} must use POSIX separators ('/'), got: {path!r}")
    segments = path.split("/")
    if ".." in segments:
        raise ValueError(f"{field} must not contain parent-traversal ('..'), got: {path!r}")


# ---------------------------------------------------------------------------
# 59.1 — Enriched YAML parser for the 59.0 benchmark schema
# ---------------------------------------------------------------------------


def _parse_benchmark_yaml_mapping(content: str, dataset_path: Path) -> dict[str, object]:
    """Parse the enriched 59.0 benchmark YAML schema.

    Handles ``expected:`` (with fixed sub-keys), ``tags:`` (list), and
    ``notes: >`` (folded block scalar) in addition to inline key/value pairs.
    """
    root: dict[str, object] = {}
    lines = _clean_lines(content)
    if not lines:
        return root
    if lines[0] != "tasks:":
        raise ValueError("Dataset YAML must start with 'tasks:'")
    tasks: list[dict[str, object]] = []
    root["tasks"] = tasks

    index = 1
    while index < len(lines):
        line = lines[index]
        if not line.startswith("  - "):
            raise ValueError(f"Expected task entry at line: {line}")
        task_payload: dict[str, object] = {}
        _parse_inline_key_value(task_payload, line[4:])
        index += 1
        while index < len(lines) and not lines[index].startswith("  - "):
            detail = lines[index]
            if detail.startswith("    expected:"):
                index = _parse_expected(lines, index, task_payload)
                continue
            if detail.startswith("    tags:"):
                index = _parse_tags_list(lines, index, task_payload)
                continue
            if detail.startswith("    notes:"):
                index = _parse_folded_notes(lines, index, task_payload)
                continue
            if not detail.startswith("    "):
                raise ValueError(f"Invalid indentation in task entry: {detail}")
            _parse_inline_key_value(task_payload, detail[4:])
            index += 1
        tasks.append(task_payload)
    return root


def _parse_expected(lines: list[str], index: int, task_payload: dict[str, object]) -> int:
    """Parse the ``expected:`` block with fixed sub-keys.

    Each sub-key is a list of strings at the next indentation level.
    Unknown sub-keys are rejected.
    """
    expected: dict[str, object] = {}
    task_payload["expected"] = expected
    index += 1
    while index < len(lines):
        line = lines[index]
        # Stop at next task entry or non-expected-line
        if line.startswith("  - "):
            break
        if line.startswith("    ") and not line.startswith("      "):
            # This is a sibling key (fixture:, query:, tags:, notes:, etc.) — stop
            break
        if not line.startswith("      "):
            raise ValueError(f"Invalid expected indentation: {line}")
        if not line.endswith(":"):
            raise ValueError(f"Expected section key must end with ':': {line}")
        list_key = line[6:-1].strip()
        if list_key not in _EXPECTED_KEYS:
            raise ValueError(
                f"Unknown expected key {list_key!r}; expected one of {sorted(_EXPECTED_KEYS)}"
            )
        values: list[str] = []
        index += 1
        while index < len(lines):
            list_line = lines[index]
            if list_line.startswith("        - "):
                values.append(_parse_scalar(list_line[10:]))
                index += 1
                continue
            break
        expected[list_key] = values
    return index


def _parse_tags_list(lines: list[str], index: int, task_payload: dict[str, object]) -> int:
    """Parse a ``tags:`` block as a list of string scalars."""
    tags: list[str] = []
    index += 1
    while index < len(lines):
        line = lines[index]
        if line.startswith("  - ") or line.startswith("    ") and not line.startswith("      "):
            break
        if line.startswith("      - "):
            tags.append(_parse_scalar(line[8:]))
            index += 1
            continue
        break
    task_payload["tags"] = tags
    return index


def _parse_folded_notes(lines: list[str], index: int, task_payload: dict[str, object]) -> int:
    """Parse a ``notes: >`` folded block scalar.

    If the scalar after ``:`` is ``>``, consume indented continuation lines,
    join them with spaces, and store.
    If the scalar is a normal quoted/unquoted string, store it directly
    (handled by the caller via ``_parse_inline_key_value`` fallback, but this
    function handles the ``>`` case).
    """
    line = lines[index]
    raw = line.split(":", 1)[1].strip()
    if raw != ">":
        # Not a folded scalar — treat as inline
        task_payload["notes"] = _parse_scalar(raw) if raw else ""
        return index + 1

    # Consume continuation lines (must be more indented than the key)
    parts: list[str] = []
    index += 1
    while index < len(lines):
        cont_line = lines[index]
        if (
            cont_line.startswith("  - ")
            or cont_line.startswith("    ")
            and not cont_line.startswith("      ")
        ):
            break
        if cont_line.startswith("      "):
            parts.append(cont_line[6:])
            index += 1
            continue
        break
    task_payload["notes"] = " ".join(parts)
    return index
