"""MC-T18 (with ``--numbered-names`` the replies carry sequential
numbers instead of the original file names, and the mapping table rides
each run's ``local/`` folder only, never ``handoff/``) and MC-T19
(without the flag the replies keep their shape and no mapping table is
written)."""

import json

import pytest

from helpers import ServerProc, layer_for, tree_files

# the fixture's original names: none of them may ride a numbered reply
ORIGINAL_NAMES = (
    "sample.txt", "plain.txt", "hidden-tr3.pdf", "hidden-white.pdf",
    "layered.pdf", "meta.png", "junk.txt", "workspace.json", "config",
)

# the receipts' fixed names: the numbered folder carries them beside the
# numbered copies (fixed names, never original ones)
RECEIPT_NAMES = ("gate-receipt.json", "clean-receipt.json",
                 "manifest-receipt.json")


def numbered_layer(root_dir, out_dir):
    from sieve_mcp_server.paths import Spaces
    from sieve_mcp_server.tools import ToolLayer
    return ToolLayer(Spaces([str(root_dir)], str(out_dir),
                            numbered_names=True))


def _assert_name_free(payload):
    raw = json.dumps(payload, ensure_ascii=False)
    for name in ORIGINAL_NAMES:
        assert name not in raw, name
    return raw


def _mapping_of(out_dir, run):
    mapping = out_dir / run / "local" / "names.json"
    assert mapping.is_file()
    doc = json.loads(mapping.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert isinstance(doc["names"], dict) and doc["names"]
    return doc


def _assert_numbered_handoff(out_dir, run):
    handoff = out_dir / run / "handoff"
    assert not (handoff / "names.json").exists()
    entries = [p.name for p in handoff.iterdir()
               if p.is_file() and p.name not in RECEIPT_NAMES]
    assert entries
    for name in entries:
        assert name[:4].isdigit(), name


def test_mct18_the_folder_prepare_rides_the_numbered_names(root_dir,
                                                           out_dir):
    layer = numbered_layer(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    _assert_name_free(prepared)
    run = prepared["output_dir"]
    items = prepared["items"]
    assert items
    for it in items:
        p = it.get("path")
        assert isinstance(p, str) and p.isdigit() and len(p) == 4, p
    for f in prepared["handoff_files"]:
        name = f["path"].split("/")[-1]
        if name in RECEIPT_NAMES:
            continue
        assert name[:4].isdigit(), f["path"]
    _assert_numbered_handoff(out_dir, run)
    doc = _mapping_of(out_dir, run)
    values = " ".join(doc["names"].values())
    # the mapping is the only place the original names ride
    assert "sample.txt" in values and "meta.png" in values
    numbered_sample = next(key for key, value in doc["names"].items()
                           if value == "sample.txt")
    assert isinstance(numbered_sample, str)
    assert numbered_sample.isdigit() and len(numbered_sample) == 4


def test_mct18_the_single_file_prepare_rides_the_numbered_names(root_dir,
                                                                out_dir):
    layer = numbered_layer(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "meta.png"})
    _assert_name_free(prepared)
    assert prepared["items"][0]["path"] == "0001"
    doc = _mapping_of(out_dir, prepared["output_dir"])
    assert doc["names"] == {"0001": "meta.png"}


def test_mct18_the_numbered_read_handoff_answers_by_number(root_dir,
                                                           out_dir):
    layer = numbered_layer(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    run = prepared["output_dir"]
    doc = _mapping_of(out_dir, run)
    sample_number = next(key for key, value in doc["names"].items()
                         if value == "sample.txt")
    target = "%s/handoff/%s.visible.txt" % (run, sample_number)
    read = layer.call("read_handoff", {"path": target})
    assert read["ok"] is True
    assert read["path"] == target
    _assert_name_free(read)


def test_mct18_the_observation_numbers_its_items_and_writes_nothing(
        root_dir, out_dir):
    layer = numbered_layer(root_dir, out_dir)
    before = tree_files(out_dir)
    observed = layer.call("observe_hidden_text", {"path": "."})
    _assert_name_free(observed)
    items = observed["items"]
    assert items
    for it in items:
        p = it.get("path")
        assert isinstance(p, str) and p.isdigit() and len(p) == 4, p
    # the observation stays write-free: no mapping table anywhere
    assert tree_files(out_dir) == before
    assert not list(out_dir.rglob("names.json"))


def test_mct18_the_metadata_clean_rides_the_numbered_names(root_dir,
                                                           out_dir):
    layer = numbered_layer(root_dir, out_dir)
    cleaned = layer.call("remove_metadata", {"path": "meta.png"})
    _assert_name_free(cleaned)
    items = cleaned["items"]
    assert items[0]["status"] == "cleaned"
    assert items[0]["path"] == "0001"
    assert items[0]["output"].split("/")[-1] == "0001.png"
    doc = _mapping_of(out_dir, cleaned["output_dir"])
    assert doc["names"] == {"0001": "meta.png"}


def test_mct18_the_file_list_and_its_verify_stay_numbered(root_dir,
                                                          out_dir):
    layer = numbered_layer(root_dir, out_dir)
    listed = layer.call("create_file_list", {"path": "."})
    _assert_name_free(listed)
    run = listed["output_dir"]
    staged_names = [p.name for p in
                    (out_dir / run / "local" / "staging").iterdir()]
    assert staged_names
    for name in staged_names:
        assert name[:4].isdigit(), name
    doc = _mapping_of(out_dir, run)
    values = " ".join(doc["names"].values())
    assert "sample.txt" in values and "meta.png" in values
    record = run + "/handoff/manifest-receipt.json"
    against = run + "/local/staging"
    verdict = layer.call("verify_record", {"record": record,
                                           "against": against})
    assert verdict["overall"] == "match"
    _assert_name_free(verdict)
    # one changed staged copy turns the verdict with the numbered form
    victim = sorted((out_dir / run / "local" / "staging").iterdir())[0]
    victim.write_bytes(victim.read_bytes() + b"tail")
    second = layer.call("verify_record", {"record": record,
                                          "against": against})
    assert second["overall"] == "differs"
    _assert_name_free(second)
    for reason in second["reasons"]:
        p = reason.get("path")
        # the tree-level reason rides the fixed dot form, the per-file
        # reasons ride the numbered staging names
        assert p == "." or (isinstance(p, str) and p[:4].isdigit()), p


def test_mct18_the_verify_of_a_numbered_gate_run_stays_numbered(root_dir,
                                                                out_dir):
    layer = numbered_layer(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    run = prepared["output_dir"]
    record = run + "/handoff/gate-receipt.json"
    verdict = layer.call("verify_record", {"record": record,
                                           "against": run})
    assert verdict["overall"] == "match"
    _assert_name_free(verdict)
    handoff = out_dir / run / "handoff"
    victim = next(p for p in sorted(handoff.iterdir())
                  if p.name != "gate-receipt.json")
    victim.write_bytes(victim.read_bytes() + b"tail")
    second = layer.call("verify_record", {"record": record,
                                          "against": run})
    assert second["overall"] == "differs"
    _assert_name_free(second)


def test_mct18_the_errors_stay_name_free_under_the_flag(root_dir,
                                                        out_dir):
    from sieve_mcp_server.errors import ToolError
    layer = numbered_layer(root_dir, out_dir)
    layer.call("prepare_for_sharing", {"path": "."})
    cases = [
        ("prepare_for_sharing", {"path": "../outside.txt"}),
        ("prepare_for_sharing", {"path": "missing.txt"}),
        ("read_handoff", {"path": "0001/local/names.json"}),
        ("read_handoff", {"path": "missing/handoff/x.txt"}),
        ("verify_record", {"record": "0001/handoff/gate-receipt.json",
                           "against": "0002"}),
    ]
    for name, args in cases:
        with pytest.raises(ToolError) as excinfo:
            layer.call(name, args)
        raw = json.dumps({"code": excinfo.value.code,
                          "message": excinfo.value.message},
                         ensure_ascii=False)
        for original in ORIGINAL_NAMES:
            assert original not in raw, (name, original)


def test_mct18_the_flag_rides_the_command_line(root_dir, out_dir):
    proc = ServerProc(root_dir, out_dir,
                      extra_args=("--numbered-names",))
    try:
        proc.send({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "prepare_for_sharing",
                              "arguments": {"path": "."}}})
        answer = proc.recv()
        payload = answer["result"]["structuredContent"]
        _assert_name_free(payload)
        assert all(it["path"].isdigit() for it in payload["items"])
    finally:
        proc.close()


def test_mct19_without_the_flag_the_replies_keep_their_shape(root_dir,
                                                             out_dir):
    from sieve_mcp_server.cli import build_parser
    args = build_parser().parse_args(["--root", "r", "--out", "o"])
    assert args.numbered_names is False
    layer = layer_for(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    paths = [it.get("path") for it in prepared["items"]]
    assert "sample.txt" in paths and "meta.png" in paths
    run = prepared["output_dir"]
    assert not (out_dir / run / "local" / "names.json").exists()


def test_mct19_the_config_printer_rides_the_flag_when_given(capsys):
    from sieve_mcp_server.printconfig import print_config
    rc = print_config(["share-root"], "share-out", numbered_names=True)
    assert rc == 0
    text = capsys.readouterr().out
    entry = json.loads(text.split("\n\n")[0])["mcpServers"]["sieve-mcp"]
    assert entry["args"][-1] == "--numbered-names"
