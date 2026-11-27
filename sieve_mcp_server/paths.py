"""The startup spaces (the roots and the output folder) and the tool
argument path resolution.

The server knows two areas only: the roots (the data the tools may
read) and the output folder (the only place anything is written).  The
two areas must not contain each other - the check runs at startup and
exits with code 2.  Tool path arguments resolve inside one area, never
through ``..`` and never through a symbolic link (the link check walks
every component below the area root).  Special files (fifo, socket,
device) never pass.
"""

import os
import stat as stat_module
from pathlib import Path

from .errors import StartupError, ToolError


def _is_within(child: Path, parent: Path) -> bool:
    """True when child equals parent or sits inside parent."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


class Spaces:
    """The validated startup areas and the limits."""

    def __init__(self, root_values, out_value, max_read_chars=8000,
                 max_file_bytes=5 * 1024 * 1024, max_files=512):
        if not root_values:
            raise StartupError("at least one root folder is required")
        if not out_value:
            raise StartupError("the output folder is required")
        roots = []
        for raw in root_values:
            p = Path(raw)
            if not p.is_dir():
                raise StartupError("every root must be an existing folder")
            roots.append(p.resolve())
        out = Path(out_value)
        if not out.is_dir():
            raise StartupError("the output folder must exist")
        out = out.resolve()
        for r in roots:
            if r == out or _is_within(r, out) or _is_within(out, r):
                raise StartupError(
                    "the output folder and the roots must not contain "
                    "each other")
        seen = []
        for r in roots:
            if r in seen:
                raise StartupError("the roots must be distinct folders")
            seen.append(r)
        self.roots = seen
        self.out = out
        # the read limit: the default is 8000 characters, the cap 20000
        self.max_read_chars = max(1, min(int(max_read_chars), 20000))
        self.max_file_bytes = max(1, int(max_file_bytes))
        self.max_files = max(1, int(max_files))

    def next_output_dir(self, name=None) -> Path:
        """A fresh folder under the output folder - the numbered serial
        form by default (existing serials are never overwritten), or a
        validated caller-chosen name."""
        existing = [p for p in self.out.iterdir()]
        serials = []
        for p in existing:
            if p.is_dir() and p.name.isdigit():
                serials.append(int(p.name))
        serial = (max(serials) + 1) if serials else 1
        if name is None:
            dirname = "%04d" % serial
        else:
            _check_output_name(name)
            dirname = name
        cand = self.out / dirname
        if cand.exists():
            raise ToolError("invalid_arguments")
        cand.mkdir()
        return cand


def _check_output_name(name: str) -> None:
    """The caller-chosen output folder name: 1-64 characters of
    letters, digits, dot, dash and underscore, not starting with a dot
    or a dash."""
    import re
    if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
        raise ToolError("invalid_arguments")


def _walk_no_symlink(base: Path, rel) -> None:
    """Every component below ``base`` must exist and must not be a
    symbolic link; the final component must exist."""
    p = base
    parts = list(rel.parts)
    for index, part in enumerate(parts):
        p = p / part
        if p.is_symlink():
            raise ToolError("path_not_allowed")
        if index < len(parts) - 1:
            if not p.is_dir():
                if not p.exists():
                    raise ToolError("not_found")
                raise ToolError("not_a_regular_file")
        elif not p.exists():
            raise ToolError("not_found")


def _lstat_kind(p: Path) -> str:
    st = os.lstat(p)
    mode = st.st_mode
    if stat_module.S_ISREG(mode):
        return "file"
    if stat_module.S_ISDIR(mode):
        return "dir"
    return "special"


def _resolve_relative(raw: str, bases) -> tuple:
    """Resolve one relative path against the candidate bases in order.
    Returns (real_path, base, rel).  A ``..`` component is rejected
    before any lookup; a symlink in any component is rejected."""
    from pathlib import PurePosixPath, PureWindowsPath
    if ".." in PurePosixPath(raw).parts or ".." in PureWindowsPath(raw).parts:
        raise ToolError("path_not_allowed")
    rel = PurePosixPath(raw)
    last_error = None
    for base in bases:
        cand = base / rel
        try:
            _walk_no_symlink(base, rel)
        except ToolError as e:
            if e.code == "not_found":
                last_error = e
                continue
            raise
        real = cand.resolve()
        if not _is_within(real, base):
            raise ToolError("path_not_allowed")
        return real, base, rel
    raise last_error or ToolError("not_found")


def _resolve_absolute(raw: str, bases) -> tuple:
    """One absolute path: accepted only when it sits inside one of the
    bases (after resolution) - anything else is outside."""
    p = Path(raw)
    real = p.resolve()
    for base in bases:
        if _is_within(real, base):
            rel = real.relative_to(base)
            return real, base, rel
    raise ToolError("path_not_allowed")


def _finish(real: Path, base: Path, rel, need: str) -> tuple:
    """The kind check: 'file' (regular file only), 'either' (file or
    folder), 'dir' (folder only).  Special files never pass."""
    kind = _lstat_kind(real)
    if need == "file":
        if kind != "file":
            raise ToolError("not_a_regular_file")
    elif need == "dir":
        if kind != "dir":
            raise ToolError("not_a_regular_file")
    else:
        if kind == "special":
            raise ToolError("not_a_regular_file")
    rel_posix = rel.as_posix() if hasattr(rel, "as_posix") else str(rel)
    return real, rel_posix


def resolve_data(raw, spaces, need="either") -> tuple:
    """A tool path that reads data: relative paths try the roots in
    order, absolute paths are accepted only inside a root.  Returns
    (real_path, root_relative_posix)."""
    if not isinstance(raw, str) or not raw:
        raise ToolError("invalid_arguments")
    real, base, rel = (
        _resolve_relative(raw, spaces.roots)
        if not Path(raw).is_absolute()
        else _resolve_absolute(raw, spaces.roots))
    return _finish(real, base, rel, need)


def resolve_out(raw, spaces, need="file") -> tuple:
    """A tool path that reads the server's own output: relative paths
    ride the output folder, absolute paths are accepted only inside
    it.  Returns (real_path, out_relative_posix)."""
    if not isinstance(raw, str) or not raw:
        raise ToolError("invalid_arguments")
    real, base, rel = (
        _resolve_relative(raw, [spaces.out])
        if not Path(raw).is_absolute()
        else _resolve_absolute(raw, [spaces.out]))
    return _finish(real, base, rel, need)


def resolve_any(raw, spaces, need="dir") -> tuple:
    """A tool path that may name either area (the verify target): the
    output folder is tried first, then the roots in order - the two
    areas are disjoint, so no name can match both."""
    if not isinstance(raw, str) or not raw:
        raise ToolError("invalid_arguments")
    if Path(raw).is_absolute():
        real, base, rel = _resolve_absolute(raw, [spaces.out] + spaces.roots)
        return _finish(real, base, rel, need)
    try:
        real, base, rel = _resolve_relative(raw, [spaces.out])
    except ToolError as e:
        if e.code != "not_found":
            raise
        real, base, rel = _resolve_relative(raw, spaces.roots)
    return _finish(real, base, rel, need)


def under_handoff(rel_posix: str) -> bool:
    """True when the output-relative path sits inside a handoff folder."""
    return "handoff" in PurePosixPath_compat(rel_posix).parts


def PurePosixPath_compat(text: str):
    from pathlib import PurePosixPath
    return PurePosixPath(text)
