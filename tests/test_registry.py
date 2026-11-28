"""MC-T15 (the ownership line of the README matches the registry
name), MC-T16 (the server.json file rides the current registry schema
with one version, not a range) and MC-T17 (the one runtime dependency
declares an upper bound)."""

import json
import re

from helpers import REPO_ROOT

REGISTRY_NAME = "io.github.neguseatama/sieve-mcp"


def test_mct15_the_readmes_carry_the_ownership_line_once():
    for name in ("README.md", "README.ja.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        lines = [ln.strip() for ln in text.splitlines()]
        hits = [ln for ln in lines if ln == "mcp-name: " + REGISTRY_NAME]
        # one independent line per README: the token rides alone, so
        # the registry's README check finds it in the package's
        # description text
        assert len(hits) == 1, name


def test_mct16_server_json_rides_the_registry_shape():
    from sieve_mcp_server import __version__
    doc = json.loads(
        (REPO_ROOT / "server.json").read_text(encoding="utf-8"))
    assert doc["$schema"] == (
        "https://static.modelcontextprotocol.io/schemas/"
        "2025-12-11/server.schema.json")
    # the namespace form the GitHub login requires
    assert re.fullmatch(r"io\.github\.[^/]+/[^/]+", doc["name"])
    assert doc["name"] == REGISTRY_NAME
    assert 1 <= len(doc["description"]) <= 100
    # one version, not a range: the registry publishes one revision of
    # one version
    assert doc["version"] == __version__
    packages = doc["packages"]
    assert len(packages) == 1
    pkg = packages[0]
    assert pkg["registryType"] == "pypi"
    assert pkg["identifier"] == "sieve-mcp-server"
    assert pkg["version"] == __version__
    assert pkg["runtimeHint"] == "uvx"
    assert pkg["transport"] == {"type": "stdio"}
    args = {a["name"]: a for a in pkg["packageArguments"]}
    assert set(args) == {"--root", "--out"}
    for flag in ("--root", "--out"):
        arg = args[flag]
        assert arg["type"] == "named"
        assert arg["isRequired"] is True
        assert arg["format"] == "filepath"
        assert isinstance(arg.get("description"), str) and arg["description"]
    assert isinstance(doc.get("repository"), dict)


def test_mct17_the_dependency_declares_an_upper_bound():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lines = text.splitlines()
    dep = next(ln for ln in lines
               if ln.strip().startswith("dependencies"))
    # the floor stays 2.6.0 (the first engine set the server needs) and
    # the ceiling stays inside the 2.x line, so a 3.x rewrite never
    # enters an install of this server unasked
    assert '"sieve-tray>=2.6.0,<3"' in dep
    # the runtime side stays one dependency without extras
    assert dep.count('"') == 2, dep
