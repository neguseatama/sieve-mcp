"""The command line: the roots and the output folder, the limits, and
the two auxiliary commands (``--self-check`` and ``--print-config``)."""

import argparse
import sys

from . import __version__
from .paths import Spaces
from .protocol import serve
from .errors import StartupError

MAX_READ_CHARS_DEFAULT = 8000
MAX_READ_CHARS_CAP = 20000
MAX_FILE_BYTES_DEFAULT = 5 * 1024 * 1024
MAX_FILES_DEFAULT = 512


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sieve-mcp-server",
        description="Sieve-MCP: hand local files to AI tools in a "
                    "shareable form over the sieve-tray engines.")
    parser.add_argument("--root", action="append", default=[],
                        metavar="DIR",
                        help="an allowed data folder (one or more)")
    parser.add_argument("--out", metavar="DIR",
                        help="the output folder (required)")
    parser.add_argument("--max-read-chars", type=int,
                        default=MAX_READ_CHARS_DEFAULT, metavar="N",
                        help="the read_handoff slice cap "
                             "(default 8000, cap 20000)")
    parser.add_argument("--max-file-bytes", type=int,
                        default=MAX_FILE_BYTES_DEFAULT, metavar="N",
                        help="the per-file byte cap (default 5 MiB)")
    parser.add_argument("--max-files", type=int, default=MAX_FILES_DEFAULT,
                        metavar="N",
                        help="the per-run file count cap (default 512)")
    parser.add_argument("--self-check", action="store_true",
                        help="run the in-process check (exit 0 / 1 / 2)")
    parser.add_argument("--print-config", action="store_true",
                        help="print the client configuration from the "
                             "given --root / --out values")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_check:
        from .selfcheck import run_self_check
        return run_self_check()
    if args.print_config:
        from .printconfig import print_config
        if not args.root or not args.out:
            parser.print_usage(sys.stderr)
            return 2
        return print_config(args.root, args.out)
    if not args.root or not args.out:
        parser.print_usage(sys.stderr)
        return 2
    try:
        spaces = Spaces(args.root, args.out,
                        max_read_chars=args.max_read_chars,
                        max_file_bytes=args.max_file_bytes,
                        max_files=args.max_files)
    except StartupError:
        print("sieve-mcp-server: the startup options are invalid - the "
              "roots and the output folder must be existing folders and "
              "must not contain each other.", file=sys.stderr)
        return 2
    return serve(spaces)


__all__ = ["main", "build_parser", "MAX_READ_CHARS_CAP",
           "MAX_READ_CHARS_DEFAULT", "MAX_FILE_BYTES_DEFAULT",
           "MAX_FILES_DEFAULT", "__version__"]
