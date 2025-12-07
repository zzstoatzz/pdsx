"""display utilities for rich output."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import yaml
from atproto_client.models.dot_dict import DotDict
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pdsx._internal.output import OutputFormat

if TYPE_CHECKING:
    from atproto import models

console = Console()


def _value_to_dict(value: object) -> dict[str, object]:
    """convert a record value to a dict, handling pydantic models and DotDict."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, DotDict):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    # fallback for unknown types
    return {k: v for k, v in value.__dict__.items() if not k.startswith("_")}


def display_records(
    collection: str,
    records: list[models.ComAtprotoRepoListRecords.Record],
    *,
    output_format: OutputFormat,
) -> None:
    """display a list of records.

    Args:
        collection: collection name
        records: list of record objects
        output_format: output format enum
    """
    if not records:
        if output_format != OutputFormat.JSON:
            print(f"no records in {collection}")
        return

    # json output
    if output_format == OutputFormat.JSON:
        output = []
        for record in records:
            rkey = record.uri.split("/")[-1]
            value_dict = _value_to_dict(record.value)
            output.append(
                {
                    "rkey": rkey,
                    "uri": record.uri,
                    "cid": record.cid,
                    **value_dict,
                }
            )
        print(json.dumps(output, indent=2))
        return

    # yaml output
    if output_format == OutputFormat.YAML:
        output = []
        for record in records:
            rkey = record.uri.split("/")[-1]
            value_dict = _value_to_dict(record.value)
            output.append(
                {
                    "rkey": rkey,
                    "uri": record.uri,
                    "cid": record.cid,
                    **value_dict,
                }
            )
        print(yaml.dump(output, default_flow_style=False, sort_keys=False))
        return

    # compact output (one line per record)
    if output_format == OutputFormat.COMPACT:
        count = len(records)
        plural = "record" if count == 1 else "records"
        print(f"{collection} ({count} {plural})")
        for record in records:
            rkey = record.uri.split("/")[-1]
            value_dict = _value_to_dict(record.value)
            print(f"{rkey}: {json.dumps(value_dict, separators=(',', ':'))}")
        return

    # rich table output (default) - show only simple fields, truncate long text
    count = len(records)
    plural = "record" if count == 1 else "records"
    table = Table(
        title=f"{collection} ({count} {plural})",
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("rkey", style="dim", width=13, no_wrap=True)

    # only show simple (non-dict, non-list) fields in table view
    if records:
        first_value = records[0].value
        value_dict = _value_to_dict(first_value)

        for key, val in value_dict.items():
            if key not in ("$type", "py_type") and not isinstance(val, dict | list):
                # special handling for text fields - give them more width
                width = 50 if key == "text" else 20
                table.add_column(
                    key,
                    style="white",
                    no_wrap=True,
                    overflow="ellipsis",
                    max_width=width,
                )

    for record in records:
        rkey = record.uri.split("/")[-1]
        value_dict = _value_to_dict(record.value)

        row = [rkey]
        for key, val in value_dict.items():
            if key not in ("$type", "py_type") and not isinstance(val, dict | list):
                cell_val = str(val) if val is not None else ""
                row.append(cell_val)

        table.add_row(*row)

    console.print(table)


def display_record(
    response: models.ComAtprotoRepoGetRecord.Response,
    *,
    output_format: OutputFormat = OutputFormat.TABLE,
) -> None:
    """display a single record.

    Args:
        response: atproto record response
        output_format: output format enum (default: table with panel)
    """
    rkey = response.uri.split("/")[-1]
    value_dict = _value_to_dict(response.value)

    # json output
    if output_format == OutputFormat.JSON:
        output = {
            "rkey": rkey,
            "uri": response.uri,
            "cid": response.cid,
            **value_dict,
        }
        print(json.dumps(output, indent=2))
        return

    # yaml output
    if output_format == OutputFormat.YAML:
        output = {
            "rkey": rkey,
            "uri": response.uri,
            "cid": response.cid,
            **value_dict,
        }
        print(yaml.dump(output, default_flow_style=False, sort_keys=False))
        return

    # compact output
    if output_format == OutputFormat.COMPACT:
        print(f"{rkey}: {json.dumps(value_dict, separators=(',', ':'))}")
        return

    # table output (default) - rich panel with table
    table = Table(show_header=False, box=None)
    table.add_column("key", style="cyan")
    table.add_column("value", style="white")

    table.add_row("uri", response.uri)
    table.add_row("cid", response.cid)

    for key, val in value_dict.items():
        if key not in ("$type", "py_type"):
            table.add_row(key, str(val))

    console.print(Panel(table, title="[bold]record[/bold]", border_style="dim"))


def display_success(operation: str, uri: str, cid: str, collection: str = "") -> None:
    """display a success message.

    Args:
        operation: operation performed (created, updated, deleted)
        uri: record uri
        cid: record cid
        collection: optional collection name
    """
    title = f"[bold]{collection}[/bold]" if collection else ""
    content = f"[green]✓[/green] {operation}"

    if uri:
        content += f"\n\n[dim]uri:[/dim] {uri}"
    if cid:
        content += f"\n[dim]cid:[/dim] {cid}"

    console.print(Panel(content, title=title, border_style="green"))
