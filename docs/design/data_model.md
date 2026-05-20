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

## Supported relation kinds

| Kind       | Description                                                                 |
|------------|-----------------------------------------------------------------------------|
| `contains` | Structural containment (e.g. module contains class/function)                |
| `imports`  | Python import reference (may be unresolved)                                 |
| `inherits` | Class inheritance (may be unresolved)                                       |
| `calls`    | Function/method call reference                                               |
| `uses`     | Generic usage reference                                                      |
| `tests`    | Test entity covers/validates a production entity                            |
| `documents`| Documentation entity describes a production entity                         |
| `owns`     | Ownership/membership relation                                               |
| `requires` | Dependency requirement                                                       |
| `violates` | Invariant violation reference                                               |
| `exports`  | Explicit re-export from a `__init__.py` module (static AST only; target may be unresolved) |

### `exports` relation semantics

The `exports` relation is produced by the `python_exports` extractor from `__init__.py` files.

- **Source**: the `__init__.py` module entity.
- **Target**: an unresolved symbol placeholder (`unresolved:export:<module>:<name>`).
- **Evidence**: anchored to the source range of the export statement in the `__init__.py`.
- **Metadata fields**:
  - `exported_name` (string): the public name as it appears in the package namespace.
  - `source_module` (string): the module path the name is imported from.
  - `original_name` (string, optional): the name before aliasing (omitted when no alias).
  - `resolved` (bool): always `False` in the MVP; targets are never resolved to entity IDs.
  - `via_all` (bool): `True` when the name also appears in `__all__`.

No SQLite schema change was required; `kind` is stored as `TEXT` and already accepts any string.
