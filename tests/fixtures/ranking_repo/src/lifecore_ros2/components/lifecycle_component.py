class LifecycleComponent:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def helper(self) -> None:
        pass


def build_component() -> LifecycleComponent:
    return LifecycleComponent()
