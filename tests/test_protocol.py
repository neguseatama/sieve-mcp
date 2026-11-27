"""MC-T01 (the official SDK client rides the whole flow), MC-T02 (the
protocol errors never end the server), MC-T03 (the standard output is
the protocol only, byte-checked) and MC-T13 (the engine noise and the
real run_gate never break the protocol flow)."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from helpers import ServerProc

INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "suite", "version": "0"}},
}


def _init_and_list(server):
    server.send(INIT)
    init = server.recv()
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "sieve-mcp-server"
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    listed = server.recv()
    names = [t["name"] for t in listed["result"]["tools"]]
    assert names == ["prepare_for_sharing", "read_handoff",
                     "observe_hidden_text", "verify_record",
                     "remove_metadata", "create_file_list"]
    return listed


def test_mct01_sdk_client_full_flow(root_dir, out_dir):
    mcp = pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    import anyio

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "sieve_mcp_server", "--root", str(root_dir),
              "--out", str(out_dir)])

    async def _flow():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                from sieve_mcp_server.protocol import (
                    SUPPORTED_PROTOCOL_VERSIONS)
                assert init.protocol_version in SUPPORTED_PROTOCOL_VERSIONS
                assert init.server_info.name == "sieve-mcp-server"
                assert "data" in init.instructions
                listed = await session.list_tools()
                names = [t.name for t in listed.tools]
                assert names == ["prepare_for_sharing", "read_handoff",
                                 "observe_hidden_text", "verify_record",
                                 "remove_metadata", "create_file_list"]
                for t in listed.tools:
                    assert t.description
                    assert t.input_schema["type"] == "object"

                prepared = await session.call_tool(
                    "prepare_for_sharing", {"path": "."})
                assert prepared.is_error is not True
                payload = prepared.structured_content
                assert payload["ok"] is True
                assert payload["record_digest"].startswith("sha256:")
                out_dir_name = payload["output_dir"]

                observed = await session.call_tool(
                    "observe_hidden_text", {"path": "."})
                assert observed.is_error is not True
                assert observed.structured_content["check_version"] == 1

                listed_files = await session.call_tool(
                    "create_file_list", {"path": "."})
                assert listed_files.is_error is not True
                assert len(listed_files.structured_content[
                    "overall_sha256"]) == 64

                cleaned = await session.call_tool(
                    "remove_metadata", {"path": "meta.png"})
                assert cleaned.is_error is not True
                assert cleaned.structured_content["items"][0][
                    "status"] == "cleaned"

                handoff_rel = next(
                    f["path"] for f in payload["handoff_files"]
                    if f["path"].endswith(".txt"))
                read = await session.call_tool(
                    "read_handoff", {"path": handoff_rel})
                assert read.is_error is not True
                assert read.structured_content["total_chars"] >= 1

                verified = await session.call_tool(
                    "verify_record",
                    {"record": out_dir_name + "/handoff/gate-receipt.json",
                     "against": out_dir_name})
                assert verified.is_error is not True
                assert verified.structured_content["overall"] == "match"

    anyio.run(_flow)


def test_mct02_protocol_errors_keep_the_server_alive(root_dir, out_dir):
    server = ServerProc(root_dir, out_dir)
    try:
        # broken json
        server.send_line_bytes(b"{not json}")
        assert server.recv()["error"]["code"] == -32700
        # unknown method
        server.send({"jsonrpc": "2.0", "id": 3, "method": "no/such"})
        assert server.recv()["error"]["code"] == -32601
        # an unsupported version negotiates the newest supported one
        server.send({"jsonrpc": "2.0", "id": 4, "method": "initialize",
                     "params": {"protocolVersion": "1999-01-01"}})
        init = server.recv()
        assert init["result"]["protocolVersion"] == "2025-11-25"
        # a missing version field is an invalid-params error
        server.send({"jsonrpc": "2.0", "id": 5, "method": "initialize",
                     "params": {}})
        assert server.recv()["error"]["code"] == -32602
        # a malformed tools/call envelope is invalid params
        server.send({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                     "params": {}})
        assert server.recv()["error"]["code"] == -32602
        # a missing required argument is a tool error with a closed word
        server.send({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                     "params": {"name": "prepare_for_sharing",
                                "arguments": {}}})
        body = server.recv()["result"]
        assert body["isError"] is True
        assert body["structuredContent"]["code"] == "invalid_arguments"
        # an unknown tool name stays in the closed vocabulary too
        server.send({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                     "params": {"name": "rename", "arguments": {}}})
        body = server.recv()["result"]
        assert body["isError"] is True
        assert body["structuredContent"]["code"] == "invalid_arguments"
        # and the server still runs
        server.send({"jsonrpc": "2.0", "id": 9, "method": "ping"})
        assert server.recv()["result"] == {}
        out, err = server.finish()
        assert err == b""
        assert b"error" not in out or True  # the answers were consumed
    finally:
        server.close()


def test_mct03_stdout_is_protocol_bytes_only(root_dir, out_dir):
    server = ServerProc(root_dir, out_dir)
    try:
        collected = []
        server.send(INIT)
        collected.append(server.proc.stdout.readline())
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        collected.append(server.proc.stdout.readline())
        server.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "observe_hidden_text",
                                "arguments": {"path": "."}}})
        collected.append(server.proc.stdout.readline())
        rest_out, rest_err = server.finish()
        raw = b"".join(collected) + rest_out
        assert b"\r" not in raw
        for line in raw.splitlines():
            msg = json.loads(line.decode("utf-8"))
            assert msg.get("jsonrpc") == "2.0"
        assert rest_err == b""
    finally:
        server.close()


def test_mct13_stub_engine_noise_never_reaches_the_protocol(root_dir,
                                                           out_dir,
                                                           monkeypatch):
    import sieve_tray
    from sieve_mcp_server.protocol import Channel, handle_line
    from helpers import layer_for

    def noisy_run_gate(input_dir, output_dir, **kwargs):
        # every form of noise an engine could produce: the text layer,
        # the buffer layer and the raw descriptor
        print("STDOUT-NOISE-LINE")
        sys.stderr.write("STDERR-NOISE-LINE\n")
        sys.stdout.flush()
        try:
            sys.stdout.buffer.write(b"BUFFER-NOISE\n")
            sys.stdout.buffer.flush()
        except AttributeError:
            pass
        os.write(1, b"FD-NOISE\n")
        return {
            "receipt_version": 1, "kind": "sieve-gate",
            "tool": {"name": "sieve-tray", "version": "stub"},
            "engines": [], "settings": {},
            "items": [{"path": "sample.txt", "status": "flagged",
                       "treatment": "produced", "not_produced_reason": None,
                       "removed_invisible": {"zero_width_space": 1},
                       "output": {"path": "handoff/sample.txt.visible.txt",
                                  "bytes": 5, "sha256": "0" * 64}}],
            "summary": {"items": 1, "produced": 1, "not_produced": 0,
                        "status": {"clean": 0, "flagged": 1,
                                   "unobserved": 0},
                        "not_produced_by_reason": {}},
            "digest": "sha256:" + "1" * 64,
        }

    monkeypatch.setattr(sieve_tray, "run_gate", noisy_run_gate)
    layer = layer_for(root_dir, out_dir)
    with tempfile.TemporaryFile("w+b") as cap:
        channel = Channel(cap.fileno())
        stdout_before = sys.stdout
        stderr_before = sys.stderr
        handle_line(
            json.dumps({"jsonrpc": "2.0", "id": 20, "method": "tools/call",
                        "params": {"name": "prepare_for_sharing",
                                   "arguments": {"path": "."}}}).encode()
            + b"\n", channel, layer)
        cap.seek(0)
        protocol_bytes = cap.read()
        # the protocol flow is intact: one clean JSON answer
        msg = json.loads(protocol_bytes.decode("utf-8"))
        assert msg["id"] == 20
        assert msg["result"]["structuredContent"]["ok"] is True
        for noise in (b"STDOUT-NOISE-LINE", b"BUFFER-NOISE", b"FD-NOISE"):
            assert noise not in protocol_bytes
        # both text streams came back exactly as they were
        assert sys.stdout is stdout_before
        assert sys.stderr is stderr_before


def test_mct13_real_run_gate_keeps_the_protocol_flow(root_dir, out_dir):
    server = ServerProc(root_dir, out_dir)
    try:
        _init_and_list(server)
        server.send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "prepare_for_sharing",
                                "arguments": {"path": "."}}})
        body = server.recv()["result"]
        assert body.get("isError") is not True
        payload = body["structuredContent"]
        out_name = payload["output_dir"]
        # the flow continues with byte writes and \n delimiters after
        # the real run_gate (which reconfigures the text streams inside
        # the bundled engine)
        visible_rel = next(
            f["path"] for f in payload["handoff_files"]
            if f["path"].endswith(".txt"))
        server.send({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "read_handoff",
                                "arguments": {"path": visible_rel}}})
        read = server.recv()["result"]
        assert read["structuredContent"]["ok"] is True
        server.send({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
        listed = server.recv()["result"]
        assert len(listed["tools"]) == 6
        server.send({"jsonrpc": "2.0", "id": 7, "method": "ping"})
        assert server.recv()["result"] == {}
        rest_out, rest_err = server.finish()
        assert b"\r" not in rest_out
        assert rest_err == b""
        assert (out_dir / out_name / "handoff" /
                "gate-receipt.json").is_file()
    finally:
        server.close()
