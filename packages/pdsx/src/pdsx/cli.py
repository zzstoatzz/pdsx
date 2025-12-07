"""general-purpose cli for atproto record operations."""

from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from typing import NoReturn

# suppress pydantic warnings from atproto library
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from atproto import AsyncClient  # noqa: E402

from pdsx import __version__  # noqa: E402
from pdsx._internal.auth import login  # noqa: E402
from pdsx._internal.batch import (  # noqa: E402
    batch_create,
    batch_delete,
    batch_update,
    display_batch_result,
    read_records_from_stdin,
    read_updates_from_stdin,
    read_uris_from_stdin,
)
from pdsx._internal.config import settings  # noqa: E402
from pdsx._internal.display import (  # noqa: E402
    console,
    display_record,
    display_records,
    display_success,
)
from pdsx._internal.operations import (  # noqa: E402
    create_record,
    delete_record,
    get_record,
    list_records,
    update_record,
    upload_blob,
)
from pdsx._internal.output import OutputFormat  # noqa: E402
from pdsx._internal.parsing import parse_key_value_args  # noqa: E402
from pdsx._internal.resolution import discover_pds  # noqa: E402
from pdsx._internal.types import RecordValue  # noqa: E402


async def cmd_list(
    client: AsyncClient,
    collection: str,
    limit: int,
    repo: str | None = None,
    cursor: str | None = None,
    output_format: OutputFormat | None = None,
) -> None:
    """list records in a collection."""
    response = await list_records(client, collection, limit, repo, cursor)

    # determine output format - default to compact (most readable for most data)
    fmt = output_format or OutputFormat.COMPACT

    display_records(collection, response.records, output_format=fmt)

    # display cursor if there are more pages
    # for structured output formats (json/yaml), send to stderr to avoid breaking parsing
    if response.cursor:
        structured_formats = (OutputFormat.JSON, OutputFormat.YAML)
        if fmt in structured_formats:
            # use stderr for structured formats to avoid breaking json/yaml parsing
            print(f"\nnext page cursor: {response.cursor}", file=sys.stderr)
        else:
            console.print(f"\n[dim]next page cursor:[/dim] {response.cursor}")


async def cmd_get(
    client: AsyncClient,
    uri: str,
    output_format: OutputFormat | None = None,
    repo: str | None = None,
) -> None:
    """get a specific record."""
    response = await get_record(client, uri, repo=repo)
    fmt = output_format or OutputFormat.TABLE
    display_record(response, output_format=fmt)


async def cmd_create(
    client: AsyncClient,
    collection: str,
    records: list[dict[str, RecordValue]],
    *,
    concurrency: int = 10,
    fail_fast: bool = False,
) -> None:
    """create one or more records."""
    # single record - use existing behavior for backward compatibility
    if len(records) == 1:
        response = await create_record(client, collection, records[0])
        display_success("created", response.uri, response.cid, collection)
        return

    # multiple records - use batch operations
    show_progress = sys.stdout.isatty()  # only show progress if interactive
    result = await batch_create(
        client,
        collection,
        records,
        concurrency=concurrency,
        fail_fast=fail_fast,
        show_progress=show_progress,
    )
    display_batch_result(result, "created")


async def cmd_update(
    client: AsyncClient,
    updates_list: list[tuple[str, dict[str, RecordValue]]],
    *,
    concurrency: int = 10,
    fail_fast: bool = False,
) -> None:
    """update one or more records."""
    # single update - use existing behavior for backward compatibility
    if len(updates_list) == 1:
        uri, updates = updates_list[0]
        response = await update_record(client, uri, updates)
        display_success("updated", response.uri, response.cid)
        return

    # multiple updates - use batch operations
    show_progress = sys.stdout.isatty()  # only show progress if interactive
    result = await batch_update(
        client,
        updates_list,
        concurrency=concurrency,
        fail_fast=fail_fast,
        show_progress=show_progress,
    )
    display_batch_result(result, "updated")


async def cmd_delete(
    client: AsyncClient,
    uris: list[str],
    *,
    concurrency: int = 10,
    fail_fast: bool = False,
) -> None:
    """delete one or more records."""
    # single URI - use existing behavior for backward compatibility
    if len(uris) == 1:
        await delete_record(client, uris[0])
        display_success("deleted", "", "")
        return

    # multiple URIs - use batch operations
    show_progress = sys.stdout.isatty()  # only show progress if interactive
    result = await batch_delete(
        client,
        uris,
        concurrency=concurrency,
        fail_fast=fail_fast,
        show_progress=show_progress,
    )
    display_batch_result(result, "deleted")


