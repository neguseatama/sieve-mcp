"""The standard-output isolation around the engine runs.

From startup the protocol owns two things: a reserved duplicate of the
standard output's file descriptor (the only channel that ever carries a
protocol message) and the byte loop on the standard input.  While an
engine runs, both the Python-level ``sys.stdout`` / ``sys.stderr`` and
the OS-level fd 1 / fd 2 are swapped away, so anything the engine
prints - through ``print()``, through ``sys.stdout.buffer``, or through
a raw ``os.write`` - lands in memory or in a scratch file and is never
emitted.  The protocol channel keeps writing to its reserved descriptor
the whole time.  Both layers are restored when the run ends.
"""

import io
import os
import sys
import tempfile
from contextlib import contextmanager


class _BytesSink:
    """The buffer-level sink: accepts bytes, keeps them in memory."""

    def __init__(self):
        self._buf = bytearray()

    def write(self, data) -> int:
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        self._buf += bytes(data)
        return len(data)

    def flush(self) -> None:
        pass

    def writable(self) -> bool:
        return True


class _TextSink(io.TextIOBase):
    """The text-level sink: looks like a text stream (encoding, flush,
    ``reconfigure`` - the engines call it), writes into the byte sink."""

    def __init__(self):
        self._buffer = _BytesSink()
        self._errors = "replace"

    @property
    def buffer(self):
        return self._buffer

    @property
    def encoding(self):
        return "utf-8"

    @property
    def errors(self):
        return self._errors

    @property
    def name(self):
        return "<sieve-mcp-engine-sink>"

    def write(self, s) -> int:
        return self._buffer.write(s)

    def writelines(self, lines) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        pass

    def reconfigure(self, **_kw) -> None:  # noqa: ANN003 - the engine's call
        # the UTF-8 re-set some engines run on the text streams: the
        # sink is already UTF-8, so the call is accepted and dropped
        return None

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


@contextmanager
def isolated_stdio():
    """Swap away both standard-output layers while one engine run
    executes; restore them afterwards, whatever the run did."""
    saved_out, saved_err = sys.stdout, sys.stderr
    out_sink, err_sink = _TextSink(), _TextSink()
    with tempfile.TemporaryFile() as scratch_out, \
            tempfile.TemporaryFile() as scratch_err:
        saved_fd1, saved_fd2 = os.dup(1), os.dup(2)
        try:
            sys.stdout, sys.stderr = out_sink, err_sink
            os.dup2(scratch_out.fileno(), 1)
            os.dup2(scratch_err.fileno(), 2)
            yield out_sink, err_sink
        finally:
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:  # noqa: BLE001 - the restore must run
                pass
            os.dup2(saved_fd1, 1)
            os.dup2(saved_fd2, 2)
            os.close(saved_fd1)
            os.close(saved_fd2)
            sys.stdout, sys.stderr = saved_out, saved_err
