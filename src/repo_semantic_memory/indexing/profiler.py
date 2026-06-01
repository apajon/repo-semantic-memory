"""Observational indexing phase profiler.

Collects per-phase timing and counters for a full ``rsm index`` run without
changing indexing semantics, ranking, or output.

Usage::

    profiler = IndexProfiler()

    with profiler.phase("python_ast") as ph:
        entities, relations = index_python_path(root)
    ph.files_processed = python_count
    ph.entities_created = len(entities)
    ph.relations_created = len(relations)

    # Print to stderr only when the user passed --profile.
    if profile_flag:
        print(profiler.format_summary(), file=sys.stderr)

Counters can be set inside or after the ``with`` block; the context manager
only records ``elapsed_seconds`` on ``__exit__``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PhaseRecord:
    """Timing and counter record for a single indexing phase.

    Attributes:
        phase_name: Human-readable phase label.
        elapsed_seconds: Wall-clock seconds the phase took.  Set automatically
            by the :class:`_PhaseContext` context manager.
        files_processed: Number of files handled in this phase (0 = N/A).
        entities_created: Entities produced by this phase (0 = N/A).
        relations_created: Relations produced by this phase (0 = N/A).
    """

    phase_name: str
    elapsed_seconds: float = field(default=0.0)
    files_processed: int = field(default=0)
    entities_created: int = field(default=0)
    relations_created: int = field(default=0)


class _PhaseContext:
    """Context manager that records elapsed time for a single phase."""

    def __init__(self, record: PhaseRecord) -> None:
        self._record = record
        self._start: float = 0.0

    def __enter__(self) -> PhaseRecord:
        self._start = time.monotonic()
        return self._record

    def __exit__(self, *_: object) -> None:
        self._record.elapsed_seconds = time.monotonic() - self._start


class IndexProfiler:
    """Collect per-phase timing and counters for a full index run.

    All operations are in-process and have negligible overhead.  No behavior
    changes are made to indexing — the profiler is purely observational.

    Example::

        profiler = IndexProfiler()

        with profiler.phase("file_discovery") as ph:
            entities = extract_filesystem_entities(root)
        ph.files_processed = len(entities)
        ph.entities_created = len(entities)

        print(profiler.format_summary(), file=sys.stderr)
    """

    def __init__(self) -> None:
        self._records: list[PhaseRecord] = []

    def phase(self, name: str) -> _PhaseContext:
        """Start a new timed phase named *name*.

        Returns a :class:`_PhaseContext` context manager whose ``__enter__``
        returns the mutable :class:`PhaseRecord`.  Callers may set counter
        fields (``files_processed``, ``entities_created``, ``relations_created``)
        inside or after the ``with`` block.

        Args:
            name: Phase label used in the summary table.

        Returns:
            A context manager that records ``elapsed_seconds`` on exit.
        """
        record = PhaseRecord(phase_name=name)
        self._records.append(record)
        return _PhaseContext(record)

    @property
    def records(self) -> tuple[PhaseRecord, ...]:
        """Return completed phase records in insertion order."""
        return tuple(self._records)

    def total_elapsed(self) -> float:
        """Return the sum of all phase elapsed times in seconds."""
        return sum(r.elapsed_seconds for r in self._records)

    def format_summary(self) -> str:
        """Return a human-readable profiling summary suitable for stderr.

        Columns: phase name, elapsed, files processed, entities created,
        relations created.  A final ``total`` row shows the cumulative elapsed
        time across all phases.  Counter columns show ``-`` when a phase did
        not populate them (value is 0) to avoid spurious zeros.
        """
        if not self._records:
            return "indexing profile: no phases recorded"

        _NAME_W = 24
        _ELAPSED_W = 9
        _FILES_W = 7
        _ENT_W = 9
        _REL_W = 10

        header = (
            f"  {'phase':<{_NAME_W}}  {'elapsed':>{_ELAPSED_W}}"
            f"  {'files':>{_FILES_W}}  {'entities':>{_ENT_W}}  {'relations':>{_REL_W}}"
        )
        sep = "  " + "─" * (_NAME_W + _ELAPSED_W + _FILES_W + _ENT_W + _REL_W + 10)

        def _fmt_counter(n: int) -> str:
            return str(n) if n else "-"

        lines = ["indexing profile:", header, sep]
        for rec in self._records:
            elapsed_str = f"{rec.elapsed_seconds:.3f}s"
            files_str = _fmt_counter(rec.files_processed)
            ent_str = _fmt_counter(rec.entities_created)
            rel_str = _fmt_counter(rec.relations_created)

            fps_note = ""
            if rec.files_processed > 0 and rec.elapsed_seconds > 0.0:
                fps = rec.files_processed / rec.elapsed_seconds
                fps_note = f"  ({fps:.1f} files/s)"

            lines.append(
                f"  {rec.phase_name:<{_NAME_W}}  {elapsed_str:>{_ELAPSED_W}}"
                f"  {files_str:>{_FILES_W}}  {ent_str:>{_ENT_W}}  {rel_str:>{_REL_W}}"
                f"{fps_note}"
            )

        total_str = f"{self.total_elapsed():.3f}s"
        lines.append(sep)
        lines.append(f"  {'total':<{_NAME_W}}  {total_str:>{_ELAPSED_W}}")

        return "\n".join(lines)


class _NullContext:
    """No-op context manager returned by :class:`_NullProfiler`.

    ``__enter__`` returns a shared :class:`PhaseRecord` whose fields may be
    set by the caller but are simply discarded.
    """

    def __init__(self) -> None:
        self._record = PhaseRecord(phase_name="")

    def __enter__(self) -> PhaseRecord:
        return self._record

    def __exit__(self, *_: object) -> None:
        pass


class _NullProfiler:
    """Drop-in for :class:`IndexProfiler` with zero overhead.

    Use this when ``--profile`` is *not* passed so that phase-wrapping code in
    the CLI is identical whether profiling is enabled or not, without paying
    any timing cost.
    """

    def __init__(self) -> None:
        self._ctx = _NullContext()

    def phase(
        self, name: str
    ) -> (
        _NullContext
    ):  # name unused: maintains API compatibility with IndexProfiler  # noqa: ARG002
        """Return a no-op context manager that discards all timing/counters."""
        return self._ctx

    @property
    def records(self) -> tuple[PhaseRecord, ...]:
        """Always empty — null profiler records nothing."""
        return ()

    def total_elapsed(self) -> float:
        """Always 0.0."""
        return 0.0

    def format_summary(self) -> str:
        """Always the no-phases message."""
        return "indexing profile: no phases recorded"


#: Union of the real and no-op profiler — used as the type for ``profiler``
#: locals in the CLI so the variable can be reassigned from either variant.
_AnyProfiler = IndexProfiler | _NullProfiler
