"""MC-T09: the originals never change, everything written lives under
the output folder, and the numbered folders are never overwritten."""

import shutil

from helpers import layer_for, tree_files


def test_mct09_originals_unchanged_and_outputs_only_under_out(root_dir,
                                                              out_dir):
    before = tree_files(root_dir)
    layer = layer_for(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    layer.call("observe_hidden_text", {"path": "."})
    layer.call("create_file_list", {"path": "."})
    layer.call("remove_metadata", {"path": "meta.png"})
    layer.call("remove_metadata", {"path": "."})
    visible_rel = next(f["path"] for f in prepared["handoff_files"]
                       if f["path"].endswith("sample.txt.visible.txt"))
    layer.call("read_handoff", {"path": visible_rel})
    out_name = prepared["output_dir"]
    layer.call("verify_record",
               {"record": out_name + "/handoff/gate-receipt.json",
                "against": out_name})
    after = tree_files(root_dir)
    assert before == after
    # the outputs live under the output folder only (the fixture tree
    # above proves the roots; the output tree holds the run folders)
    assert (out_dir / out_name / "handoff").is_dir()
    assert (out_dir / out_name / "local").is_dir()


def test_mct09_serial_folders_never_overwritten(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    one = layer.call("prepare_for_sharing", {"path": "sample.txt"})
    snapshot = tree_files(out_dir / one["output_dir"])
    two = layer.call("prepare_for_sharing", {"path": "sample.txt"})
    assert one["output_dir"] == "0001"
    assert two["output_dir"] == "0002"
    assert tree_files(out_dir / "0001") == snapshot
    # a caller-chosen name lands as its own folder
    named = layer.call("prepare_for_sharing",
                       {"path": "sample.txt", "name": "report-run"})
    assert named["output_dir"] == "report-run"
    from sieve_mcp_server.errors import ToolError
    try:
        layer.call("prepare_for_sharing",
                   {"path": "sample.txt", "name": "report-run"})
        raise AssertionError("the duplicate name must fail")
    except ToolError as e:
        assert e.code == "invalid_arguments"
    # the bad names never pass
    for bad in ("../escape", "with/slash", ".hidden", "-dash"):
        try:
            layer.call("prepare_for_sharing",
                       {"path": "sample.txt", "name": bad})
            raise AssertionError("the bad name must fail: %r" % bad)
        except ToolError as e:
            assert e.code == "invalid_arguments"
