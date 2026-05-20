"""Export semantic memory as portable `.ai/` directory for agent consumption.

Generated files are compact, deterministic (except timestamps), and carry
provenance metadata. Source of truth always remains code/docs/tests/git.

License: Apache-2.0
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repo_semantic_memory.context.repo_map import build_repo_map_markdown
from repo_semantic_memory.memory.ecs_components import infer_semantic_components
from repo_semantic_memory.model import Entity, Relation, SemanticComponent
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, PACKAGE_VERSION, SCHEMA_VERSION

# Budget for embedded repo map in .ai/ export (compact, not full budget)
_REPO_MAP_BUDGET = 8000

_AGENT_COMMANDS_TEMPLATE = """\
# AGENT_COMMANDS — RSM command guide for coding agents

> **WARNING**: Generated artifact. Source of truth is always code, docs, tests, and git history.
> Regenerate with: `rsm export-ai --db .rsm/index.sqlite --out .ai --force`

## Overview

These are the canonical RSM commands for coding agents. Load this file early in any
RSM-assisted task to avoid redundant full-file reads and context waste.

---

## When to run each command

### `rsm index`

Run after cloning or after significant structural changes (new modules, renamed files,
moved packages). This rebuilds the SQLite index from source.

```bash
uv run rsm index . --db .rsm/index.sqlite
```

Run with `--with-git` to attach last-commit dates to entities:

```bash
uv run rsm index . --db .rsm/index.sqlite --with-git
```

### `rsm repo-map`

Run to get a compact structural overview of the repository. Use as orientation before
editing unfamiliar code.

```bash
uv run rsm repo-map --db .rsm/index.sqlite
```

### `rsm pack`

Run to build a token-budgeted context pack for a specific task. Pass a task prompt to
focus the pack on relevant symbols and files.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "describe the task here" --budget 8000
```

Use `--explain-ranking` to see why entities were selected:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 8000 --explain-ranking
```

### `--profile agent_brief`

Use when token budget is very tight or the task is narrow. Suppresses unresolved
imports, low-confidence components, and ranking detail. Smallest output.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 4000 --profile agent_brief
```

### `--profile agent_debug`

Use when diagnosing unexpected pack output or ranking anomalies. Includes ranking
breakdown and compact score reasons. Larger output — use with a generous budget.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 12000 --profile agent_debug
```

---

## When to use each `.ai/` file

### `symbols.yaml`

Use to resolve entity IDs, source file paths, and line numbers before editing.
Prefer this over grepping for class/function names directly.

### `relations.yaml`

Use to understand structural dependencies: which modules import which, which classes
inherit from which, which functions are tested by which test files. Use before
refactoring to understand downstream impact.

### `components.yaml`

Use to identify semantic roles: PublicAPI, EntryPoint, TestTarget, TestFile, etc.
All components are `inferred` unless explicitly marked `confirmed`. Do not treat
inferred components as confirmed claims.

---

## When to regenerate `.ai/`

Regenerate after:
- indexing adds new symbols (new modules, classes, functions)
- files are renamed, moved, or deleted
- significant refactors that change structural relations
- public API changes (exports, `__init__.py` edits)

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

Check `INDEX.yaml` → `generated_at` against recent git commits to assess staleness.

---

## What NOT to do

- **Do not treat `.ai/` files as source truth.** They are derived snapshots.
  Always verify against the actual source files cited in symbols.yaml.

- **Do not read full source files before checking the context pack.**
  Run `rsm pack` first; it cites the relevant sections. Read only what is cited.

- **Do not trust inferred components as confirmed claims.**
  `components.yaml` entries with `status: inferred` are heuristic guesses.
  Confirm by reading the cited source.

- **Do not use stale `.ai/` without checking the timestamp.**
  Check `INDEX.yaml` → `generated_at`. If the repo has changed significantly
  since that timestamp, regenerate before relying on any `.ai/` file.

- **Do not ignore citations when editing code.**
  Every symbol in `symbols.yaml` has a `source:` citation. Use it.
  Do not guess file locations.

- **Do not claim token savings are quality unless coverage is preserved.**
  A smaller context pack is only better if it still covers the gold files and
  symbols for the task. Use `rsm eval compare` to measure coverage, not just size.

