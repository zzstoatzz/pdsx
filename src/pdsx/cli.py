"""general-purpose cli for atproto record operations."""

from __future__ import annotations

import argparse
import asyncio
import json
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
    display_repo_description,
    display_success,
)
from pdsx._internal.operations import (  # noqa: E402
    create_record,
    delete_record,
    describe_repo,
    get_record,
    list_records,
    update_record,
    upload_blob,
)
from pdsx._internal.output import OutputFormat  # noqa: E402
from pdsx._internal.parsing import parse_key_value_args  # noqa: E402
from pdsx._internal.permissioned import (  # noqa: E402
    PermissionedDataUnsupported,
    get_space_record,
    list_space_records,
    list_spaces,
)
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


async def cmd_describe(
    client: AsyncClient,
    repo: str,
    output_format: OutputFormat | None = None,
) -> None:
    """describe a repo, listing its collections."""
    response = await describe_repo(client, repo)
    fmt = output_format or OutputFormat.TABLE
    display_repo_description(response, output_format=fmt)


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
    rkey: str | None = None,
    concurrency: int = 10,
    fail_fast: bool = False,
) -> None:
    """create one or more records."""
    handle = client.me.handle if client.me else ""

    # single record - use existing behavior for backward compatibility
    if len(records) == 1:
        response = await create_record(client, collection, records[0], rkey=rkey)
        display_success("created", response.uri, response.cid, collection, handle)
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

    from atproto_client.models.blob_ref import IpldLink

    # a successful blob upload always returns an IpldLink ref; narrow the
    # union (str | bytes | IpldLink) so `.link` resolves
    ref = response.blob.ref
    link = ref.link if isinstance(ref, IpldLink) else ref
    blob_ref = {
        "$type": "blob",
        "ref": {"$link": link},
        "mimeType": response.blob.mime_type,
        "size": response.blob.size,
    }
    console.print("[green]✓[/green] blob uploaded successfully")
    console.print("\n[bold]blob reference:[/bold]")
    console.print(json.dumps(blob_ref, indent=2))
    console.print(
        "\n[dim]use this blob reference in records (e.g., for post embeds)[/dim]"
    )


async def cmd_whoami(client: AsyncClient) -> None:
    """show authenticated identity."""
    if not client.me:
        console.print("[red]error:[/red] not authenticated")
        return

    console.print(f"[bold]{client.me.handle}[/bold] ({client.me.did})")


def _print_unsupported(exc: PermissionedDataUnsupported) -> None:
    console.print(f"[yellow]permissioned data unavailable:[/yellow] {exc}")


async def cmd_spaces_list(
    client: AsyncClient,
    pds_url: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
    output_format: OutputFormat | None = None,
) -> int:
    """list permissioned spaces, degrading to an empty result if unsupported.

    Enumeration has a legitimate empty answer, so an unsupported PDS is
    reported explicitly and exits 0 rather than failing — but it always says
    why, so "none" is never silently indistinguishable from "can't ask".
    """
    try:
        result = await list_spaces(client, pds_url, limit=limit, cursor=cursor)
    except PermissionedDataUnsupported as exc:
        if output_format == OutputFormat.JSON:
            print(json.dumps({"supported": False, "spaces": []}, indent=2))
        else:
            _print_unsupported(exc)
        return 0

    spaces = result.get("spaces", [])
    if output_format == OutputFormat.JSON:
        print(json.dumps({"supported": True, **result}, indent=2))
        return 0

    if not spaces:
        console.print("[dim]no spaces[/dim]")
        return 0
    for space in spaces:
        owner = " [dim](owner)[/dim]" if space.get("isOwner") else ""
        console.print(f"{space.get('uri')}{owner}")
    if result.get("cursor"):
        console.print(f"\n[dim]cursor: {result['cursor']}[/dim]")
    return 0


async def cmd_space_records(
    client: AsyncClient,
    pds_url: str,
    *,
    space: str,
    repo: str,
    collection: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    exclude_values: bool = False,
    output_format: OutputFormat | None = None,
) -> int:
    """list records in a permissioned space."""
    try:
        result = await list_space_records(
            client,
            pds_url,
            space=space,
            repo=repo,
            collection=collection,
            limit=limit,
            cursor=cursor,
            exclude_values=exclude_values,
        )
    except PermissionedDataUnsupported as exc:
        # a specific space was named, so there is no honest empty answer here
        _print_unsupported(exc)
        return 1

    if output_format == OutputFormat.JSON:
        print(json.dumps(result, indent=2))
        return 0

    records = result.get("records", [])
    if not records:
        console.print("[dim]no records[/dim]")
        return 0
    for record in records:
        console.print(f"{record.get('collection')}/{record.get('rkey')}")
    if result.get("cursor"):
        console.print(f"\n[dim]cursor: {result['cursor']}[/dim]")
    return 0


