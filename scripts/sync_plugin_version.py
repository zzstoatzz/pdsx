"""sync the codex plugin manifest version from the latest git tag.

versions are never hand-written: pdsx derives its package version from git
tags via uv-dynamic-versioning, and the plugin manifest has to agree or it
starts lying the moment a release is cut.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MANIFEST = (
    Path(__file__).resolve().parent.parent / "plugins/pdsx/.codex-plugin/plugin.json"
)


def latest_tag() -> str | None:
    try:
        tag = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None
    return tag.lstrip("v") or None


def main() -> int:
    version = latest_tag()
    if version is None:
        # a shallow clone or a repo with no tags yet: leave the file alone
        # rather than write a placeholder that outlives the checkout
        return 0

    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("version") == version:
        return 0

    manifest["version"] = version
    with MANIFEST.open("w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"synced plugin version -> {version}")
    return 1  # signal a modification, as pre-commit expects


if __name__ == "__main__":
    sys.exit(main())
