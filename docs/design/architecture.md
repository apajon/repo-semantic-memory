# Architecture

`repo-semantic-memory` is structured as a layered semantic compiler.

1. Raw repository inputs
2. Symbol index
3. Structural graph
4. ECS-style semantic components
5. Claims/contracts/invariants
6. Evidence and temporal validity
7. Context pack builder
8. Benchmark harness
9. MCP server integration (later)

This repository currently implements only the project foundation and CLI surface.
