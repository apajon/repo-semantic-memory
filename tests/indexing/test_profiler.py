"""Unit tests for the indexing phase profiler (Prompt 57.1)."""

from __future__ import annotations

import time

import pytest

from repo_semantic_memory.indexing.profiler import IndexProfiler, PhaseRecord

# ---------------------------------------------------------------------------
# PhaseRecord defaults
# ---------------------------------------------------------------------------


class TestPhaseRecordDefaults:
    def test_default_counters_are_zero(self) -> None:
        rec = PhaseRecord(phase_name="test_phase")
        assert rec.elapsed_seconds == 0.0
        assert rec.files_processed == 0
        assert rec.entities_created == 0
        assert rec.relations_created == 0

    def test_phase_name_preserved(self) -> None:
        rec = PhaseRecord(phase_name="python_ast")
        assert rec.phase_name == "python_ast"

    def test_counters_are_mutable(self) -> None:
        rec = PhaseRecord(phase_name="p")
        rec.files_processed = 42
        rec.entities_created = 10
        rec.relations_created = 5
        assert rec.files_processed == 42
        assert rec.entities_created == 10
        assert rec.relations_created == 5


# ---------------------------------------------------------------------------
# IndexProfiler phase ordering and elapsed time
# ---------------------------------------------------------------------------


class TestIndexProfiler:
    def test_records_empty_initially(self) -> None:
        profiler = IndexProfiler()
        assert profiler.records == ()

    def test_phase_returns_record_with_correct_name(self) -> None:
        profiler = IndexProfiler()
        ctx = profiler.phase("file_discovery")
        with ctx as ph:
            pass
        assert ph.phase_name == "file_discovery"

    def test_phases_recorded_in_order(self) -> None:
        profiler = IndexProfiler()
        for name in ("file_discovery", "python_ast", "sqlite_persist"):
            with profiler.phase(name):
                pass
        assert tuple(r.phase_name for r in profiler.records) == (
            "file_discovery",
            "python_ast",
            "sqlite_persist",
        )

    def test_elapsed_seconds_is_non_negative(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("fast_phase") as ph:
            pass
        assert ph.elapsed_seconds >= 0.0

    def test_elapsed_seconds_is_set_on_exit(self) -> None:
        profiler = IndexProfiler()
        ctx = profiler.phase("timed")
        with ctx as ph:
            assert ph.elapsed_seconds == 0.0  # not yet set inside the block
        assert ph.elapsed_seconds >= 0.0

    def test_elapsed_captures_real_time(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("slow") as ph:
            time.sleep(0.01)
        assert ph.elapsed_seconds >= 0.005  # generous lower bound

    def test_counters_set_inside_block(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("phase") as ph:
            ph.files_processed = 7
            ph.entities_created = 3
        assert ph.files_processed == 7
        assert ph.entities_created == 3

    def test_counters_set_after_block(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("phase") as ph:
            pass
        ph.relations_created = 99
        assert profiler.records[0].relations_created == 99

    def test_records_returns_tuple_snapshot(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("a"):
            pass
        snapshot = profiler.records
        with profiler.phase("b"):
            pass
        # snapshot should not include the new phase
        assert len(snapshot) == 1
        assert len(profiler.records) == 2

    def test_total_elapsed_sums_phases(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("a") as ph_a:
            pass
        with profiler.phase("b") as ph_b:
            pass
        ph_a.elapsed_seconds = 1.0
        ph_b.elapsed_seconds = 2.5
        assert profiler.total_elapsed() == pytest.approx(3.5)

    def test_total_elapsed_zero_when_empty(self) -> None:
        profiler = IndexProfiler()
        assert profiler.total_elapsed() == 0.0


# ---------------------------------------------------------------------------
# format_summary output
# ---------------------------------------------------------------------------


class TestFormatSummary:
    def test_empty_profiler_returns_no_phases_message(self) -> None:
        profiler = IndexProfiler()
        summary = profiler.format_summary()
        assert "no phases recorded" in summary

    def test_summary_starts_with_indexing_profile(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("file_discovery"):
            pass
        summary = profiler.format_summary()
        assert summary.startswith("indexing profile:")

    def test_summary_contains_all_phase_names(self) -> None:
        profiler = IndexProfiler()
        phases = ["file_discovery", "python_ast", "sqlite_persist"]
        for name in phases:
            with profiler.phase(name):
                pass
        summary = profiler.format_summary()
        for name in phases:
            assert name in summary

    def test_summary_contains_total_row(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("phase"):
            pass
        assert "total" in profiler.format_summary()

    def test_zero_counters_shown_as_dash(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("empty_phase"):
            pass
        summary = profiler.format_summary()
        # files/entities/relations all 0 → should show dashes not "0"
        assert " - " in summary or summary.count("-") >= 1

    def test_nonzero_counters_shown_as_numbers(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("loaded_phase") as ph:
            pass
        ph.files_processed = 50
        ph.entities_created = 120
        ph.relations_created = 75
        summary = profiler.format_summary()
        assert "50" in summary
        assert "120" in summary
        assert "75" in summary

    def test_files_per_second_shown_when_files_and_elapsed_nonzero(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("perf_phase") as ph:
            pass
        ph.files_processed = 100
        ph.elapsed_seconds = 1.0
        summary = profiler.format_summary()
        assert "files/s" in summary

    def test_files_per_second_absent_when_no_files(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("no_files") as ph:
            pass
        ph.elapsed_seconds = 1.0  # files_processed stays 0
        summary = profiler.format_summary()
        assert "files/s" not in summary

    def test_files_per_second_absent_when_elapsed_zero(self) -> None:
        """No files/s annotation when elapsed is 0 — avoids divide-by-zero."""
        profiler = IndexProfiler()
        with profiler.phase("instant") as ph:
            pass
        ph.files_processed = 100
        ph.elapsed_seconds = 0.0  # guard: must not compute 100 / 0
        summary = profiler.format_summary()
        assert "files/s" not in summary

    def test_zero_elapsed_shown_as_zero_string(self) -> None:
        """A phase that completed in zero measured time still renders a valid elapsed cell."""
        profiler = IndexProfiler()
        with profiler.phase("instant") as ph:
            pass
        ph.elapsed_seconds = 0.0
        summary = profiler.format_summary()
        assert "0.000s" in summary

    def test_summary_is_multiline(self) -> None:
        profiler = IndexProfiler()
        with profiler.phase("phase1"):
            pass
        with profiler.phase("phase2"):
            pass
        assert "\n" in profiler.format_summary()
