import os

from pkg.base import BaseThing


def decorated(func):
    return func


def current_os_name() -> str:
    return os.name


class NoDocClass:
    pass


class DerivedThing(BaseThing):
    """A class with a docstring."""

    @staticmethod
    @decorated
    def decorated_method(value: int) -> str:
        return str(value)

    async def async_method(self, flag: bool) -> bool:
        return flag


@decorated
def top_level_function(value: int) -> str:
    return str(value)


async def top_level_async(value: int) -> int:
    return value
