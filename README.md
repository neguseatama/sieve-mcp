**English** | [日本語](README.ja.md)

# Sieve-MCP v0.1.1 (sieve-mcp-server)

**The MCP server that hands local files to AI tools in a form ready to share**

Sieve-MCP is a small Model Context Protocol server for Claude Desktop,
Claude Code, and any other MCP client. It works as a lightweight wrapper
with the [Sieve Tray](https://github.com/neguseatama/sieve-tray) engines
installed: when the AI specifies a file or folder inside the folders you
allow, the reply includes what the material looks like and where the
shareable copy went — counts, status words, checksums, digests, and
relative paths. The package installs as `sieve-mcp-server`; the product
name is Sieve-MCP.

```
pip install sieve-mcp-server
```

The only runtime dependency is `sieve-tray>=2.6.0,<3` (installed
automatically, no extra needed). Requires Python >= 3.10.

## Configure

### Claude Desktop

Edit `claude_desktop_config.json` (the standard places: macOS
`~/Library/Application Support/Claude/`, Windows `%APPDATA%\Claude\`)
and add:

```json
{
  "mcpServers": {
    "sieve-mcp": {
      "command": "sieve-mcp-server",
      "args": ["--root", "/path/to/your/folder",
               "--out", "/path/to/output"]
    }
  }
}
```

### Claude Code

```
claude mcp add sieve-mcp -- sieve-mcp-server --root /path/to/your/folder --out /path/to/output
```

`--root` names the folders the server may read (one or more); `--out`
names the folder every run writes into; the two must not contain each
other. `sieve-mcp-server --print-config --root ... --out ...` prints
this configuration from your own values, and
`sieve-mcp-server --self-check` runs the whole flow in one process and
exits 0 when everything matches.

### Claude Desktop (the .mcpb bundle)

Download `sieve-mcp-0.1.1.mcpb` from the release page of the
repository and drag it into the Claude Desktop window. The installer
asks for the two folders (the allowed folder and the output folder;
two different folders, neither containing the other) and writes the
configuration for you.

> The official MCP registry lists this server too: clients that
> support the registry can install it from there (the `server.json`
> file at the repository root carries the registered shape).

## The tools

| Tool | What it does | What the reply carries |
| --- | --- | --- |
| `prepare_for_sharing` | Strips hidden characters and masks sensitive values into a fresh output folder (`handoff/` + `local/`) | Per-item status words, hidden-character kind counts, handoff file names and sizes, the record digest |
| `read_handoff` | Reads a UTF-8 text from a previous output's `handoff/` in slices | The text slice, the total length, the continuation offset |
| `observe_hidden_text` | Observes a file or a folder for hidden text, writing nothing | The check shape (`check_version: 1`): per-file status words and kind counts |
| `verify_record` | Re-checks a run record against a folder | `match` / `differs` / `not_verifiable` with the closed reason words |
| `remove_metadata` | Copies a JPEG, PNG, Office or PDF file with its metadata stripped | The eight metadata categories before and after, the re-observation, the output path |
| `create_file_list` | Lists a tree with per-file hashes and the whole-tree checksum | The file count, the overall checksum, the record path |

## How the answers stay safe

Every reply carries counts, status words, checksums and relative paths
only - the hidden text, the metadata values, the layer names and the
absolute paths never enter a reply, and everything the engines print
during a run is captured and dropped, so the protocol stream carries
the JSON messages alone. The server reads only inside the `--root`
folders (no `..`, no symbolic links, no special files), writes only
under `--out` into numbered folders that are never overwritten, leaves
the originals untouched, and skips the `.obsidian/` and `.trash/`
folders of a folder target by default. Starting the server with
`--numbered-names` replaces the file names in the replies with
sequential numbers; the mapping between the numbers and the original
names rides each run's `local/` folder only.

## Scope

What the server does: it runs the Sieve Tray engines on the files
inside the folders you allow, hands the shareable copies to the AI,
and keeps every reply to counts, status words, checksums and relative
paths. The originals never change.

What it does not do: the observation covers the hidden-text and
metadata kinds the engines list - forms outside those lists are not
found; nothing here scans for malware; and which files the AI asks
for is governed by how you use the client, not by the server. The
software is provided under the MIT license, without warranty of any
kind.

## Development

- Test suite: `python -m pytest -v` (the protocol tests also ride the
  official SDK; `pip install ".[test]"`).
- Public-text watch: `python tools/check_public_text.py`.
- The docs: `docs/tools.md` (the tool shapes) and `docs/protocol.md`
  (the protocol versions and their sources).

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 👤 Author

* **Kai IWASAKI**

Copyright (c) 2026 Kai IWASAKI

mcp-name: io.github.neguseatama/sieve-mcp
