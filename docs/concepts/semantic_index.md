# Semantic index

The RSM index is a deterministic structural model of a repository. It is built from source code, docs, tests, and optional local Git metadata.

## What is indexed

Current extraction includes:

- repository files and path roles
- Python modules, classes, functions, methods, imports, inheritance, and call-like references from `ast`
- Markdown documents and heading sections
- explicit Python package exports from `__init__.py`
- deterministic inferred test relationships
- optional local Git summary/last-commit metadata

## Core records

- **Entities** represent files, modules, symbols, Markdown sections, and unresolved placeholders.
- **Relations** connect entities with kinds such as `contains`, `imports`, `inherits`, `calls`, `tests`, `documents`, and `exports`.
- **Evidence** points back to repository-relative paths and source ranges where available.
- **Components** are derived semantic labels used by context builders; they can be confirmed or inferred depending on evidence.

Stable IDs and deterministic ordering are part of the contract for reproducible outputs.

## Evidence rules

Semantic claims should cite source evidence or be marked uncertain. Inferred relations/components are useful ranking and navigation hints, not proof. `confirmed PublicAPI` means an entity is explicitly exported in source; it does not imply API stability.
