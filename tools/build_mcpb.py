#!/usr/bin/env python3
"""Build the .mcpb bundle of Sieve-MCP.

The release workflow runs this script; the recipe lives here and never
in a manual step.  The recipe:

1. the release wheel is installed WITH its runtime dependencies into
   ``server/lib`` (the chain is resolved from the package index, the
   same way a user's install resolves it),
2. the launcher (``server/server.py``) starts the console entry point,
3. the manifest is written from the package's single version source
   (``sieve_mcp_server/__init__.py``),
4. the assembled tree is checked for compiled parts (a ``.so`` or a
   ``.pyd`` stops the build - the bundle format cannot carry them),
5. the official CLI (``@anthropic-ai/mcpb``) validates the manifest and
   packs the folder (skipped with ``--no-pack`` for the test lanes,
   which have no npm).

The launch command is ``python3`` with a ``win32`` override to
``python``: macOS machines ship ``python3`` only, the Windows installs
answer to ``python``, and the manifest format carries the per-platform
override (``mcp_config.platform_overrides``).
"""

import argparse
import glob
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_NAME = "sieve-mcp"
DESCRIPTION = "Hands local files to AI tools in a shareable form."
LAUNCHER = """\
import sys

from sieve_mcp_server.cli import main

if __name__ == "__main__":
    sys.exit(main())
"""


def build_manifest(version: str) -> dict:
    return {
        "manifest_version": "0.3",
        "name": BUNDLE_NAME,
        "display_name": "Sieve-MCP",
        "version": version,
        "description": DESCRIPTION,
        "author": {"name": "Kai IWASAKI"},
        "license": "MIT",
        "compatibility": {"runtimes": {"python": ">=3.10"}},
        "server": {
            "type": "python",
            "entry_point": "server/server.py",
            "mcp_config": {
                "command": "python3",
                "args": ["${__dirname}/server/server.py",
                         "--root", "${user_config.root}",
                         "--out", "${user_config.out}"],
                "env": {"PYTHONPATH": "${__dirname}/server/lib"},
                "platform_overrides": {
                    "win32": {"command": "python"},
                },
            },
        },
        "user_config": {
            "root": {
                "type": "directory",
                "title": "Allowed folder",
                "description": "The folder whose files may be shared. It "
                               "must be an existing folder, different "
                               "from the output folder, and neither "
                               "folder may contain the other.",
                "required": True,
            },
            "out": {
                "type": "directory",
                "title": "Output folder",
                "description": "The folder the shareable copies go into. "
                               "It must be an existing folder, different "
                               "from the allowed folder, and neither "
                               "folder may contain the other.",
                "required": True,
            },
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Sieve-MCP .mcpb bundle")
    parser.add_argument("--wheel", required=True,
                        help="the release wheel (a glob is allowed)")
    parser.add_argument("--dest", required=True,
                        help="the output folder (the assembled bundle and "
                             "the packed file land here)")
    parser.add_argument("--no-pack", action="store_true",
                        help="stop after the assembled folder (the test "
                             "lanes have no npm; the release run packs)")
    opts = parser.parse_args(argv)

    wheels = sorted(glob.glob(opts.wheel))
    if len(wheels) != 1:
        print("expected exactly one wheel, got %d: %s"
              % (len(wheels), wheels[:5]), file=sys.stderr)
        return 2
    wheel = Path(wheels[0]).resolve()

    sys.path.insert(0, str(REPO_ROOT))
    from sieve_mcp_server import __version__

    dest = Path(opts.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    bundle = dest / BUNDLE_NAME
    lib = bundle / "server" / "lib"
    lib.mkdir(parents=True, exist_ok=True)

    # the runtime dependencies ride the bundle: the wheel itself and
    # the chain it declares, resolved from the package index
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--target",
         str(lib), str(wheel)], check=True)

    (bundle / "server" / "server.py").write_text(LAUNCHER, encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps(build_manifest(__version__), ensure_ascii=False,
                   indent=2) + "\n", encoding="utf-8")

    # a compiled part cannot ride the bundle format - the build stops
    compiled = [p.name for p in lib.rglob("*")
                if p.suffix in (".so", ".pyd")]
    if compiled:
        print("compiled parts cannot ride the bundle: %s" % compiled[:5],
              file=sys.stderr)
        return 1

    if opts.no_pack:
        print(bundle)
        return 0

    subprocess.run(["mcpb", "validate", str(bundle)], check=True)
    packed = dest / ("%s-%s.mcpb" % (BUNDLE_NAME, __version__))
    subprocess.run(["mcpb", "pack", str(bundle), str(packed)], check=True)
    print(packed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
