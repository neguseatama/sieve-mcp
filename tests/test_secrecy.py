"""MC-T05: no marker ever reaches a tool reply - the hidden text of
every sample kind, the metadata values, the adversarial layer name -
across all six tools, on the raw reply bytes; the one exception is the
visible side that read_handoff is FOR."""

import json

import pytest

from helpers import (ALL_SECRET_MARKERS, MARK_PDF_TR3, MARK_PDF_WHITE,
                     MARK_VIS, layer_for)


def _payload_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def test_mct05_no_secret_marker_reaches_any_tool_reply(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)

    prepared = layer.call("prepare_for_sharing", {"path": "."})
    observed = layer.call("observe_hidden_text", {"path": "."})
    observed_file = layer.call("observe_hidden_text",
                               {"path": "sample.txt"})
    listed = layer.call("create_file_list", {"path": "."})
    cleaned = layer.call("remove_metadata", {"path": "meta.png"})
    out_name = prepared["output_dir"]
    verified = layer.call(
        "verify_record",
        {"record": out_name + "/handoff/gate-receipt.json",
         "against": out_name})

    for name, payload in (("prepare_for_sharing", prepared),
                          ("observe_hidden_text", observed),
                          ("observe_hidden_text file", observed_file),
                          ("create_file_list", listed),
                          ("remove_metadata", cleaned),
                          ("verify_record", verified)):
        raw = _payload_bytes(payload)
        for marker in ALL_SECRET_MARKERS:
            assert marker.encode("utf-8") not in raw, (name, marker)

    # the handoff side answers with the visible text only: the visible
    # marker rides, every hidden marker stays out
    visible_rel = None
    for f in prepared["handoff_files"]:
        if f["path"].endswith("sample.txt.visible.txt"):
            visible_rel = f["path"]
    assert visible_rel is not None
    read = layer.call("read_handoff", {"path": visible_rel})
    assert MARK_VIS in read["content"]
    raw = _payload_bytes(read)
    for marker in ALL_SECRET_MARKERS:
        assert marker.encode("utf-8") not in raw, ("read_handoff", marker)

    # the layered pdf's visible text is on the handoff side - the
    # layer NAME never shows up anywhere
    for f in prepared["handoff_files"]:
        if f["path"].endswith("layered.pdf.visible.txt"):
            read2 = layer.call("read_handoff", {"path": f["path"]})
            raw2 = _payload_bytes(read2)
            for marker in ALL_SECRET_MARKERS:
                assert marker.encode("utf-8") not in raw2


def test_mct05_hidden_pdf_lines_stay_out_of_the_visible_text(root_dir,
                                                            out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = layer.call("prepare_for_sharing", {"path": "."})
    text_by_name = {}
    for f in prepared["handoff_files"]:
        if f["path"].endswith(".visible.txt"):
            read = layer.call("read_handoff", {"path": f["path"]})
            text_by_name[f["path"]] = read["content"]
    tr3 = [v for k, v in text_by_name.items()
           if k.endswith("hidden-tr3.pdf.visible.txt")]
    white = [v for k, v in text_by_name.items()
             if k.endswith("hidden-white.pdf.visible.txt")]
    assert tr3 and MARK_PDF_TR3.encode() not in tr3[0].encode()
    assert white and MARK_PDF_WHITE.encode() not in white[0].encode()


def test_mct05_raw_protocol_stream_is_marker_free(root_dir, out_dir):
    from helpers import ServerProc
    server = ServerProc(root_dir, out_dir)
    try:
        server.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18",
                                "capabilities": {}}})
        server.recv()
        server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                     "params": {"name": "prepare_for_sharing",
                                "arguments": {"path": "."}}})
        server.recv()
        server.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "observe_hidden_text",
                                "arguments": {"path": "."}}})
        server.recv()
        rest_out, rest_err = server.finish()
        raw = rest_out + rest_err
        for marker in ALL_SECRET_MARKERS:
            assert marker.encode("utf-8") not in raw
    finally:
        server.close()
