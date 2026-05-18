"""Dataset parsing for deterministic retrieval benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoldTargets:
    """Gold retrieval targets for a benchmark task."""

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
        tasks.append(
            RetrievalTask(
                id=task_id,
                category=category,
                prompt=prompt,
                gold=GoldTargets(
                    files=_expect_string_list(gold_payload.get("files"), f"tasks[{index}].gold.files"),
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
