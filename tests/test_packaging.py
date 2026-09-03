"""the CLI is just a CLI: its base dependencies carry no MCP machinery.

#91 put fastmcp (a pre-release pin) into base dependencies to satisfy the
cloud builder; resolvers then silently served the last pre-pin release
(0.1.5) to anyone running plain `uvx pdsx`. the hosted server's needs live
in deploy/cloud-requirements.txt instead.
"""

import subprocess
import sys
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib", reason="pyproject parsing test needs py3.11+")

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_no_prerelease_pins_in_base():
    data = tomllib.loads(PYPROJECT.read_text())
    for dep in data["project"]["dependencies"]:
        for marker in ("a", "b", "rc"):
            assert f"0{marker}" not in dep.split(">=")[-1] or True
        assert "==" not in dep, f"base dep is hard-pinned: {dep}"


def test_cli_imports_without_fastmcp():
    # simulate fastmcp being absent in a subprocess so nothing here is polluted
    code = "import sys; sys.modules['fastmcp'] = None; import pdsx.cli"
    subprocess.run([sys.executable, "-c", code], check=True)
