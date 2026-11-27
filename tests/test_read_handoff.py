"""MC-T06: read_handoff reads the handoff texts only - the local side
is refused, the slices carry the continuation, the non-UTF-8 bytes and
the receipts are not readable."""

import pytest

from helpers import layer_for


def _prepare(layer):
    return layer.call("prepare_for_sharing", {"path": "sample.txt"})


def test_mct06_handoff_text_reads_with_slices(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = _prepare(layer)
    out_name = prepared["output_dir"]
    rel = None
    for f in prepared["handoff_files"]:
        if f["path"].endswith("sample.txt.visible.txt"):
            rel = f["path"]
    assert rel is not None
    full = layer.call("read_handoff", {"path": rel})
    assert full["ok"] is True
    total = full["total_chars"]
    assert full["next_offset"] is None
    # the slice form
    head = layer.call("read_handoff",
                      {"path": rel, "offset": 0, "limit": 5})
    assert head["content"] == full["content"][:5]
    assert head["next_offset"] == 5
    tail = layer.call("read_handoff",
                      {"path": rel, "offset": 5, "limit": 100000})
    assert tail["content"] == full["content"][5:]
    # the cap of the slice rides --max-read-chars
    capped = layer.call("read_handoff", {"path": rel, "limit": 10**9})
    assert len(capped["content"]) <= 20000
    assert total == len(full["content"])
    # an offset beyond the end is an argument error
    from sieve_mcp_server.errors import ToolError
    with pytest.raises(ToolError) as e:
        layer.call("read_handoff", {"path": rel, "offset": total + 5})
    assert e.value.code == "invalid_arguments"


def test_mct06_local_side_is_refused(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = _prepare(layer)
    out_name = prepared["output_dir"]
    from sieve_mcp_server.errors import ToolError
    with pytest.raises(ToolError) as e:
        layer.call("read_handoff", {"path": out_name + "/local"})
    assert e.value.code == "read_not_allowed"
    with pytest.raises(ToolError) as e2:
        layer.call("read_handoff", {"path": out_name + "/handoff"})
    assert e2.value.code == "not_a_regular_file"
    with pytest.raises(ToolError) as e3:
        layer.call("read_handoff", {"path": out_name + "/handoff/nope.txt"})
    assert e3.value.code == "not_found"


def test_mct06_non_utf8_and_receipts_are_unsupported(root_dir, out_dir):
    layer = layer_for(root_dir, out_dir)
    prepared = _prepare(layer)
    out_name = prepared["output_dir"]
    # a latin-1 file inside the handoff folder: not readable
    latin = (out_dir / out_name / "handoff" / "latin.txt")
    latin.write_bytes(b"caf\xe9\n")
    from sieve_mcp_server.errors import ToolError
    with pytest.raises(ToolError) as e:
        layer.call("read_handoff", {"path": latin.relative_to(out_dir)
                                    .as_posix()})
    assert e.value.code == "unsupported_type"
    # the receipt json is not in the readable set
    with pytest.raises(ToolError) as e2:
        layer.call("read_handoff",
                   {"path": out_name + "/handoff/gate-receipt.json"})
    assert e2.value.code == "unsupported_type"
    # a binary suffix inside handoff is not readable either
    blob = (out_dir / out_name / "handoff" / "blob.bin")
    blob.write_bytes(b"\x00\x01\x02")
    with pytest.raises(ToolError) as e3:
        layer.call("read_handoff",
                   {"path": out_name + "/handoff/blob.bin"})
    assert e3.value.code == "unsupported_type"
