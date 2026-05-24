"""Session-local in-memory result store for the MCP runtime.

This module is intentionally small and only used by the MCP runtime/server.
It implements the bounded result-set cache designed in
:doc:`docs/design/mcp_progressive_context` so that
:func:`rsm_build_context_pack <repo_semantic_memory.mcp.runtime._tool_build_context_pack>`
can return a small first-page response and a follow-up
:func:`rsm_get_context_page <repo_semantic_memory.mcp.runtime._tool_get_context_page>`
call can return additional already-computed entries from the same result set
without ever recomputing the pack.

Design contracts:

- Process-local memory only. No disk writes, no background timers.
- Bounded: at most ``max_sets`` entries; each entry is capped at
  ``max_bytes_per_set`` approximate JSON bytes.
- Oldest result sets are evicted on insertion when the cap is exceeded.
- Opaque ``pack_<short-hex>`` IDs that are stable only within the current
  MCP process. They are not reproducible across sessions.
- The store is internal to the MCP runtime; it is not exported as a stable
  public API.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Default bounds (Prompt 46.3 spec).
DEFAULT_MAX_RESULT_SETS: int = 8
DEFAULT_MAX_BYTES_PER_SET: int = 256 * 1024
DEFAULT_PAGE_LIMIT: int = 5
MAX_PAGE_LIMIT: int = 20

# Stream names exposed by the progressive retrieval model. ``ranking_breakdowns``
# is optional and only present when the underlying pack was built with ranking
# explanations enabled.
STREAM_NAMES: tuple[str, ...] = (
    "files",
    "entities",
    "relations",
    "citations",
    "ranking_breakdowns",
)


@dataclass(frozen=True)
class ResultSet:
    """An immutable, in-memory view of one already-computed context pack.

    A result set never recomputes the pack. It is a thin paged view over the
    deterministic streams already produced by the handler.
    """

    result_set_id: str
    streams: dict[str, tuple[dict[str, Any], ...]]
    counts: dict[str, int]
    approx_bytes: int


class ResultStore:
    """Bounded LRU store of :class:`ResultSet` entries for one MCP session.

    The store is intentionally small (a guarded :class:`OrderedDict`) and has
    no background tasks. Eviction happens lazily on :meth:`put`.
    """

    def __init__(
        self,
        *,
        max_sets: int = DEFAULT_MAX_RESULT_SETS,
        max_bytes_per_set: int = DEFAULT_MAX_BYTES_PER_SET,
    ) -> None:
        if max_sets < 1:
            raise ValueError("max_sets must be >= 1")
        if max_bytes_per_set < 1:
            raise ValueError("max_bytes_per_set must be >= 1")
        self._max_sets = max_sets
        self._max_bytes_per_set = max_bytes_per_set
        self._lock = threading.Lock()
        self._sets: OrderedDict[str, ResultSet] = OrderedDict()

    # -- Configuration introspection ------------------------------------------------

    @property
    def max_sets(self) -> int:
        return self._max_sets

    @property
    def max_bytes_per_set(self) -> int:
        return self._max_bytes_per_set

    def __len__(self) -> int:
        with self._lock:
            return len(self._sets)

    # -- Mutation -------------------------------------------------------------------

    def put(
        self,
        streams: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> ResultSet:
        """Store ``streams`` under a freshly minted opaque ``result_set_id``.

        Entries are trimmed deterministically (in :data:`STREAM_NAMES` order)
        until the approximate serialized size fits in ``max_bytes_per_set``.
        ``counts`` reflect the number of *stored* items per stream, since
        :func:`rsm_get_context_page` only ever pages stored content.
        """

        bounded, counts, approx_bytes = self._bound_streams(streams)
        with self._lock:
            self._evict_for_one_more()
            result_set_id = self._mint_id_locked()
            entry = ResultSet(
                result_set_id=result_set_id,
                streams=bounded,
                counts=counts,
                approx_bytes=approx_bytes,
            )
            self._sets[result_set_id] = entry
            return entry

    def get(self, result_set_id: str) -> ResultSet | None:
        """Return the stored result set, marking it as most-recently used."""

        if not isinstance(result_set_id, str) or not result_set_id:
            return None
        with self._lock:
            entry = self._sets.get(result_set_id)
            if entry is None:
                return None
            self._sets.move_to_end(result_set_id)
            return entry

    # -- Internal helpers -----------------------------------------------------------

    def _bound_streams(
        self,
        streams: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> tuple[dict[str, tuple[dict[str, Any], ...]], dict[str, int], int]:
        bounded: dict[str, tuple[dict[str, Any], ...]] = {}
        counts: dict[str, int] = {}
        running_bytes = 0
        for name in STREAM_NAMES:
            raw_items = streams.get(name, ())
            kept: list[dict[str, Any]] = []
            for item in raw_items:
                if not isinstance(item, Mapping):
                    continue
                snapshot = dict(item)
                try:
                    size = len(json.dumps(snapshot, separators=(",", ":"), default=str))
                except (TypeError, ValueError):
                    # Non-serializable entries are dropped rather than failing
                    # the entire put(); paging stays best-effort over already
                    # computed JSON-safe payloads.
                    continue
                if running_bytes + size > self._max_bytes_per_set:
                    break
                kept.append(snapshot)
                running_bytes += size
            bounded[name] = tuple(kept)
            counts[name] = len(kept)
        return bounded, counts, running_bytes

    def _evict_for_one_more(self) -> None:
        while len(self._sets) >= self._max_sets:
            self._sets.popitem(last=False)

    def _mint_id_locked(self) -> str:
        # Loop is defensive against the (extremely unlikely) collision case;
        # token_hex(5) has 40 bits of entropy, far above ``max_sets``.
        for _ in range(8):
            candidate = f"pack_{secrets.token_hex(5)}"
            if candidate not in self._sets:
                return candidate
        raise RuntimeError("failed to mint a unique result_set_id")


def slice_page(
    result_set: ResultSet,
    *,
    stream: str,
    offset: int,
    limit: int,
) -> tuple[tuple[dict[str, Any], ...], int, int | None]:
    """Return a deterministic slice of ``stream`` and pagination metadata.

    Raises :class:`ValueError` on unknown stream names or out-of-range
    ``offset``/``limit`` values. Callers translate those into normal MCP
    tool-call errors; unknown/expired result-set IDs are handled separately
    by the runtime as a recoverable tool-level uncertainty.
    """

    if stream not in STREAM_NAMES:
        raise ValueError(f"unknown stream: {stream!r}")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")
    items = result_set.streams.get(stream, ())
    total = len(items)
    if offset >= total:
        return ((), total, None)
    end = min(offset + limit, total)
    next_offset: int | None = end if end < total else None
    return (items[offset:end], total, next_offset)


__all__ = [
    "DEFAULT_MAX_BYTES_PER_SET",
    "DEFAULT_MAX_RESULT_SETS",
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "STREAM_NAMES",
    "ResultSet",
    "ResultStore",
    "slice_page",
]
