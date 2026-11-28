"""The ``--print-config`` auxiliary command: the client configuration
built from the values the caller gave - never a discovered absolute
path of its own."""

import json
import sys

SERVER_KEY = "sieve-mcp"
SERVER_COMMAND = "sieve-mcp-server"


def build_args(root_values, out_value, numbered_names=False) -> list:
    args = []
    for root in root_values:
        args.extend(["--root", root])
    args.extend(["--out", out_value])
    if numbered_names:
        args.append("--numbered-names")
    return args


def build_config(root_values, out_value, numbered_names=False) -> dict:
    return {
        "mcpServers": {
            SERVER_KEY: {
                "command": SERVER_COMMAND,
                "args": build_args(root_values, out_value,
                                   numbered_names),
            }
        }
    }


def build_claude_code_command(root_values, out_value,
                              numbered_names=False) -> str:
    parts = ["claude", "mcp", "add", SERVER_KEY, "--", SERVER_COMMAND]
    parts.extend(build_args(root_values, out_value, numbered_names))
    return " ".join(parts)


def print_config(root_values, out_value, numbered_names=False) -> int:
    """Print the Claude Desktop configuration (JSON) and the Claude
    Code add command.  The root and the output values ride as they
    were given, and the numbered-names option rides only when it was
    given; the command is the console script's own name, so no
    absolute path of this machine is invented here."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(build_config(root_values, out_value, numbered_names),
                     ensure_ascii=False, indent=2))
    print()
    print("# Claude Code:")
    print(build_claude_code_command(root_values, out_value,
                                    numbered_names))
    return 0
