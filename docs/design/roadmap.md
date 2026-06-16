# Roadmap

This roadmap is directional. It shows what RSM is focused on now and what is planned next, but tracks are not committed release promises.

Priorities are driven by benchmarks, dogfooding on real repositories, real agent workflow failures, implementation cost, and avoiding scope creep.

## Current Focus

**69.x — Public readiness** (active)

Making RSM understandable and usable for first-time users:

- 69.0: Public-facing README
- 69.1: Quickstart and first-use validation
- 69.2: CLI examples and output examples
- 69.3: Known limitations and roadmap cleanup
- 69.4: Release-readiness validation
- 69.5: Public announcement

## Public Readiness

The 69.x track prepares RSM for its first public announcement. It does not add new features — it makes the current state honest, documented, and safe to share.

By the end of 69.x:

- The README is clear about what RSM does and does not do.
- The quickstart works from `uv sync` to first context pack.
- Realistic CLI examples with representative output exist.
- Known limitations are documented honestly.
- The roadmap is public-readable.

## Near-Term Backlog

These tracks are planned for after public readiness. They are not promised and may be reordered based on user feedback.

### 68.x — Non-Python / interface-file indexing

Extend indexing beyond Python and Markdown to cover interface definition files common in ROS 2 and similar ecosystems.

- 68.0: Design interface-file indexing approach (`.msg`, `.srv`, `.action`, `.proto`, etc.)
- 68.1: Add benchmark cases for ROS interface files
- 68.2: Implement minimal `.msg` / `.srv` / `.action` indexing
- 68.3: Validate on lifecore_ros2
- 68.4: Add relations between interface files and build/config files

### 63.x — Search refinement

Improve search precision and recall based on benchmark results and dogfooding findings.

### 64.x — find_related refinement

Improve anchor-based expansion to return more relevant related entities and fewer false positives.

### 65.x — ContextPack refinement

Improve symbol selection, file ordering, and budget allocation in context packs.

## Deferred Technical Work

These items are explicitly deferred. They may be revisited but are not actively planned.

### 66.x — Snippets/chunks feasibility

Evaluate whether extracting code snippets or semantic chunks alongside entity metadata improves agent usefulness. This is a feasibility study, not a commitment to implement.

## Not Currently Planned

These items are out of scope for the foreseeable future:

- Embeddings or vector search (architectural decision — RSM is lexical and structural)
- GUI or web dashboard
- Remote or multi-user MCP server
- Full semantic graph export (RDF, GraphML)
- Automatic background indexing or watch mode
- LLM-generated summaries or claims
- Neo4j or graph database backend

## How Priorities Are Chosen

RSM priorities are driven by:

- **Benchmarks**: Internal task-based benchmarks that measure retrieval quality.
- **Dogfooding**: Using RSM on real repositories (lifecore_ros2, repo-semantic-memory itself) and recording what works and what fails.
- **Real agent workflow failures**: When an agent cannot complete a task because RSM missed relevant context, that drives prioritization.
- **Implementation cost**: Prefer small, incremental changes over large rewrites.
- **Avoiding scope creep**: RSM is a context compiler, not a general-purpose code intelligence platform. Features that expand scope are deferred unless they have strong evidence of agent workflow impact.
