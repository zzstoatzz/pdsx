"""filterable decorator for MCP tools.

Adds a `_filter` parameter that accepts jmespath expressions to
filter/project tool results. Reduces response size and lets
LLM clients request only the fields they need.

See https://jmespath.org for filter syntax.
"""

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Annotated, Any, ParamSpec, TypeVar, overload

import jmespath
import jmespath.exceptions
from pydantic import Field, TypeAdapter

P = ParamSpec("P")
R = TypeVar("R")

FilterParam = Annotated[
    str | None,
    Field(
        description=(
            "jmespath expression to filter/project the result. "
            "examples: '[*].{uri: uri, text: value.text}' (select fields), "
            "'[?value.text != null]' (filter items), "
            "'[*].uri' (extract values)"
        ),
    ),
]


def apply_filter(data: Any, filter_expr: str | None) -> Any:
    """apply jmespath filter to data."""
    if not filter_expr:
        return data
    try:
        jsonable = TypeAdapter(type(data)).dump_python(data, mode="json")
        return jmespath.search(filter_expr, jsonable)
    except jmespath.exceptions.JMESPathError:
        return data


@overload
def filterable(
    fn: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]: ...


@overload
def filterable(
    fn: Callable[P, R],
) -> Callable[P, Any]: ...


def filterable(
    fn: Callable[P, R] | Callable[P, Awaitable[R]],
) -> Callable[P, Any] | Callable[P, Awaitable[Any]]:
    """decorator that adds `_filter` parameter to a tool.

    the filter is a jmespath expression applied to the result.
    see https://jmespath.org/ for syntax.

    usage:
        @mcp.tool
        @filterable
        async def list_records(collection: str) -> list[dict]:
            return [{"uri": "...", "value": {...}}, ...]

        # call without filter - get everything
        list_records(collection="app.bsky.feed.post")

        # call with filter - get filtered result
        list_records(collection="app.bsky.feed.post", _filter="[*].uri")
    """

    @wraps(fn)
    async def async_wrapper(
        *args: P.args, _filter: str | None = None, **kwargs: P.kwargs
    ) -> Any:
        result = await fn(*args, **kwargs)  # type: ignore[misc]
        return apply_filter(result, _filter)

    @wraps(fn)
    def sync_wrapper(
        *args: P.args, _filter: str | None = None, **kwargs: P.kwargs
    ) -> Any:
        result = fn(*args, **kwargs)  # type: ignore[misc]
        return apply_filter(result, _filter)

    wrapper = async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    params.append(
        inspect.Parameter(
            "_filter",
            inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=FilterParam,
        )
    )
    wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]

    wrapper.__annotations__ = {
        **fn.__annotations__,
        "_filter": FilterParam,
        "return": Any,
    }

    return wrapper