---

## Canonical workflows

### 1. New task

```
1. uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000
2. Inspect cited files and symbols in the pack output.
3. Edit only the cited source files.
```

Do not load full source files before running `rsm pack`.

### 2. Large repo orientation

```
1. Load .ai/INDEX.yaml — confirm generation timestamp and version.
2. Load .ai/repo_map.md — structural overview at low token cost.
3. Load .ai/symbols.yaml — only if resolving a specific entity.
4. Load .ai/relations.yaml — only if tracing dependencies.
```

Do not load all `.ai/` files at once.

### 3. Public API task

```
1. uv run rsm pack --db .rsm/index.sqlite --task "public API for <module>" --budget 8000
2. Inspect __init__.py exports cited in pack output.
3. Inspect public import tests if listed in relations.yaml.
```

### 4. Debug regression

```
1. uv run rsm pack --db .rsm/index.sqlite --task "<failing test or symptom>" --budget 8000
2. Inspect tests and related source cited in pack output.
3. Use --profile agent_debug if ranking seems off.
```

### 5. Documentation task

```
1. uv run rsm pack --db .rsm/index.sqlite --task "<doc topic>" --budget 8000
2. Inspect doc sections cited in pack output.
3. Do not read full doc files before checking cited sections.
```

### 6. After code structure change

```
1. uv run rsm index . --db .rsm/index.sqlite
2. uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
   (only if this project commits .ai/ snapshots)
3. Verify INDEX.yaml → generated_at is current.
```

---

## License

Apache-2.0 — generated by `repo-semantic-memory`
"""

_README_TEMPLATE = """\
# .ai/ — Agent Semantic Memory

> **WARNING**: These files are generated artifacts. They may be stale.
> Source of truth is always the code, docs, tests, and git history.
> Regenerate with: `rsm export-ai --db .rsm/index.sqlite --out .ai`

## Purpose

This directory contains compact semantic memory files for coding agents.
It is NOT a human documentation replacement.

## Files

| File | Description |
|---|---|
| `INDEX.yaml` | Versions, source DB path, generation timestamp, entity/relation counts |
| `AGENT_COMMANDS.md` | Canonical command guide and workflows for coding agents |
| `repo_map.md` | Compact structural map of the repository |
| `symbols.yaml` | Stable entity IDs, kinds, names, and source locations |
| `relations.yaml` | Directed structural relations between entities |
| `components.yaml` | Inferred ECS-style semantic component labels (if present) |
| `invariants.yaml` | Inferred invariant entities (if present) |
| `context_policy.md` | How to use these files in agent context windows |

## Git behaviour

Projects may choose to commit generated `.ai/` outputs.
If committed, treat them as compiled semantic artifacts (like generated protobufs).
The `.rsm/` index (SQLite) must NOT be committed — it is local only.

## License

Generated by `repo-semantic-memory` — Apache-2.0
Source: https://github.com/apajon/repo-semantic-memory
"""

_CONTEXT_POLICY_TEMPLATE = """\
# Context Policy

This file describes how coding agents should use `.ai/` semantic memory files.

## Source of truth

Code, docs, tests, and git history are always authoritative.
These files are derived snapshots and may be stale.

## Recommended usage

1. Load `INDEX.yaml` to confirm generation timestamp and versions.
2. Load `repo_map.md` for structural orientation.
3. Load `symbols.yaml` to resolve entity IDs and source locations.
4. Load `relations.yaml` to understand structural dependencies.
5. Load `components.yaml` to identify semantic roles (if present).
6. Load `invariants.yaml` to understand declared invariants (if present).

## Budget guidance

Prefer loading only files relevant to the current task.
`repo_map.md` provides the broadest structural context at lowest token cost.
`symbols.yaml` and `relations.yaml` together provide full graph context.

## Compression profiles

`rsm repo-map` and `rsm pack` support deterministic profiles:

- `agent_brief`: smallest output, suppresses unresolved imports and low-signal detail.
- `agent_standard`: default balanced profile for most coding tasks.
- `agent_debug`: keeps ranking breakdown and compact score reasons for diagnostics.
- `human_review`: balanced for human PR/design review workflows.
- `ci_summary`: compact CI-oriented output with strict noise suppression.
- `full`: maximum verbosity while still avoiding source body dumps.

