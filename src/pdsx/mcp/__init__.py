"""pdsx MCP server for atproto record operations."""

import warnings

# suppress pydantic field annotation warning from dependencies
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="pydantic._internal._generate_schema",
)

from pdsx.mcp.client import AuthenticationRequired, get_atproto_client  # noqa: E402
from pdsx.mcp.filterable import filterable  # noqa: E402
from pdsx.mcp.middleware import AtprotoAuthMiddleware  # noqa: E402
from pdsx.mcp.server import mcp  # noqa: E402

__all__ = [
    "AtprotoAuthMiddleware",
    "AuthenticationRequired",
    "filterable",
    "get_atproto_client",
    "mcp",
]
