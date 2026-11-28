"""MC-T20: the .mcpb bundle rides the package's single version source
and the recipe is the checked-in script - the bundled libraries, the
launcher and the manifest are built by tools/build_mcpb.py, with no
compiled part and the two folder questions asked from the user."""

import json
import subprocess
import sys
from pathlib import Path

from helpers import REPO_ROOT
from test_package import _build_wheel


def test_mct20_the_bundle_recipe_rides_the_package_version(tmp_path):
    wheel = _build_wheel(tmp_path)
    dest = tmp_path / "bundle"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build_mcpb.py"),
         "--wheel", str(wheel), "--dest", str(dest), "--no-pack"],
        capture_output=True, timeout=900, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, (
        proc.stdout.decode("utf-8", "replace")[-2000:]
        + proc.stderr.decode("utf-8", "replace")[-4000:])
    from sieve_mcp_server import __version__
    manifest = json.loads(
        (dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.3"
    assert manifest["name"] == "sieve-mcp"
    # the manifest's version is written from the package's single
    # source, never typed by hand
    assert manifest["version"] == __version__
    assert manifest["author"] == {"name": "Kai IWASAKI"}
    assert manifest["license"] == "MIT"
    server = manifest["server"]
    assert server["type"] == "python"
    assert server["entry_point"] == "server/server.py"
    config = server["mcp_config"]
    assert "${__dirname}/server/server.py" in config["args"]
    assert "${user_config.root}" in config["args"]
    assert "${user_config.out}" in config["args"]
    assert config["env"]["PYTHONPATH"] == "${__dirname}/server/lib"
    # the launch command: macOS machines ship python3 only, the Windows
    # installs answer to python - the override rides the manifest
    assert config["command"] == "python3"
    assert config["platform_overrides"]["win32"] == {"command": "python"}
    questions = manifest["user_config"]
    for key in ("root", "out"):
        entry = questions[key]
        assert entry["type"] == "directory", key
        assert entry["required"] is True, key
    # the launcher rides the bundle and starts the console entry point
    launcher = (dest / "server" / "server.py").read_text(encoding="utf-8")
    assert "sieve_mcp_server.cli" in launcher
    lib = dest / "server" / "lib"
    assert (lib / "sieve_mcp_server").is_dir()
    assert (lib / "sieve_tray.py").is_file()
    # no compiled part rides the bundle
    compiled = [p.name for p in lib.rglob("*")
                if p.suffix in (".so", ".pyd")]
    assert compiled == []
