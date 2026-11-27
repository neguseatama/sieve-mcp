"""The six tool handlers.

Every handler takes the arguments object, returns the response payload
(a plain dict - the protocol layer sends it as ``structuredContent`` and
as the same JSON text in ``content``).  The vocabulary of every reply is
closed: status words and reason words from the Tray engines, the eight
error words, counts, checksums, digests and relative POSIX paths.  The
hidden text itself, the metadata values, the absolute paths and the
free strings of the input files never enter a reply - a final guard
scans every payload for the roots' and the output folder's absolute
paths and fails closed.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import sieve_tray

from .errors import ToolError
from .isolation import isolated_stdio
from .paths import (Spaces, resolve_any, resolve_data, resolve_out,
                    under_handoff)

# the readable texts of the handoff side: the plain document forms only.
# The JSON receipts carry the run's own recorded paths and stay outside
# the readable set (the tools hand their content to the AI themselves)
READ_SUFFIXES = (".txt", ".md", ".html", ".csv")

TOOL_NAMES = (
    "prepare_for_sharing",
    "read_handoff",
    "observe_hidden_text",
    "verify_record",
    "remove_metadata",
    "create_file_list",
)


def _req_str(args, key) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ToolError("invalid_arguments")
    return value


def _opt_str(args, key):
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError("invalid_arguments")
    return value


def _opt_int(args, key):
    value = args.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ToolError("invalid_arguments")
    return value


def _opt_bool(args, key):
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ToolError("invalid_arguments")
    return value


def _reject_unknown(args, allowed) -> None:
    for key in args:
        if key not in allowed:
            raise ToolError("invalid_arguments")


def _payload_leaks(value, spaces: Spaces) -> bool:
    """True when any string in the payload carries one of the areas'
    absolute paths (raw or POSIX form).  Fail closed."""
    forms = []
    for p in list(spaces.roots) + [spaces.out]:
        forms.append(str(p))
        forms.append(p.as_posix())
    if isinstance(value, str):
        return any(form and form in value for form in forms)
    if isinstance(value, dict):
        return any(_payload_leaks(v, spaces) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_payload_leaks(v, spaces) for v in value)
    return False


def _run_engine(fn):
    """One engine run with both standard-output layers swapped away.
    Every failure becomes the closed run_failed word - the engine's own
    exception text never leaves the server."""
    try:
        with isolated_stdio():
            return fn()
    except ToolError:
        raise
    except Exception:  # noqa: BLE001 - the closed word carries it
        raise ToolError("run_failed") from None


def _count_folder_files(target: Path, *, exclude_vault: bool) -> int:
    # the Tray walk is the same scan the engines run - the vault
    # folders are pruned by the Gate's ingest flag, never by a local list
    files = sieve_tray._gate_walk(target, exclude_vault_dirs=exclude_vault)
    return len(files)


class ToolLayer:
    """The six handlers over one validated Spaces object."""

    def __init__(self, spaces: Spaces):
        self.spaces = spaces

    def call(self, name, args) -> dict:
        if not isinstance(args, dict):
            raise ToolError("invalid_arguments")
        handlers = {
            "prepare_for_sharing": self.prepare_for_sharing,
            "read_handoff": self.read_handoff,
            "observe_hidden_text": self.observe_hidden_text,
            "verify_record": self.verify_record,
            "remove_metadata": self.remove_metadata,
            "create_file_list": self.create_file_list,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError("invalid_arguments")
        payload = handler(args)
        if _payload_leaks(payload, self.spaces):
            raise ToolError("run_failed")
        return payload

    # --- prepare_for_sharing -------------------------------------------

    def prepare_for_sharing(self, args) -> dict:
        _reject_unknown(args, {"path", "name", "same_value"})
        path_arg = _req_str(args, "path")
        name = _opt_str(args, "name")
        same_value = _opt_bool(args, "same_value") or False
        target, rel = resolve_data(path_arg, self.spaces)
        if target.is_dir():
            count = _count_folder_files(target, exclude_vault=True)
        else:
            count = 1
        if count > self.spaces.max_files:
            raise ToolError("too_large")
        outdir = self.spaces.next_output_dir(name)
        redact_mode = "same-value" if same_value else "label"
        if target.is_dir():
            receipt = _run_engine(
                lambda: sieve_tray.run_gate(
                    target, outdir, redact_mode=redact_mode))
        else:
            if target.stat().st_size > self.spaces.max_file_bytes:
                raise ToolError("too_large")
            # the Gate's ingest is folder-only: a single file rides a
            # scratch staging folder outside the output tree, removed
            # when the run ends
            receipt = _run_engine(lambda: self._gate_one_file(
                target, outdir, redact_mode))
        return self._gate_payload(receipt, outdir)

    @staticmethod
    def _gate_one_file(target: Path, outdir: Path, redact_mode: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="sieve-mcp-stage-") as td:
            stage = Path(td) / "staging"
            stage.mkdir()
            shutil.copyfile(target, stage / target.name)
            return sieve_tray.run_gate(stage, outdir, redact_mode=redact_mode)

    def _gate_payload(self, receipt: dict, outdir: Path) -> dict:
        out_rel = outdir.name
        items = []
        hidden = {}
        for it in receipt.get("items") or []:
            entry = {"path": it.get("path"), "status": it.get("status")}
            reason = it.get("not_produced_reason") or it.get("unobserved_reason")
            if reason:
                entry["reason"] = reason
            items.append(entry)
            for word, count in (it.get("removed_invisible") or {}).items():
                hidden[word] = hidden.get(word, 0) + count
        handoff_files = []
        handoff_dir = outdir / "handoff"
        if handoff_dir.is_dir():
            for p in sorted(handoff_dir.iterdir(), key=lambda q: q.name):
                if p.is_file() and not p.is_symlink():
                    handoff_files.append({
                        "path": "%s/handoff/%s" % (out_rel, p.name),
                        "bytes": p.stat().st_size,
                    })
        return {
            "ok": True,
            "tool": "prepare_for_sharing",
            "output_dir": out_rel,
            "items": items,
            "hidden_kinds": {k: hidden[k] for k in sorted(hidden)},
            "handoff_files": handoff_files,
            "record_digest": receipt.get("digest"),
        }

    # --- read_handoff ---------------------------------------------------

    def read_handoff(self, args) -> dict:
        _reject_unknown(args, {"path", "offset", "limit"})
        path_arg = _req_str(args, "path")
        offset = _opt_int(args, "offset")
        limit = _opt_int(args, "limit")
        # resolve as either kind first, so the handoff rule (the only
        # readable area) answers before the file-kind check
        real, rel = resolve_out(path_arg, self.spaces, need="either")
        if not under_handoff(rel):
            raise ToolError("read_not_allowed")
        if _lstat_kind_of(real) != "file":
            raise ToolError("not_a_regular_file")
        if real.suffix.lower() not in READ_SUFFIXES:
            raise ToolError("unsupported_type")
        size = real.stat().st_size
        if size > self.spaces.max_file_bytes:
            raise ToolError("too_large")
        data = real.read_bytes()
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeDecodeError:
            raise ToolError("unsupported_type") from None
        total = len(text)
        if offset is not None and offset > total:
            raise ToolError("invalid_arguments")
        start = offset or 0
        cap = limit if limit else self.spaces.max_read_chars
        cap = min(cap, self.spaces.max_read_chars)
        chunk = text[start:start + cap]
        end = start + len(chunk)
        next_offset = end if end < total else None
        return {
            "ok": True,
            "tool": "read_handoff",
            "path": rel,
            "content": chunk,
            "total_chars": total,
            "next_offset": next_offset,
        }

    # --- observe_hidden_text --------------------------------------------

    def observe_hidden_text(self, args) -> dict:
        _reject_unknown(args, {"path", "only_hidden"})
        path_arg = _req_str(args, "path")
        only_hidden = _opt_bool(args, "only_hidden") or False
        target, rel = resolve_data(path_arg, self.spaces)
        if target.is_dir():
            count = _count_folder_files(target, exclude_vault=True)
        else:
            count = 1
        if count > self.spaces.max_files:
            raise ToolError("too_large")
        result = _run_engine(
            lambda: sieve_tray.check_paths([str(target)],
                                           only_hidden=only_hidden))
        # check_paths echoes the given path back into the items - the
        # reply carries the root-relative POSIX form only
        target_str = str(target)
        for item in result.get("items") or []:
            p = item.get("path")
            if isinstance(p, str):
                item["path"] = self._relativize(p, target_str, rel)
        return result

    @staticmethod
    def _relativize(path_str: str, target_str: str, rel: str) -> str:
        if path_str == target_str:
            return rel
        for sep in ("/", os.sep):
            prefix = target_str + sep
            if path_str.startswith(prefix):
                rest = path_str[len(prefix):].replace("\\", "/")
                if rel in ("", "."):
                    return rest
                return "%s/%s" % (rel, rest)
        return path_str

    # --- verify_record ----------------------------------------------------

    def verify_record(self, args) -> dict:
        _reject_unknown(args, {"record", "against"})
        record_arg = _req_str(args, "record")
        against_arg = _req_str(args, "against")
        record_real, record_rel = resolve_out(record_arg, self.spaces)
        if not under_handoff(record_rel):
            raise ToolError("read_not_allowed")
        if record_real.suffix.lower() != ".json":
            raise ToolError("unsupported_type")
        if record_real.stat().st_size > self.spaces.max_file_bytes:
            raise ToolError("too_large")
        try:
            obj = json.loads(
                record_real.read_bytes().decode("utf-8", "strict"))
        except (UnicodeDecodeError, ValueError):
            return self._verify_payload("not_verifiable", None, [],
                                        "receipt_unreadable")
        kind = obj.get("kind") if isinstance(obj, dict) else None
        against_real, _against_rel = resolve_any(against_arg, self.spaces)
        serial_dir = record_real.parent.parent
        if kind == "sieve-gate":
            if against_real != serial_dir:
                raise ToolError("invalid_arguments")
            v = _run_engine(lambda: sieve_tray.verify_gate(
                record_real, output_dir=record_real.parent))
        elif kind == "sieve-clean":
            if against_real != serial_dir:
                raise ToolError("invalid_arguments")
            v = _run_engine(lambda: sieve_tray.verify_gate(
                record_real, input_dir=record_real.parent))
        elif kind == "sieve-manifest":
            v = _run_engine(lambda: sieve_tray.verify_gate(
                record_real, input_dir=against_real))
        else:
            return self._verify_payload("not_verifiable", None, [],
                                        "receipt_version_unsupported")
        reasons = v.get("items") or []
        return self._verify_payload(
            v.get("overall"), v.get("scope"), reasons,
            v.get("not_verifiable_reason"))

    @staticmethod
    def _verify_payload(overall, scope, reasons, not_verifiable_reason) -> dict:
        payload = {
            "ok": True,
            "tool": "verify_record",
            "overall": overall,
            "scope": scope,
            "reasons": reasons,
        }
        if not_verifiable_reason:
            payload["not_verifiable_reason"] = not_verifiable_reason
        return payload

    # --- remove_metadata ---------------------------------------------------

    def remove_metadata(self, args) -> dict:
        _reject_unknown(args, {"path", "name"})
        path_arg = _req_str(args, "path")
        name = _opt_str(args, "name")
        target, rel = resolve_data(path_arg, self.spaces)
        if target.is_dir():
            # the clean scan is Tray's own (the vault folders stay, as
            # in every other Tray lane)
            count = _count_folder_files(target, exclude_vault=False)
            if count > self.spaces.max_files:
                raise ToolError("too_large")
        else:
            if target.stat().st_size > self.spaces.max_file_bytes:
                raise ToolError("too_large")
        outdir = self.spaces.next_output_dir(name)
        receipt = _run_engine(
            lambda: _import_canon().run_clean(target, outdir))
        out_rel = outdir.name
        items = []
        for it in receipt.get("items") or []:
            entry = {
                "path": self._clean_item_path(it, target, rel),
                "status": it.get("status"),
                "format": it.get("format"),
                "categories_before": it.get("categories_before"),
                "categories_after": it.get("categories_after"),
            }
            if it.get("reason"):
                entry["reason"] = it["reason"]
            if it.get("content_checksum_match") is not None:
                entry["content_checksum_match"] = it["content_checksum_match"]
            if it.get("output_name"):
                entry["output"] = "%s/handoff/%s" % (out_rel,
                                                     it["output_name"])
            items.append(entry)
        return {
            "ok": True,
            "tool": "remove_metadata",
            "output_dir": out_rel,
            "items": items,
            "record_path": "%s/handoff/clean-receipt.json" % out_rel,
            "record_digest": receipt.get("digest"),
        }

    @staticmethod
    def _clean_item_path(it: dict, target: Path, rel: str):
        """The clean receipt carries the folder-relative path (a folder
        run) or the bare file name (a file run) - the reply carries the
        root-relative POSIX form."""
        p = it.get("path")
        if p is None:
            return None
        if target.is_dir():
            if rel in ("", "."):
                return p.replace("\\", "/")
            return rel + "/" + p.replace("\\", "/")
        return rel

    # --- create_file_list ---------------------------------------------------

    def create_file_list(self, args) -> dict:
        _reject_unknown(args, {"path", "name"})
        path_arg = _req_str(args, "path")
        name = _opt_str(args, "name")
        target, rel = resolve_data(path_arg, self.spaces)
        if target.is_dir():
            count = _count_folder_files(target, exclude_vault=True)
        else:
            count = 1
        if count > self.spaces.max_files:
            raise ToolError("too_large")
        outdir = self.spaces.next_output_dir(name)
        if target.is_dir():
            receipt = _run_engine(lambda: self._manifest_tree(target, outdir))
        else:
            if target.stat().st_size > self.spaces.max_file_bytes:
                raise ToolError("too_large")
            receipt = _run_engine(lambda: self._manifest_one_file(
                target, outdir))
        summary = receipt.get("summary") or {}
        out_rel = outdir.name
        return {
            "ok": True,
            "tool": "create_file_list",
            "output_dir": out_rel,
            "file_count": summary.get("items"),
            "overall_sha256": summary.get("overall_sha256"),
            "record_path": "%s/handoff/manifest-receipt.json" % out_rel,
        }

    def _manifest_tree(self, target: Path, outdir: Path) -> dict:
        # the folder list skips the two vault folders with the Tray
        # walk (the Gate's ingest flag) and lists the rest byte-exact:
        # the manifest runs over a staging copy under the run's local/
        # side (kept, so the record stays verifiable); symlinks never
        # get copied
        stage = outdir / "local" / "staging"
        stage.mkdir(parents=True)
        for rel_file in sieve_tray._gate_walk(
                target, exclude_vault_dirs=True):
            src = target / rel_file
            if src.is_symlink():
                continue
            dest = stage / rel_file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        return sieve_tray.run_manifest(stage, outdir)

    @staticmethod
    def _manifest_one_file(target: Path, outdir: Path) -> dict:
        # one file rides the same local staging shape, so the record
        # stays verifiable against the run folder
        stage = outdir / "local" / "staging"
        stage.mkdir(parents=True)
        shutil.copyfile(target, stage / target.name)
        return sieve_tray.run_manifest(stage, outdir)


def _lstat_kind_of(p: Path) -> str:
    import os
    import stat as stat_module
    st = os.lstat(p)
    if stat_module.S_ISREG(st.st_mode):
        return "file"
    if stat_module.S_ISDIR(st.st_mode):
        return "dir"
    return "special"


def _import_canon():
    import sieve_canon
    return sieve_canon
