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


def test_mct20_the_folder_questions_carry_the_two_folder_rule():
    # the two questions state the rule themselves: the folders must
    # exist, they must differ, and neither may contain the other - a
    # start with one folder for both is refused, so the questions say
    # the rule before the answer arrives
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_mcpb", REPO_ROOT / "tools" / "build_mcpb.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    questions = module.build_manifest("0.0.0")["user_config"]
    for key in ("root", "out"):
        description = questions[key]["description"]
        assert "existing folder" in description, key
        assert "different from" in description, key
        assert "neither folder may contain the other" in description, key


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
    stage = dest / "sieve-mcp"
    manifest = json.loads(
        (stage / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.3"
    assert manifest["name"] == "sieve-mcp"
    # the manifest's version is written from the package's single
    # source, never typed by hand
    assert manifest["version"] == __version__
    assert manifest["author"] == {"name": "Kai IWASAKI"}
    assert manifest["license"] == "MIT"
    assert manifest["icon"] == "icon.png"
    png = (REPO_ROOT / "icon.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    staged_icon = stage / "icon.png"
    assert staged_icon.is_file()
    assert staged_icon.read_bytes() == png
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
    launcher = (stage / "server" / "server.py").read_text(
        encoding="utf-8")
    assert "sieve_mcp_server.cli" in launcher
    lib = stage / "server" / "lib"
    assert (lib / "sieve_mcp_server").is_dir()
    assert (lib / "sieve_tray.py").is_file()
    # no compiled part rides the bundle
    compiled = [p.name for p in lib.rglob("*")
                if p.suffix in (".so", ".pyd")]
    assert compiled == []
