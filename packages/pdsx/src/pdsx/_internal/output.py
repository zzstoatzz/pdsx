"""output formatting utilities."""

from __future__ import annotations

import sys
from enum import Enum


class OutputFormat(str, Enum):
    """output format options following kubectl/gh conventions."""

    JSON = "json"
    YAML = "yaml"
    TABLE = "table"  # rich table (default for TTY)
    COMPACT = "compact"  # one-line per record


def is_tty() -> bool:
    """check if stdout is a terminal."""
    return sys.stdout.isatty()
