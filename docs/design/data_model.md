# Data Model (Initial)

Current deterministic versions:

- Package version: tracks Python package releases.
- Schema version: tracks semantic artifact schema evolution.
- Context pack version: tracks serialized context pack contract evolution.

Version identifiers are explicit constants and must not be inferred from each other.

## MVP file/module representation

For the MVP, source files discovered by the filesystem extractor are represented directly as entities.

- `.py` files use `kind: module`
- documentation/config-like text files use `kind: doc`
- stable IDs are based on repository-relative POSIX paths

This intentionally conflates physical Python files and logical Python modules for the initial implementation.

A later schema may split these into:
- `file` entities for physical files
- `module` entities for logical importable modules
- `contains` or `defines` relations between them

For persisted index output (`rsm index`), Python module/class/function/method entities are owned by the Python AST extractor.
Filesystem-discovered `.py` module entities are not persisted to avoid duplicate Python module representations.

## Relation identity (SQLite MVP)

SQLite currently models relations as logical edges keyed by:

- `(source_id, target_id, kind)`

This means repeated occurrences of the same logical relation are intentionally collapsed in the MVP.
If occurrence-level tracking is required later, a future schema can introduce explicit relation occurrence IDs.
