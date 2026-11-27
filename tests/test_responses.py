"""MC-T07: every reply carries relative POSIX paths only, the error
words ride the closed eight, and no exception text ever leaves."""

import json

import pytest

from helpers import layer_for, tree_files

ERROR_WORDS = {
    "path_not_allowed", "not_found", "not_a_regular_file", "too_large",
    "unsupported_type", "invalid_arguments", "run_failed",
    "read_not_allowed",
}

ABS_FORMS = ("/Users/", "/home/", "C:\\Users\\")


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_strings(v)


def _paths_of(payload):
    for key in ("path", "output_dir", "record_path", "output"):
        if key in payload:
            yield payload[key]


def test_mct07_paths_are_relative_posix_only(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    observed = layer.call("observe_hidden_text", {"path": "."})
    listed = layer.call("create_file_list", {"path": "."})
    cleaned = layer.call("remove_metadata", {"path": "meta.png"})
    out_name = prepared["output_dir"]
    verified = layer.call(
        "verify_record",
        {"record": out_name + "/handoff/gate-receipt.json",
         "against": out_name})
    visible_rel = next(f["path"] for f in prepared["handoff_files"]
                       if f["path"].endswith("sample.txt.visible.txt"))
    read = layer.call("read_handoff", {"path": visible_rel})

    for payload in (prepared, observed, listed, cleaned, verified, read):
        raw = json.dumps(payload, ensure_ascii=False)
        for form in ABS_FORMS:
            assert form not in raw
        assert str(root_dir) not in raw
        assert str(out_dir) not in raw
        assert str(root_dir.as_posix()) not in raw
        assert str(out_dir.as_posix()) not in raw
    # the path fields carry no backslash and no absolute form
    for payload in (prepared, listed, cleaned, read):
        for p in _paths_of(payload):
            if isinstance(p, str):
                assert "\\" not in p
                assert not p.startswith("/")
                assert not p[1:2] == ":"
    for item in prepared["items"] + cleaned["items"]:
        p = item.get("path")
        if isinstance(p, str):
            assert "\\" not in p
    for item in observed["items"]:
        p = item.get("path")
        if isinstance(p, str):
            assert "\\" not in p
            assert not p.startswith("/")


def test_mct07_error_words_are_the_closed_eight(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    cases = [
        ("prepare_for_sharing", {"path": "../x"}),
        ("prepare_for_sharing", {"path": "missing.txt"}),
        ("prepare_for_sharing", {}),
        ("prepare_for_sharing", {"path": 5}),
        ("prepare_for_sharing", {"path": ".", "bogus": 1}),
        ("read_handoff", {"path": "nowhere/nowhere.txt"}),
        ("observe_hidden_text", {"path": "../x"}),
        ("verify_record", {"record": "nope.json", "against": "x"}),
        ("remove_metadata", {"path": "missing.png"}),
        ("create_file_list", {"path": "../x"}),
    ]
    from sieve_mcp_server.errors import ToolError
    for name, args in cases:
        with pytest.raises(ToolError) as e:
            layer.call(name, args)
        assert e.value.code in ERROR_WORDS, (name, args)
        assert e.value.message and isinstance(e.value.message, str)


def test_mct07_exception_text_never_leaves(root_dir, out_dir, monkeypatch):
    import sieve_tray
    from sieve_mcp_server.errors import ToolError
    from sieve_mcp_server.protocol import tool_call_payload
    from helpers import layer_for

    def exploding_run_gate(*a, **kw):
        raise RuntimeError("SECRET-EXCEPTION-DETAILS /tmp/secret/path")

    monkeypatch.setattr(sieve_tray, "run_gate", exploding_run_gate)
    layer = layer_for(root_dir, out_dir)
    payload = tool_call_payload(layer, "prepare_for_sharing",
                                {"path": "."})
    assert payload["ok"] is False
    assert payload["code"] == "run_failed"
    raw = json.dumps(payload, ensure_ascii=False)
    assert "SECRET-EXCEPTION-DETAILS" not in raw
    assert "RuntimeError" not in raw
    assert "/tmp/secret/path" not in raw


def test_mct07_leak_guard_fails_closed(root_dir, out_dir, monkeypatch):
    import sieve_tray
    from sieve_mcp_server.errors import ToolError
    from helpers import layer_for

    def leaking_run_gate(input_dir, output_dir, **kwargs):
        return {
            "items": [{"path": str(root_dir), "status": "flagged",
                       "treatment": "produced", "not_produced_reason": None,
                       "removed_invisible": {},
                       "output": {"path": "handoff/x.txt", "bytes": 1,
                                  "sha256": "0" * 64}}],
            "summary": {"items": 1}, "settings": {},
            "digest": "sha256:" + "2" * 64,
        }

    monkeypatch.setattr(sieve_tray, "run_gate", leaking_run_gate)
    layer = layer_for(root_dir, out_dir)
    with pytest.raises(ToolError) as e:
        layer.call("prepare_for_sharing", {"path": "."})
    assert e.value.code == "run_failed"
    # the original tree is untouched by the failed run
    assert "sample.txt" in tree_files(root_dir)
