"""Static project configuration defaults for the CLI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Immutable application-level configuration values."""

    cli_name: str = "rsm"
    project_name: str = "repo-semantic-memory"


DEFAULT_CONFIG = AppConfig()
