"""web URL generation for ATProto records.

maps collection namespaces to web app URL patterns. the collection namespace
(e.g., app.bsky) hints at which app ecosystem the record belongs to.

mappings derived from:
https://github.com/notjuliet/pdsls/blob/main/src/utils/templates.ts
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# type for template functions
# takes (repo, rkey, record) and returns URL or None
TemplateFn = Callable[[str, str, dict[str, Any] | None], str | None]


def _bsky_profile(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://bsky.app/profile/{repo}"


def _bsky_post(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://bsky.app/profile/{repo}/post/{rkey}"


def _bsky_list(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://bsky.app/profile/{repo}/lists/{rkey}"


def _bsky_feed(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://bsky.app/profile/{repo}/feed/{rkey}"


def _bsky_starterpack(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://bsky.app/starter-pack/{repo}/{rkey}"


def _frontpage_post(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://frontpage.fyi/post/{repo}/{rkey}"


def _pinksea_oekaki(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://pinksea.art/{repo}/oekaki/{rkey}"


def _pinksea_profile(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://pinksea.art/{repo}"


def _linkat_board(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://linkat.blue/{repo}"


def _tangled_profile(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://tangled.org/{repo}"


def _tangled_repo(repo: str, rkey: str, record: dict[str, Any] | None) -> str | None:
    # needs record.name to construct URL
    if record and "name" in record:
        return f"https://tangled.org/{repo}/{record['name']}"
    return None


def _leaflet_document(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://leaflet.pub/p/{repo}/{rkey}"


def _leaflet_publication(repo: str, rkey: str, record: dict[str, Any] | None) -> str:
    return f"https://leaflet.pub/lish/{repo}/{rkey}"


# URL patterns by collection type
# derived from https://github.com/notjuliet/pdsls/blob/main/src/utils/templates.ts
WEB_URL_TEMPLATES: dict[str, TemplateFn] = {
    # bluesky
    "app.bsky.actor.profile": _bsky_profile,
    "app.bsky.feed.post": _bsky_post,
    "app.bsky.graph.list": _bsky_list,
    "app.bsky.feed.generator": _bsky_feed,
    "app.bsky.graph.starterpack": _bsky_starterpack,
    # frontpage
    "fyi.unravel.frontpage.post": _frontpage_post,
    # pinksea
    "com.shinolabs.pinksea.oekaki": _pinksea_oekaki,
    "com.shinolabs.pinksea.profile": _pinksea_profile,
    # linkat
    "blue.linkat.board": _linkat_board,
    # tangled
    "sh.tangled.actor.profile": _tangled_profile,
    "sh.tangled.repo": _tangled_repo,
    # leaflet
    "pub.leaflet.document": _leaflet_document,
    "pub.leaflet.publication": _leaflet_publication,
}


def get_web_url(
    uri: str,
    handle: str | None = None,
    record: dict[str, Any] | None = None,
) -> str | None:
    """get web URL for a record if a pattern is known.

    args:
        uri: AT-URI (at://did/collection/rkey)
        handle: optional handle to use instead of DID (more readable)
        record: optional record data (needed for some URL patterns)

    returns:
        web URL or None if no pattern is known for this collection
    """
    # parse at://did/collection/rkey
    parts = uri.replace("at://", "").split("/")
    if len(parts) < 2:
        return None

    repo_did = parts[0]
    collection = parts[1]
    rkey = parts[2] if len(parts) > 2 else ""

    template = WEB_URL_TEMPLATES.get(collection)
    if not template:
        return None

    # prefer handle over DID for readability (matches official bluesky social-app)
    repo = handle if handle else repo_did

    return template(repo, rkey, record)
