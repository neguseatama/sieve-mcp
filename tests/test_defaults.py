"""MC-T14: the two vault folders are the default exclusion of the
folder-targeting tools, a direct file never gets excluded, and every
other hidden folder keeps the Tray behavior."""

import json
from pathlib import Path

from helpers import layer_for


def test_mct14_observe_excludes_the_two_vault_folders(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    observed = layer.call("observe_hidden_text", {"path": "."})
    assert observed["check_version"] == 1
    assert observed["excluded_dirs"] == 2
    paths = [item["path"] for item in observed["items"]]
    assert "sample.txt" in paths
    assert ".obsidian/workspace.json" not in paths
    assert ".trash/junk.txt" not in paths
    # every other hidden folder keeps the Tray behavior: it stays
    assert ".git/config" in paths


def test_mct14_prepare_excludes_the_vault_folders(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    paths = [item["path"] for item in prepared["items"]]
    assert "sample.txt" in paths
    assert not any(p.startswith(".obsidian/") for p in paths)
    assert not any(p.startswith(".trash/") for p in paths)


def test_mct14_file_list_excludes_the_vault_folders(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    listed = layer.call("create_file_list", {"path": "."})
    # sample.txt, plain.txt, three pdfs, meta.png and .git/config -
    # the two vault folders are out
    assert listed["file_count"] == 7
    record = out_dir / listed["record_path"]
    items = json_items(record)
    rels = [it["path"] for it in items]
    assert not any(r.startswith(".obsidian/") for r in rels)
    assert not any(r.startswith(".trash/") for r in rels)
    assert ".git/config" in rels


def json_items(record: Path):
    import json
    obj = json.loads(record.read_text(encoding="utf-8"))
    return obj["items"]


def test_mct14_direct_file_never_gets_excluded(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    observed = layer.call("observe_hidden_text",
                          {"path": ".obsidian/workspace.json"})
    assert observed["excluded_dirs"] == 0
    paths = [item["path"] for item in observed["items"]]
    assert paths == [".obsidian/workspace.json"]
    cleaned = layer.call("remove_metadata",
                         {"path": ".obsidian/workspace.json"})
    assert cleaned["items"][0]["path"] == ".obsidian/workspace.json"
    assert cleaned["items"][0]["status"] == "not_applicable"


def test_mct14_limits_are_enforced(root_dir, out_dir):
    from sieve_mcp_server.errors import ToolError
    from sieve_mcp_server.paths import Spaces
    from sieve_mcp_server.tools import ToolLayer
    spaces = Spaces([str(root_dir)], str(out_dir), max_files=2)
    layer = ToolLayer(spaces)
    for name in ("prepare_for_sharing", "observe_hidden_text",
                 "create_file_list"):
        try:
            layer.call(name, {"path": "."})
            raise AssertionError("%s must refuse the folder" % name)
        except ToolError as e:
            assert e.code == "too_large", name
    # a direct file rides the same cap by its own size
    spaces2 = Spaces([str(root_dir)], str(out_dir), max_file_bytes=4)
    layer2 = ToolLayer(spaces2)
    try:
        layer2.call("prepare_for_sharing", {"path": "sample.txt"})
        raise AssertionError("the oversized file must be refused")
    except ToolError as e:
        assert e.code == "too_large"
