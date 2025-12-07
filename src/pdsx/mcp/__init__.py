"""pdsx MCP server for atproto record operations."""

import sys


def main() -> None:
    """entry point for pdsx-mcp command.

    requires the [mcp] extra: pip install pdsx[mcp] or uv add pdsx[mcp]
    """
    try:
        import fastmcp
    except ImportError:
        print(
            "error: pdsx-mcp requires the [mcp] extra.\n\n"
            "install with:\n"
            "  uv add pdsx[mcp]\n"
            "  # or\n"
            "  pip install pdsx[mcp]\n\n"
            "run with uvx:\n"
            "  uvx --from 'pdsx[mcp]' pdsx-mcp"
        )
        sys.exit(1)

    # only import after confirming fastmcp is available
    from pdsx.mcp.server import mcp

    mcp.run()


def _lazy_imports():
    """lazy imports for when the module is imported directly."""
    import warnings

    # suppress pydantic field annotation warning from dependencies
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module="pydantic._internal._generate_schema",
    )

    try:
        from pdsx.mcp.client import (
            AuthenticationRequired,
            get_atproto_client,
        )
        from pdsx.mcp.filterable import filterable
        from pdsx.mcp.middleware import AtprotoAuthMiddleware
        from pdsx.mcp.server import mcp

        return {
            "AtprotoAuthMiddleware": AtprotoAuthMiddleware,
            "AuthenticationRequired": AuthenticationRequired,
            "filterable": filterable,
            "get_atproto_client": get_atproto_client,
            "mcp": mcp,
        }
    except ImportError:
        return {}


def __getattr__(name: str):
    """lazy attribute access - only imports if fastmcp is available."""
    exports = _lazy_imports()
    if name in exports:
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AtprotoAuthMiddleware",
    "AuthenticationRequired",
    "filterable",
    "get_atproto_client",
    "main",
    "mcp",
]
