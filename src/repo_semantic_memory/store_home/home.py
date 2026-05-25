"""RSM Index Store home directory resolution.

The RSM Index Store is a central local directory that maps repository roots to
their SQLite index files. This module resolves the store home path without
requiring any external dependencies.

Resolution order:

1. ``RSM_HOME`` environment variable, if set and non-empty.
2. OS-specific default:

   - Linux / Ubuntu: ``$XDG_DATA_HOME/repo-semantic-memory``
     (fallback: ``~/.local/share/repo-semantic-memory``)
   - macOS: ``~/Library/Application Support/repo-semantic-memory``
   - Windows: ``%LOCALAPPDATA%\\repo-semantic-memory``
     (fallback: ``~\\AppData\\Local\\repo-semantic-memory``)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_STORE_DIR_NAME = "repo-semantic-memory"


def resolve_store_home() -> Path:
    """Resolve the RSM Index Store home directory.

    Creates the directory and its ``indexes/`` subdirectory on first call if
    they do not already exist. Safe to call multiple times.
    """
    home = _locate_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "indexes").mkdir(exist_ok=True)
    return home


def _locate_home() -> Path:
    """Return the store home Path without creating any directories."""
    rsm_home = os.environ.get("RSM_HOME")
    if rsm_home:
        return Path(os.path.expandvars(os.path.expanduser(rsm_home)))

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / _STORE_DIR_NAME
        return Path.home() / "AppData" / "Local" / _STORE_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _STORE_DIR_NAME

    # Linux / other POSIX: XDG Base Directory Specification
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / _STORE_DIR_NAME
    return Path.home() / ".local" / "share" / _STORE_DIR_NAME


__all__ = ["resolve_store_home"]