Profile controls include:

- max imports per module
- max components per entity
- unresolved import inclusion
- ranking breakdown inclusion
- low-confidence inferred component inclusion
- relation verbosity
- citation verbosity
- max related symbols
- max uncertainties
- compact score reason inclusion

Preservation rules always favor:

- direct task matches
- source citations
- explicit public exports
- high-confidence structural context
- selected implementation symbols

## Staleness

Check `INDEX.yaml` → `generated_at` field against recent git commits.
Regenerate when indexing adds new symbols or structural changes occur.

## License

Apache-2.0 — generated by `repo-semantic-memory`
"""


@dataclass(frozen=True)
class ExportResult:
    """Summary of a completed `.ai/` export operation."""

    output_dir: Path
    files_written: tuple[str, ...]
    files_skipped: tuple[str, ...]
    entity_count: int
    relation_count: int
    component_count: int
    invariant_count: int


@dataclass
class AiDirectoryExporter:
    """Exports indexed semantic data as a portable `.ai/` directory."""

    db_path: Path
    output_dir: Path
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    generated_at: str = ""

    def export(self, *, force: bool = False) -> ExportResult:
        """Write all `.ai/` files, respecting overwrite policy.

        Args:
            force: When True, overwrite existing generated files.
                   When False, skip files that already exist.

        Returns:
            ExportResult summarising what was written and skipped.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        components = infer_semantic_components(entities=self.entities, relations=self.relations)
        invariant_entities = [e for e in self.entities if e.kind == "invariant"]

        files_written: list[str] = []
        files_skipped: list[str] = []

        def _write(name: str, content: str) -> None:
            target = self.output_dir / name
            if target.exists() and not force:
                files_skipped.append(name)
                return
            target.write_text(content, encoding="utf-8")
            files_written.append(name)

        _write("README.md", _README_TEMPLATE)
        _write("AGENT_COMMANDS.md", _AGENT_COMMANDS_TEMPLATE)
        _write("context_policy.md", _CONTEXT_POLICY_TEMPLATE)
        _write("INDEX.yaml", self._build_index_yaml(components, invariant_entities))
        _write("repo_map.md", self._build_repo_map())
        _write("symbols.yaml", self._build_symbols_yaml())
        _write("relations.yaml", self._build_relations_yaml())

        if components:
            _write("components.yaml", self._build_components_yaml(components))
        if invariant_entities:
            _write("invariants.yaml", self._build_invariants_yaml(invariant_entities))

        return ExportResult(
            output_dir=self.output_dir,
            files_written=tuple(sorted(files_written)),
            files_skipped=tuple(sorted(files_skipped)),
            entity_count=len(self.entities),
            relation_count=len(self.relations),
            component_count=len(components),
            invariant_count=len(invariant_entities),
        )

    # ------------------------------------------------------------------
    # File content builders
    # ------------------------------------------------------------------

    def _build_index_yaml(
        self,
        components: Sequence[SemanticComponent],
        invariant_entities: Sequence[Entity],
    ) -> str:
        lines = [
            "# .ai/INDEX.yaml — semantic memory index manifest",
            "# WARNING: Generated file. Regenerate with: rsm export-ai",
            "# Apache-2.0 — repo-semantic-memory",
            "",
            f"generated_at: {self.generated_at!r}",
            f"source_db: {str(self.db_path)!r}",
            "",
            "versions:",
            f"  package_version: {PACKAGE_VERSION!r}",
            f"  schema_version: {SCHEMA_VERSION!r}",
            f"  context_pack_version: {CONTEXT_PACK_VERSION!r}",
            "",
            "counts:",
            f"  entities: {len(self.entities)}",
            f"  relations: {len(self.relations)}",
            f"  components: {len(components)}",
            f"  invariants: {len(invariant_entities)}",
        ]
        if self.metadata:
            lines += ["", "extraction_metadata:"]
            for key in sorted(self.metadata.keys()):
                value = self.metadata[key]
                lines.append(f"  {key}: {value!r}")
        lines.append("")
        return "\n".join(lines)

    def _build_repo_map(self) -> str:
        return build_repo_map_markdown(self.entities, self.relations, budget_chars=_REPO_MAP_BUDGET)

    def _build_symbols_yaml(self) -> str:
        lines = [
            "# .ai/symbols.yaml — entity symbol index",
            "# WARNING: Generated file. Regenerate with: rsm export-ai",
            "# Apache-2.0 — repo-semantic-memory",
            "",
            "symbols:",
        ]
        for entity in sorted(self.entities, key=lambda e: e.id.value):
            path = entity.source_range.path
            citation = f"{path}:{entity.source_range.start_line}"
            lines.append(f"  - id: {entity.id.value!r}")
            lines.append(f"    kind: {entity.kind!r}")
            lines.append(f"    name: {entity.name!r}")
            lines.append(f"    qualified_name: {entity.qualified_name!r}")
            lines.append(f"    source: {citation!r}")
            if entity.metadata.get("entity_type") == "doc_section":
                lines.append("    metadata:")
                for key in ("entity_type", "section_level", "heading", "anchor"):
                    value = entity.metadata.get(key)
                    if value is not None:
                        lines.append(f"      {key}: {value!r}")
        lines.append("")
        return "\n".join(lines)

    def _build_relations_yaml(self) -> str:
        lines = [
            "# .ai/relations.yaml — structural relation graph",
            "# WARNING: Generated file. Regenerate with: rsm export-ai",
            "# Apache-2.0 — repo-semantic-memory",
            "",
            "relations:",
        ]
        ordered = sorted(
            self.relations,
            key=lambda r: (r.kind, r.source_entity_id.value, r.target_entity_id.value),
        )
        for relation in ordered:
            lines.append(f"  - kind: {relation.kind!r}")
            lines.append(f"    source: {relation.source_entity_id.value!r}")
            lines.append(f"    target: {relation.target_entity_id.value!r}")
            if relation.evidence is not None:
                evidence_dict = relation.evidence.to_dict()
                citation = _evidence_citation(evidence_dict)
                if citation:
                    lines.append(f"    citation: {citation!r}")
        lines.append("")
        return "\n".join(lines)

    def _build_components_yaml(self, components: Sequence[SemanticComponent]) -> str:
        lines = [
            "# .ai/components.yaml — inferred ECS semantic component labels",
            "# WARNING: Generated file. Regenerate with: rsm export-ai",
            "# Apache-2.0 — repo-semantic-memory",
            "",
            "components:",
        ]
        ordered = sorted(
            components,
            key=lambda c: (c.component_type, c.entity_id.value),
        )
        for component in ordered:
            lines.append(f"  - component_type: {component.component_type!r}")
            lines.append(f"    entity_id: {component.entity_id.value!r}")
            lines.append(f"    status: {component.status!r}")
            lines.append(f"    confidence: {component.confidence:.2f}")
            if component.inference_note:
                lines.append(f"    note: {component.inference_note!r}")
        lines.append("")
        return "\n".join(lines)

    def _build_invariants_yaml(self, invariant_entities: Sequence[Entity]) -> str:
        lines = [
            "# .ai/invariants.yaml — invariant entities",
            "# WARNING: Generated file. Regenerate with: rsm export-ai",
            "# Apache-2.0 — repo-semantic-memory",
            "",
            "invariants:",
        ]
        for entity in sorted(invariant_entities, key=lambda e: e.id.value):
            path = entity.source_range.path
            citation = f"{path}:{entity.source_range.start_line}"
            lines.append(f"  - id: {entity.id.value!r}")
            lines.append(f"    name: {entity.name!r}")
            lines.append(f"    qualified_name: {entity.qualified_name!r}")
            lines.append(f"    source: {citation!r}")
        lines.append("")
        return "\n".join(lines)


def _evidence_citation(evidence_dict: dict[str, Any]) -> str | None:
    """Extract a compact citation string from an evidence dictionary."""
    source = evidence_dict.get("source_range")
    if not source:
        return None
    if isinstance(source, dict):
        path = source.get("path")
        line = source.get("start_line")
        if path:
            return f"{path}:{line}" if line is not None else str(path)
    return None
