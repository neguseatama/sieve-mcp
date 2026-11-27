"""The ``--self-check`` auxiliary command: the whole flow in one
process - the protocol handshake, the tool list, the six tools over a
bundled sample, and the standard error forms - with the exit contract
0 (all matched) / 1 (a difference) / 2 (the check could not run)."""

import json
import os
import stat
import struct
import sys
import tempfile
import zlib
from pathlib import Path

from . import __version__
from .errors import StartupError
from .paths import Spaces
from .protocol import (SUPPORTED_PROTOCOL_VERSIONS, TOOL_DEFS, Channel,
                       handle_line)

_HIDDEN_SAMPLE = "visible line\nhidden:\u200bzero\u2060join\u202ebil\n"
_VISIBLE_SAMPLE = "visible line\nhidden:zerojoinbil\n"


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + ctype + payload
            + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))


def _png_with_meta() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"tEXt", b"Author\x00Sample Author")
            + _png_chunk(b"tEXt", b"Comment\x00sample comment")
            + _png_chunk(b"IDAT", idat)
            + _png_chunk(b"IEND", b""))


class _Difference(Exception):
    def __init__(self, problems):
        self.problems = problems
        super().__init__("self-check differences")


class _Runner:
    """The in-process protocol runner: requests go through the real
    ``handle_line``, the answers land in one scratch file."""

    def __init__(self, spaces):
        self.spaces = spaces
        from .tools import ToolLayer
        self.layer = ToolLayer(spaces)
        self._fh = tempfile.TemporaryFile("w+b")
        self.channel = Channel(self._fh.fileno())
        self.checks = 0
        self.problems = []

    def request(self, obj) -> dict:
        line = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
        handle_line(line, self.channel, self.layer)
        return self._read_one()

    def raw_request(self, raw: bytes) -> dict:
        handle_line(raw, self.channel, self.layer)
        return self._read_one()

    def _read_one(self) -> dict:
        self._fh.seek(0)
        lines = self._fh.read().splitlines()
        self._fh.seek(0)
        self._fh.truncate()
        if len(lines) != 1:
            self.problems.append("expected exactly one answer line, "
                                 "got %d" % len(lines))
            return {}
        return json.loads(lines[0].decode("utf-8"))

    def expect(self, condition, message) -> None:
        self.checks += 1
        if not condition:
            self.problems.append(message)

    def close(self) -> None:
        self._fh.close()


def _build_fixture(base: Path) -> Path:
    root = base / "root"
    (root / ".obsidian").mkdir(parents=True)
    (root / ".trash").mkdir()
    (root / ".obsidian" / "workspace.json").write_text("{}\n",
                                                       encoding="utf-8")
    (root / ".trash" / "junk.txt").write_text("junk\n", encoding="utf-8")
    (root / "sample.txt").write_text(_HIDDEN_SAMPLE, encoding="utf-8")
    (root / "meta.png").write_bytes(_png_with_meta())
    return root


