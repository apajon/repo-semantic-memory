class LifecycleComponent:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def helper(self) -> None:
        return None


def build_component() -> LifecycleComponent:
    return LifecycleComponent()
