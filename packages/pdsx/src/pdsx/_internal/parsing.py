"""argument parsing utilities."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console

console = Console()


def parse_key_value_args(args: list[str]) -> dict[str, Any]:
    """parse key=value arguments into a dict.

    supports JSON for complex values (objects/arrays).

    Args:
        args: list of key=value strings

    Returns:
        parsed dictionary

    Examples:
        ```python
        >>> parse_key_value_args(["name=test", "count=5", "active=true"])
        {'name': 'test', 'count': 5, 'active': True}
        >>> parse_key_value_args(['embed={"$type":"blob"}'])
        {'embed': {'$type': 'blob'}}
        ```
    """
    result: dict[str, Any] = {}
    for arg in args:
        if "=" not in arg:
            console.print(f"[red]error:[/red] invalid argument format: {arg}")
            console.print("[dim]use key=value format[/dim]")
            sys.exit(1)
        key, value = arg.split("=", 1)

        # try JSON first for objects/arrays
        if value.startswith(("{", "[")):
            try:
                result[key] = json.loads(value)
                continue
            except json.JSONDecodeError as e:
                console.print(f"[red]error:[/red] invalid JSON for {key}: {e}")
                sys.exit(1)

        # parse primitives
        if value.lower() == "true":
            result[key] = True
        elif value.lower() == "false":
            result[key] = False
        elif value.lower() == "null":
            result[key] = None
        elif value.isdigit():
            result[key] = int(value)
        else:
            try:
                result[key] = float(value)
            except ValueError:
                result[key] = value
    return result
