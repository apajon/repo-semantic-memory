"""Lifecycle component tests — used as a ranking fixture.

This file is intentionally minimal: it exercises the LifecycleComponent
through its public interface so that test-relationship extraction can
infer a ``tests`` relation from this file to
``lifecycle_component.LifecycleComponent``.
"""

from lifecore_ros2.components.lifecycle_component import build_component


class TestLifecycleComponent:
    def test_cleanup_releases_publisher(self) -> None:
        pass

    def test_start_stop(self) -> None:
        pass


def test_build_component_returns_lifecycle() -> None:
    _ = build_component