async def cmd_space_get(
    client: AsyncClient,
    pds_url: str,
    *,
    space: str,
    repo: str,
    collection: str,
    rkey: str,
    output_format: OutputFormat | None = None,
) -> int:
    """get one record from a permissioned space."""
    try:
        result = await get_space_record(
            client,
            pds_url,
            space=space,
            repo=repo,
            collection=collection,
            rkey=rkey,
        )
    except PermissionedDataUnsupported as exc:
        _print_unsupported(exc)
        return 1

    print(json.dumps(result, indent=2))
    return 0


async def async_main() -> int:
    """main entry point."""
    parser = argparse.ArgumentParser(
        description="atproto record operations",
        epilog="""
examples:
  # list collections in a repo
  pdsx -r zzstoatzz.io ls

  # read posts (no auth needed, -r is required)
  pdsx -r zzstoatzz.io ls app.bsky.feed.post

  # read with DID (more durable than handle)
  pdsx -r did:plc:abc123 ls app.bsky.feed.post

  # create a record (requires auth)
  pdsx --handle you.bsky.social --password xxxx-xxxx create app.bsky.feed.post text='hello'

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
        "collection",
        nargs="?",
        default=None,
        help="collection name (e.g., app.bsky.feed.post). omit to list collections in the repo",
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
        "--rkey",
        help="record key (e.g., 'self' for profile records)",
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

    # whoami (me/identity aliases)
    subparsers.add_parser(
        "whoami", aliases=["me", "identity"], help="show authenticated identity"
    )

    # spaces - experimental permissioned data (com.atproto.space.*)
    spaces_parser = subparsers.add_parser(
        "spaces",
        help="experimental: read permissioned data (not served by most PDSes)",
    )
    spaces_sub = spaces_parser.add_subparsers(dest="spaces_command")

    spaces_ls = spaces_sub.add_parser("ls", help="list your permissioned spaces")
    spaces_ls.add_argument("--limit", type=int, default=50, help="max spaces")
    spaces_ls.add_argument("--cursor", help="pagination cursor")
    spaces_ls.add_argument(
        "-o", "--output", choices=["json", "compact"], help="output format"
    )

    spaces_records = spaces_sub.add_parser(
        "records", help="list records in a permissioned space"
    )
    spaces_records.add_argument("--space", required=True, help="space URI")
    spaces_records.add_argument(
        "--repo", dest="space_repo", required=True, help="writer repo DID"
    )
    spaces_records.add_argument("--collection", help="filter to one collection")
    spaces_records.add_argument("--limit", type=int, default=50, help="max records")
    spaces_records.add_argument("--cursor", help="pagination cursor")
    spaces_records.add_argument(
        "--exclude-values",
        action="store_true",
        help="omit record values (collection/rkey/cid only)",
    )
    spaces_records.add_argument(
        "-o", "--output", choices=["json", "compact"], help="output format"
    )

    spaces_get = spaces_sub.add_parser(
        "get", help="get one record from a permissioned space"
    )
    spaces_get.add_argument("--space", required=True, help="space URI")
    spaces_get.add_argument(
        "--repo", dest="space_repo", required=True, help="writer repo DID"
    )
    spaces_get.add_argument("--collection", required=True, help="collection NSID")
    spaces_get.add_argument("--rkey", required=True, help="record key")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # capture before the assignment below, which would itself mark the field set
    pds_configured = "atproto_pds_url" in settings.model_fields_set

    # update pds if provided
    if args.pds:
        settings.atproto_pds_url = args.pds

    try:
        # determine if auth is needed
        # reads with --repo don't need auth, writes always need auth
        read_commands = ("list", "ls", "get", "cat")
        is_read = args.command in read_commands
        has_repo_target = args.repo is not None

        # for get/cat, a full AT-URI contains the repo already
        is_get_with_full_uri = (
            args.command in ("get", "cat")
            and hasattr(args, "uri")
            and args.uri
            and args.uri.startswith("at://")
        )

        # for reads without --repo (and not a full URI), require the flag
        if is_read and not has_repo_target and not is_get_with_full_uri:
            console.print(
                "[red]error:[/red] -r/--repo is required for read operations\n"
                f"example: pdsx -r someone.bsky.social {args.command} ..."
            )
            return 1

        # auth required only for write operations
        auth_needed = not is_read

        # create client with or without base_url depending on auth
        if auth_needed:
            # writes must go to the account's own PDS: a bare AsyncClient()
            # defaults to bsky.social, which mints a token the real PDS then
            # rejects with BadJwtSignature (self-hosted accounts)
            handle = args.handle or settings.atproto_handle
            if args.pds or pds_configured:
                pds_url = settings.atproto_pds_url
            elif handle:
                pds_url = await discover_pds(handle)
            else:
                pds_url = settings.atproto_pds_url
            client = AsyncClient(base_url=pds_url)

            await login(
                client,
                args.handle or settings.atproto_handle,
                args.password or settings.atproto_password,
                silent=True,
                required=True,
            )
        else:
            if args.pds:
                # prefer explicit --pds flag if provided
                pds_url = args.pds
            elif args.repo:
                # for unauthenticated reads, auto-discover PDS
                pds_url = await discover_pds(args.repo)
            elif is_get_with_full_uri:
                # extract DID from at://did/collection/rkey
                did = args.uri.replace("at://", "").split("/")[0]
                pds_url = await discover_pds(did)
            else:
                pds_url = settings.atproto_pds_url
            client = AsyncClient(base_url=pds_url)

        if args.command in ("list", "ls"):
            output_fmt = OutputFormat(args.output) if args.output else None
            if args.collection is None:
                await cmd_describe(client, args.repo, output_format=output_fmt)
            else:
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
                rkeys: list[str | None] | None = None
                rkey = args.rkey
            else:
                # batch records from stdin (JSONL format)
                # each record may have its own rkey
                try:
                    parsed = read_records_from_stdin()
                except ValueError as e:
                    console.print(f"[red]error:[/red] {e}")
                    return 1

                if not parsed:
                    console.print(
                        "[red]error:[/red] no records provided (use key=value arguments or pipe JSONL to stdin)"
                    )
                    return 1

                records = [r for r, _ in parsed]
                rkeys = [rk for _, rk in parsed]
                rkey = args.rkey  # CLI --rkey overrides per-record rkeys for single

            if not records:
                console.print(
                    "[red]error:[/red] no records provided (use key=value arguments or pipe JSONL to stdin)"
                )
                return 1

            if len(records) == 1:
                await cmd_create(
                    client,
                    args.collection,
                    records,
                    rkey=rkey or (rkeys[0] if rkeys else None),
                    concurrency=args.concurrency,
                    fail_fast=args.fail_fast,
                )
            else:
                # batch: use per-record rkeys from JSONL
                show_progress = sys.stdout.isatty()
                result = await batch_create(
                    client,
                    args.collection,
                    records,
                    rkeys=rkeys,
                    concurrency=args.concurrency,
                    fail_fast=args.fail_fast,
                    show_progress=show_progress,
                )
                display_batch_result(result, "created")

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

        elif args.command in ("whoami", "me", "identity"):
            await cmd_whoami(client)

        elif args.command == "spaces":
            spaces_fmt = (
                OutputFormat(args.output) if getattr(args, "output", None) else None
            )
            if args.spaces_command == "ls":
                return await cmd_spaces_list(
                    client,
                    pds_url,
                    limit=args.limit,
                    cursor=args.cursor,
                    output_format=spaces_fmt,
                )
            if args.spaces_command == "records":
                return await cmd_space_records(
                    client,
                    pds_url,
                    space=args.space,
                    repo=args.space_repo,
                    collection=args.collection,
                    limit=args.limit,
                    cursor=args.cursor,
                    exclude_values=args.exclude_values,
                    output_format=spaces_fmt,
                )
            if args.spaces_command == "get":
                return await cmd_space_get(
                    client,
                    pds_url,
                    space=args.space,
                    repo=args.space_repo,
                    collection=args.collection,
                    rkey=args.rkey,
                )
            spaces_parser.print_help()
            return 1

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
