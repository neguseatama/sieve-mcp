"""MC-T04: the path refusals - the startup containment, the ``..``
forms, the absolute outside, the symbolic links (mid-path too), the
special files, and the input that points inside the output area."""

import os
import subprocess
import sys

import pytest

from helpers import ServerProc, layer_for

INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "suite", "version": "0"}},
}


def _startup_code(args) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "sieve_mcp_server", *args],
        input=b"", capture_output=True, timeout=60)
    return proc.returncode


def test_mct04_startup_containment_refusals(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    # the good start runs (it exits at once on the closed stdin)
    assert _startup_code(["--root", str(root), "--out", str(out)]) == 0
    # the output inside a root
    assert _startup_code(["--root", str(root), "--out", str(root / "sub")]) != 0
    # a root inside the output
    assert _startup_code(["--root", str(out / "sub"), "--out", str(out)]) != 0
    # the same folder for both
    assert _startup_code(["--root", str(root), "--out", str(root)]) != 0
    # a missing folder
    assert _startup_code(["--root", str(tmp_path / "nope"),
                          "--out", str(out)]) != 0
    # missing --out or --root
    assert _startup_code(["--root", str(root)]) != 0
    assert _startup_code(["--out", str(out)]) != 0


def _call(server, name, arguments) -> dict:
    server.send({"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                 "params": {"name": name, "arguments": arguments}})
    return server.recv()["result"]["structuredContent"]


def test_mct04_tool_path_refusals(root_dir, out_dir):
    (root_dir / "sub").mkdir()
    (root_dir / "sub" / "deep.txt").write_text("d\n", encoding="utf-8")
    server = ServerProc(root_dir, out_dir)
    try:
        server.send(INIT)
        server.recv()
        # the .. form
        assert _call(server, "observe_hidden_text",
                     {"path": "../x.txt"})["code"] == "path_not_allowed"
        assert _call(server, "observe_hidden_text",
                     {"path": "sub/../../x.txt"})["code"] == \
            "path_not_allowed"
        # an absolute path outside the roots
        outside = out_dir.parent / "outside.txt"
        outside.write_text("out\n", encoding="utf-8")
        assert _call(server, "observe_hidden_text",
                     {"path": str(outside)})["code"] == "path_not_allowed"
        # a missing path
        assert _call(server, "observe_hidden_text",
                     {"path": "missing.txt"})["code"] == "not_found"
        # an input that points inside the output area
        assert _call(server, "observe_hidden_text",
                     {"path": str(out_dir)})["code"] == "path_not_allowed"
        # a folder where a regular file is required
        server.send({"jsonrpc": "2.0", "id": 100, "method": "tools/call",
                     "params": {"name": "read_handoff",
                                "arguments": {"path": "."}}})
        body = server.recv()["result"]["structuredContent"]
        assert body["code"] == "read_not_allowed"
    finally:
        server.close()


def test_mct04_symlink_refusals(root_dir, out_dir, tmp_path_factory):
    if os.name == "nt":
        pytest.skip("the symlink test needs the privilege the runners "
                    "do not guarantee on windows")
    link_dir = tmp_path_factory.mktemp("links")
    secret_root = link_dir / "secret"
    secret_root.mkdir()
    (secret_root / "secret.txt").write_text("s\n", encoding="utf-8")
    # a symlinked file
    os.symlink(secret_root / "secret.txt", root_dir / "lnk.txt")
    # a symlinked middle folder
    os.symlink(secret_root, root_dir / "lnkdir")
    layer = layer_for(root_dir, out_dir)
    from sieve_mcp_server.errors import ToolError
    with pytest.raises(ToolError) as e1:
        layer.call("observe_hidden_text", {"path": "lnk.txt"})
    assert e1.value.code == "path_not_allowed"
    with pytest.raises(ToolError) as e2:
        layer.call("observe_hidden_text", {"path": "lnkdir/secret.txt"})
    assert e2.value.code == "path_not_allowed"


def test_mct04_special_file_refusal(root_dir, out_dir):
    if not hasattr(os, "mkfifo"):
        pytest.skip("the platform cannot create a fifo")
    fifo = root_dir / "pipe.fifo"
    os.mkfifo(fifo)
    layer = layer_for(root_dir, out_dir)
    from sieve_mcp_server.errors import ToolError
    with pytest.raises(ToolError) as e:
        layer.call("observe_hidden_text", {"path": "pipe.fifo"})
    assert e.value.code == "not_a_regular_file"