async def cmd_upload_blob(client: AsyncClient, file_path: str) -> None:
    """upload a blob (image, video, etc.)."""
    response = await upload_blob(client, file_path)

    # display blob reference in json format for easy copying
    import json

    blob_ref = {
        "$type": "blob",
        "ref": {"$link": response.blob.ref.link},
        "mimeType": response.blob.mime_type,
        "size": response.blob.size,
    }
    console.print("[green]✓[/green] blob uploaded successfully")
    console.print("\n[bold]blob reference:[/bold]")
    console.print(json.dumps(blob_ref, indent=2))
    console.print(
        "\n[dim]use this blob reference in records (e.g., for post embeds)[/dim]"
    )


async def async_main() -> int:
    """main entry point."""
    parser = argparse.ArgumentParser(
        description="atproto record operations",
        epilog="""
examples:
  # read anyone's posts (no auth needed)
  pdsx -r zzstoatzz.io ls app.bsky.feed.post

  # read with DID (more durable than handle)
  pdsx -r did:plc:abc123 ls app.bsky.feed.post

  # list your own records (requires auth)
  pdsx --handle you.bsky.social --password xxxx-xxxx ls app.bsky.feed.post

  # create a record (requires auth)
  pdsx --handle you.bsky.social create app.bsky.feed.post text='hello'

note: -r flag goes BEFORE the command (ls, get, etc.)
      auth flags (--handle, --password) also go BEFORE the command
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # version flag
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"pdsx {__version__}",
    )

    # global identity flag - can be handle or DID
    parser.add_argument(
        "-r",
        "--repo",
        metavar="REPO",
        help="read from another repo (handle or DID) - no auth needed for public data",
    )

    # auth options (only needed for writes to your own repo)
    parser.add_argument(
        "--handle",
        help="your atproto handle for authentication (required for writes)",
    )
    parser.add_argument(
        "--password",
        help="your atproto app password",
    )
    parser.add_argument(
        "--pds",
        help="custom PDS URL (auto-discovered from handle if not specified)",
    )

    subparsers = parser.add_subparsers(dest="command", help="command")

    # list (ls alias)
    list_parser = subparsers.add_parser("list", aliases=["ls"], help="list records")
    list_parser.add_argument(
        "collection", help="collection name (e.g., app.bsky.feed.post)"
    )
    list_parser.add_argument("--limit", type=int, default=50, help="max records")
    list_parser.add_argument(
        "--cursor",
        help="pagination cursor from previous response",
    )
    list_parser.add_argument(
        "-o",
        "--output",
        choices=["json", "yaml", "table", "compact"],
        help="output format (default: compact)",
    )

    # get (cat alias)
    get_parser = subparsers.add_parser("get", aliases=["cat"], help="get record")
    get_parser.add_argument("uri", help="record AT-URI")
    get_parser.add_argument(
        "-o",
        "--output",
        choices=["json", "yaml", "table", "compact"],
        help="output format (default: table)",
    )

    # create (touch/add aliases)
    create_parser = subparsers.add_parser(
        "create", aliases=["touch", "add"], help="create record(s)"
    )
    create_parser.add_argument("collection", help="collection name")
    create_parser.add_argument(
        "fields",
        nargs="*",
        help="record fields as key=value pairs (e.g., title='My Song' artist='Artist') - reads JSONL from stdin if not provided",
    )
    create_parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="max concurrent operations for batch create (default: 10)",
    )
    create_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop on first error (default: continue on error)",
    )

    # update (edit alias)
    update_parser = subparsers.add_parser(
        "update", aliases=["edit"], help="update record(s)"
    )
    update_parser.add_argument(
        "uri", nargs="?", help="record AT-URI (not required if using stdin)"
    )
    update_parser.add_argument(
        "fields",
        nargs="*",
        help="fields to update as key=value pairs - reads JSONL from stdin if uri not provided",
    )
    update_parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="max concurrent operations for batch update (default: 10)",
    )
    update_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop on first error (default: continue on error)",
    )

    # delete (rm alias)
    delete_parser = subparsers.add_parser(
        "delete", aliases=["rm"], help="delete record(s)"
    )
    delete_parser.add_argument(
        "uris",
        nargs="*",
        help="record AT-URI(s) - reads from stdin if not provided",
    )
    delete_parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="max concurrent operations for batch delete (default: 10)",
    )
    delete_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop on first error (default: continue on error)",
    )

    # upload-blob
    upload_blob_parser = subparsers.add_parser(
        "upload-blob", help="upload a blob (image, video, etc.)"
    )
    upload_blob_parser.add_argument("file_path", help="path to file to upload")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # update pds if provided
    if args.pds:
        settings.atproto_pds_url = args.pds

    try:
        # determine if auth is needed
        # reads with --repo don't need auth, writes always need auth
        read_commands = ("list", "ls", "get", "cat")
        is_read = args.command in read_commands
        has_repo_target = args.repo is not None

        # auth required if: doing a write operation OR doing a read without --repo
        auth_needed = not is_read or not has_repo_target

        # create client with or without base_url depending on auth
        if auth_needed:
            # for authenticated operations, let SDK discover PDS from handle
            # unless user explicitly provided --pds flag
            client = AsyncClient(base_url=args.pds) if args.pds else AsyncClient()

            await login(
                client,
                args.handle or settings.atproto_handle,
                args.password or settings.atproto_password,
                silent=True,
                required=True,
            )
        else:
            # for unauthenticated reads with -r, auto-discover PDS from handle/DID
            pds_url = (
                await discover_pds(args.repo) if args.repo else settings.atproto_pds_url
            )
            client = AsyncClient(base_url=pds_url)

        if args.command in ("list", "ls"):
            output_fmt = OutputFormat(args.output) if args.output else None
            await cmd_list(
                client,
                args.collection,
                args.limit,
                args.repo,
                args.cursor,
                output_format=output_fmt,
            )

        elif args.command in ("get", "cat"):
            output_fmt = (
                OutputFormat[args.output.upper()] if args.output else OutputFormat.TABLE
            )
            await cmd_get(client, args.uri, output_format=output_fmt, repo=args.repo)

        elif args.command in ("create", "touch", "add"):
            # support batch create from stdin (JSONL) or single record from args
            if args.fields:
                # single record from command line args
                record = parse_key_value_args(args.fields)
                records = [record]
            else:
                # batch records from stdin (JSONL format)
                try:
                    records = read_records_from_stdin()
                except ValueError as e:
                    console.print(f"[red]error:[/red] {e}")
                    return 1

            if not records:
                console.print(
                    "[red]error:[/red] no records provided (use key=value arguments or pipe JSONL to stdin)"
                )
                return 1

            await cmd_create(
                client,
                args.collection,
                records,
                concurrency=args.concurrency,
                fail_fast=args.fail_fast,
            )

        elif args.command in ("update", "edit"):
            # support batch update from stdin (JSONL) or single update from args
            if args.uri and args.fields:
                # single update from command line args
                updates = parse_key_value_args(args.fields)
                updates_list = [(args.uri, updates)]
            elif not args.uri and not args.fields:
                # batch updates from stdin (JSONL format with uri field)
                try:
                    updates_list = read_updates_from_stdin()
                except ValueError as e:
                    console.print(f"[red]error:[/red] {e}")
                    return 1
            else:
                console.print(
                    "[red]error:[/red] provide both uri and fields, or pipe JSONL to stdin"
                )
                return 1

            if not updates_list:
                console.print(
                    "[red]error:[/red] no updates provided (use uri + key=value arguments or pipe JSONL to stdin)"
                )
                return 1

            await cmd_update(
                client,
                updates_list,
                concurrency=args.concurrency,
                fail_fast=args.fail_fast,
            )

        elif args.command in ("delete", "rm"):
            uris = args.uris if args.uris else read_uris_from_stdin()

            if not uris:
                console.print(
                    "[red]error:[/red] no URIs provided (use positional arguments or pipe to stdin)"
                )
                return 1

            await cmd_delete(
                client,
                uris,
                concurrency=args.concurrency,
                fail_fast=args.fail_fast,
            )

        elif args.command == "upload-blob":
            await cmd_upload_blob(client, args.file_path)

        return 0

    except Exception as e:
        console.print(f"[red]error:[/red] {e}")
        import os

        if os.getenv("DEBUG"):
            raise
        return 1


def main() -> NoReturn:
    """synchronous entry point."""
    sys.exit(asyncio.run(async_main()))
