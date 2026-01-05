"""web URL generation for ATProto records.

maps collection namespaces to web app URL patterns. the collection namespace
(e.g., app.bsky) hints at which app ecosystem the record belongs to.
"""

from __future__ import annotations

# URL patterns by collection type
# {handle} and {rkey} are replaced with actual values
WEB_URL_PATTERNS: dict[str, str] = {
    "app.bsky.feed.post": "https://bsky.app/profile/{handle}/post/{rkey}",
    "app.bsky.actor.profile": "https://bsky.app/profile/{handle}",
    "app.bsky.graph.list": "https://bsky.app/profile/{handle}/lists/{rkey}",
    "app.bsky.feed.generator": "https://bsky.app/profile/{handle}/feed/{rkey}",
}


def get_web_url(uri: str, handle: str) -> str | None:
    """get web URL for a record if a pattern is known.

    args:
        uri: AT-URI (at://did/collection/rkey)
        handle: user's handle for the URL

    returns:
        web URL or None if no pattern is known for this collection
    """
    # parse at://did/collection/rkey
    parts = uri.replace("at://", "").split("/")
    if len(parts) < 3:
        return None

    collection = parts[1]
    rkey = parts[2]

    pattern = WEB_URL_PATTERNS.get(collection)
    if not pattern:
        return None

    return pattern.format(handle=handle, rkey=rkey)
