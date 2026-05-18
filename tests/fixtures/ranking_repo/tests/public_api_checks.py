from lifecore_ros2 import LifecycleComponent


def test_public_export() -> None:
    assert LifecycleComponent is not None
