"""Tests for the session-local in-memory MCP result store."""

from __future__ import annotations

import pytest

from repo_semantic_memory.mcp.session import (
    DEFAULT_MAX_BYTES_PER_SET,
    DEFAULT_MAX_RESULT_SETS,
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    STREAM_NAMES,
    ResultSet,
    ResultStore,
    slice_page,
)


def _sample_streams() -> dict[str, list[dict[str, object]]]:
    return {
        "files": [{"id": "f1", "path": "a.py"}, {"id": "f2", "path": "b.py"}],
        "entities": [{"id": "e1", "entity_id": "python:function:a"}],
        "relations": [{"id": "r1", "kind": "contains"}],
        "citations": [{"id": "c1", "path": "a.py", "start_line": 1, "end_line": 2}],
        "ranking_breakdowns": [],
    }


# ---------------------------------------------------------------------------
# Configuration & ID minting
# ---------------------------------------------------------------------------


def test_default_bounds_match_prompt_spec() -> None:
    assert DEFAULT_MAX_RESULT_SETS == 8
    assert DEFAULT_MAX_BYTES_PER_SET == 256 * 1024
    assert DEFAULT_PAGE_LIMIT == 5
    assert MAX_PAGE_LIMIT == 20
    assert STREAM_NAMES == (
        "files",
        "entities",
        "relations",
        "citations",
        "ranking_breakdowns",
    )


def test_store_rejects_zero_bounds() -> None:
    with pytest.raises(ValueError):
        ResultStore(max_sets=0)
    with pytest.raises(ValueError):
        ResultStore(max_bytes_per_set=0)


def test_put_mints_opaque_pack_prefixed_id() -> None:
    store = ResultStore()
    entry = store.put(_sample_streams())
    assert isinstance(entry, ResultSet)
    assert entry.result_set_id.startswith("pack_")
    # 10 hex chars after the prefix matches secrets.token_hex(5).
    assert len(entry.result_set_id) == len("pack_") + 10
    # IDs are unique across calls in the same store.
    other = store.put(_sample_streams())
    assert other.result_set_id != entry.result_set_id


def test_put_records_counts_per_stream() -> None:
    store = ResultStore()
    entry = store.put(_sample_streams())
    assert entry.counts == {
        "files": 2,
        "entities": 1,
        "relations": 1,
        "citations": 1,
        "ranking_breakdowns": 0,
    }


# ---------------------------------------------------------------------------
# Retrieval / LRU eviction
# ---------------------------------------------------------------------------


def test_get_unknown_id_returns_none() -> None:
    store = ResultStore()
    assert store.get("pack_unknown") is None
    assert store.get("") is None


def test_lru_eviction_drops_oldest_on_overflow() -> None:
    store = ResultStore(max_sets=2)
    a = store.put(_sample_streams())
    b = store.put(_sample_streams())
    # Touching ``a`` should mark it as most-recently used.
    assert store.get(a.result_set_id) is not None
    c = store.put(_sample_streams())
    # ``b`` was the oldest after the get-touch on ``a``; it should be evicted.
    assert store.get(b.result_set_id) is None
    assert store.get(a.result_set_id) is not None
    assert store.get(c.result_set_id) is not None
    assert len(store) == 2


def test_eviction_is_lazy_on_put_only() -> None:
    store = ResultStore(max_sets=1)
    first = store.put(_sample_streams())
    assert len(store) == 1
    # Repeated gets do not evict.
    for _ in range(5):
        assert store.get(first.result_set_id) is not None
    assert len(store) == 1


# ---------------------------------------------------------------------------
# Byte-size cap
# ---------------------------------------------------------------------------


def test_put_truncates_streams_to_byte_cap() -> None:
    # Each entity is ~200+ bytes serialized; cap should drop later items.
    streams = {"entities": [{"id": f"e{i}", "name": "x" * 200, "path": "a.py"} for i in range(20)]}
    store = ResultStore(max_bytes_per_set=400)
    entry = store.put(streams)
    assert entry.counts["entities"] < 20
    assert entry.approx_bytes <= 400


# ---------------------------------------------------------------------------
# slice_page semantics
# ---------------------------------------------------------------------------


def _store_with_entities(n: int) -> tuple[ResultStore, ResultSet]:
    store = ResultStore()
    entries = [{"id": f"e{i}", "entity_id": f"python:function:f{i}"} for i in range(1, n + 1)]
    entry = store.put({"entities": entries})
    return store, entry


def test_slice_page_returns_slice_and_next_offset() -> None:
    _, entry = _store_with_entities(7)
    items, total, next_offset = slice_page(entry, stream="entities", offset=0, limit=3)
    assert total == 7
    assert next_offset == 3
    assert [item["id"] for item in items] == ["e1", "e2", "e3"]

    items, total, next_offset = slice_page(entry, stream="entities", offset=3, limit=3)
    assert next_offset == 6
    assert [item["id"] for item in items] == ["e4", "e5", "e6"]

    items, total, next_offset = slice_page(entry, stream="entities", offset=6, limit=3)
    assert next_offset is None
    assert [item["id"] for item in items] == ["e7"]


def test_slice_page_past_end_returns_empty_slice() -> None:
    _, entry = _store_with_entities(2)
    items, total, next_offset = slice_page(entry, stream="entities", offset=10, limit=5)
    assert items == ()
    assert total == 2
    assert next_offset is None


def test_slice_page_validates_arguments() -> None:
    _, entry = _store_with_entities(1)
    with pytest.raises(ValueError, match="unknown stream"):
        slice_page(entry, stream="nope", offset=0, limit=1)
    with pytest.raises(ValueError, match="offset"):
        slice_page(entry, stream="entities", offset=-1, limit=1)
    with pytest.raises(ValueError, match="limit"):
        slice_page(entry, stream="entities", offset=0, limit=0)
    with pytest.raises(ValueError, match="limit"):
        slice_page(entry, stream="entities", offset=0, limit=MAX_PAGE_LIMIT + 1)