def _run() -> tuple:
    runner = None
    try:
        with tempfile.TemporaryDirectory(prefix="sieve-mcp-selfcheck-") as td:
            base = Path(td)
            root = _build_fixture(base)
            out = base / "out"
            out.mkdir()
            spaces = Spaces([str(root)], str(out))
            runner = _Runner(spaces)

            init = runner.request({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18",
                           "capabilities": {},
                           "clientInfo": {"name": "self-check",
                                          "version": "0"}},
            })
            result = init.get("result") or {}
            runner.expect(
                result.get("protocolVersion") in SUPPORTED_PROTOCOL_VERSIONS,
                "initialize: the negotiated version is not supported")
            runner.expect(
                (result.get("serverInfo") or {}).get("version") == __version__,
                "initialize: the server version does not match the package")
            runner.expect("instructions" in result,
                          "initialize: the instructions are missing")
            runner.request({"jsonrpc": "2.0", "id": 90,
                            "method": "notifications/initialized"})

            listed = runner.request(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            names = [t.get("name")
                     for t in ((listed.get("result") or {}).get("tools")
                               or [])]
            runner.expect(
                names == [t["name"] for t in TOOL_DEFS],
                "tools/list: the tool list does not match the six tools")

            prepared = runner.request({
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "prepare_for_sharing",
                           "arguments": {"path": "."}},
            })
            payload = (prepared.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(payload.get("ok") is True,
                          "prepare_for_sharing: the run failed")
            runner.expect(
                str(payload.get("record_digest") or "").startswith("sha256:"),
                "prepare_for_sharing: the record digest is missing")
            hidden = payload.get("hidden_kinds") or {}
            runner.expect(hidden.get("zero_width_space", 0) >= 1,
                          "prepare_for_sharing: the hidden kind count is "
                          "missing")
            handoff_files = payload.get("handoff_files") or []
            runner.expect(bool(handoff_files),
                          "prepare_for_sharing: no handoff files listed")
            text_rel = None
            for entry in handoff_files:
                if entry["path"].endswith(".txt"):
                    text_rel = entry["path"]
            runner.expect(text_rel is not None,
                          "prepare_for_sharing: the visible text file is "
                          "missing")

            out_rel = text_rel
            read = runner.request({
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "read_handoff",
                           "arguments": {"path": out_rel}},
            })
            read_payload = (read.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(read_payload.get("ok") is True,
                          "read_handoff: the read failed")
            runner.expect(read_payload.get("content") == _VISIBLE_SAMPLE,
                          "read_handoff: the visible text does not match "
                          "the sample")

            first_dir = payload.get("output_dir")

            observed = runner.request({
                "jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "observe_hidden_text",
                           "arguments": {"path": "."}},
            })
            obs = (observed.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(obs.get("check_version") == 1,
                          "observe_hidden_text: the check shape is wrong")
            runner.expect(obs.get("excluded_dirs") == 2,
                          "observe_hidden_text: the two vault folders are "
                          "not the default exclusion")

            record_path = first_dir + "/handoff/gate-receipt.json"
            verified = runner.request({
                "jsonrpc": "2.0", "id": 6, "method": "tools/call",
                "params": {"name": "verify_record",
                           "arguments": {"record": record_path,
                                         "against": first_dir}},
            })
            verdict = (verified.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(verdict.get("overall") == "match",
                          "verify_record: the untouched run does not match")

            cleaned = runner.request({
                "jsonrpc": "2.0", "id": 7, "method": "tools/call",
                "params": {"name": "remove_metadata",
                           "arguments": {"path": "meta.png"}},
            })
            clean_payload = (cleaned.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(clean_payload.get("ok") is True,
                          "remove_metadata: the run failed")
            items = clean_payload.get("items") or []
            runner.expect(
                bool(items) and items[0].get("status") == "cleaned",
                "remove_metadata: the png sample is not cleaned")
            if items:
                runner.expect(
                    any((items[0].get("categories_before") or {}).values()),
                    "remove_metadata: the before counts are all zero")
                runner.expect(
                    not any((items[0].get("categories_after") or {}).values()),
                    "remove_metadata: the re-observation still finds "
                    "metadata")

            listed_files = runner.request({
                "jsonrpc": "2.0", "id": 8, "method": "tools/call",
                "params": {"name": "create_file_list",
                           "arguments": {"path": "."}},
            })
            list_payload = (listed_files.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(list_payload.get("file_count") == 2,
                          "create_file_list: the file count does not match "
                          "the sample (the vault folders are excluded)")
            runner.expect(
                len(str(list_payload.get("overall_sha256") or "")) == 64,
                "create_file_list: the whole-tree checksum is missing")

            pinged = runner.request(
                {"jsonrpc": "2.0", "id": 9, "method": "ping"})
            runner.expect(pinged.get("result") == {},
                          "ping: the answer is not an empty result")

            unknown = runner.request(
                {"jsonrpc": "2.0", "id": 10, "method": "no/such/method"})
            runner.expect(
                (unknown.get("error") or {}).get("code") == -32601,
                "the unknown method does not answer with -32601")

            broken = runner.raw_request(b"{not json}\n")
            runner.expect(
                (broken.get("error") or {}).get("code") == -32700,
                "the broken json does not answer with -32700")

            refused = runner.request({
                "jsonrpc": "2.0", "id": 11, "method": "tools/call",
                "params": {"name": "prepare_for_sharing",
                           "arguments": {"path": "../outside.txt"}},
            })
            refusal = (refused.get("result") or {}).get(
                "structuredContent") or {}
            runner.expect(refusal.get("code") == "path_not_allowed",
                          "the .. form is not refused with the closed word")

            # the original tree is unchanged
            runner.expect(
                (root / "sample.txt").read_text(encoding="utf-8")
                == _HIDDEN_SAMPLE,
                "the original file changed")
            runner.expect(
                stat.S_ISREG(os.lstat(root / "sample.txt").st_mode),
                "the original file is not a regular file anymore")

            if runner.problems:
                raise _Difference(runner.problems)
            return runner.checks, first_dir
    finally:
        if runner is not None:
            runner.close()


def run_self_check() -> int:
    try:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        checks, _first_dir = _run()
        print(json.dumps({"self-check": "ok", "checks": checks},
                         ensure_ascii=False))
        return 0
    except _Difference as e:
        print(json.dumps({"self-check": "differences",
                          "problems": e.problems}, ensure_ascii=False))
        return 1
    except StartupError:
        print(json.dumps({"self-check": "could-not-run"}))
        return 2
    except Exception as e:  # noqa: BLE001 - the exit contract carries it
        print(json.dumps({"self-check": "could-not-run",
                          "kind": type(e).__name__}))
        return 2
