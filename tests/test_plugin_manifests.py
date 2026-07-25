"""tests for the claude code / codex plugin manifests.

These files ship the plugin but are not importable code, so nothing else in
the suite touches them. #62 shipped a `.mcp.json` missing its `mcpServers`
wrapper key — it registered no servers at all and went unnoticed for months,
because a malformed manifest fails silently at install time rather than
loudly in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "pdsx"

MANIFESTS = [
    REPO / ".mcp.json",
    REPO / ".claude-plugin" / "plugin.json",
    REPO / ".claude-plugin" / "marketplace.json",
    REPO / ".agents" / "plugins" / "marketplace.json",
    PLUGIN / ".mcp.json",
    PLUGIN / ".codex-plugin" / "plugin.json",
]


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: str(p.relative_to(REPO)))
def test_manifest_is_valid_json(path: Path) -> None:
    assert path.exists(), f"missing manifest: {path.relative_to(REPO)}"
    json.loads(path.read_text())


@pytest.mark.parametrize(
    "path",
    [REPO / ".mcp.json", PLUGIN / ".mcp.json"],
    ids=["root", "plugin"],
)
def test_mcp_json_declares_servers(path: Path) -> None:
    """the wrapper key is the whole contract — without it, nothing registers."""
    config = json.loads(path.read_text())
    assert "mcpServers" in config, f"{path.relative_to(REPO)} has no mcpServers key"
    assert config["mcpServers"], "mcpServers is empty"
    assert "pdsx" in config["mcpServers"]


def test_claude_manifest_paths_resolve() -> None:
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    for key in ("skills", "mcpServers"):
        target = (REPO / manifest[key]).resolve()
        assert target.exists(), f"claude plugin.json {key} -> {manifest[key]} missing"


def test_codex_manifest_paths_resolve() -> None:
    """codex paths are relative to the plugin directory, not the repo root."""
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    for key in ("skills", "mcpServers"):
        target = (PLUGIN / manifest[key]).resolve()
        assert target.exists(), f"codex plugin.json {key} -> {manifest[key]} missing"


def test_agents_marketplace_path_resolves() -> None:
    manifest = json.loads(
        (REPO / ".agents" / "plugins" / "marketplace.json").read_text()
    )
    source = manifest["plugins"][0]["source"]["path"]
    assert (REPO / source).resolve().is_dir(), f"agents source {source} missing"


def test_every_skill_has_usable_frontmatter() -> None:
    """discovery only sees name + description, so both must be present."""
    skills = sorted(d for d in (PLUGIN / "skills").iterdir() if d.is_dir())
    assert skills, "no skills found"

    for skill in skills:
        doc = skill / "SKILL.md"
        assert doc.exists(), f"{skill.name} has no SKILL.md"

        text = doc.read_text()
        assert text.startswith("---\n"), f"{skill.name}: no frontmatter"
        frontmatter = text.split("---", 2)[1]

        for field in ("name:", "description:"):
            assert field in frontmatter, f"{skill.name}: frontmatter missing {field}"

        declared = next(
            line.split(":", 1)[1].strip()
            for line in frontmatter.splitlines()
            if line.startswith("name:")
        )
        assert declared == skill.name, (
            f"{skill.name}: frontmatter name is {declared!r}; "
            "the directory name is what clients invoke"
        )


def test_no_hand_written_versions() -> None:
    """versions come from git tags, never from a literal in a manifest.

    the package version is derived by uv-dynamic-versioning; a hardcoded
    manifest version is wrong the moment the next release is cut.
    """
    import subprocess

    tagged = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if tagged.returncode != 0:
        pytest.skip("no git tags available in this checkout")
    expected = tagged.stdout.strip().lstrip("v")

    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    assert codex.get("version") == expected, (
        f"codex manifest version is {codex.get('version')!r}, git tag says "
        f"{expected!r} — run scripts/sync_plugin_version.py"
    )

    claude = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert "version" not in claude, (
        "the claude manifest should carry no version at all; it has no "
        "generator to keep one honest"
    )
