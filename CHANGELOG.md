# Changelog

## [0.1.1] - 2026-11-28

### Added
- **Registry support**: `server.json` at the repository root rides the
  official MCP registry shape (the `pypi` package with the `uvx` hint,
  the stdio transport and the two required folder arguments), and the
  READMEs carry the `mcp-name: io.github.neguseatama/sieve-mcp`
  ownership line.
- **`--numbered-names`**: the startup flag replaces the file names in
  every reply with sequential numbers (0001, 0002, ...); the mapping
  table rides each run's `local/` folder only, never `handoff/`.
- **`.mcpb` bundle**: the release builds a Claude Desktop bundle with
  the server and its dependencies inside (the recipe is a checked-in
  script), attaches it to the GitHub Release with the wheel and the
  sdist, and the checksums list covers everything attached; the two
  folder questions state the rule (existing folders, different from
  each other, neither containing the other).

### Changed
- The one runtime dependency declares its ceiling:
  `sieve-tray>=2.6.0,<3`.
- The startup refusal names its reason and repeats the received folder
  values, and a leading tilde in an answer resolves against the home
  folder.
- The READMEs carry the scope section: what the server does and what
  it does not promise.
- Bundle the Sieve Tray icon in the MCPB (.mcpb) archive and add icons to server.json

## [0.1.0] - 2026-11-27

### Added
- **Sieve-MCP**: the MCP server that hands local files to AI tools in a
  shareable form - the six tools (`prepare_for_sharing`, `read_handoff`,
  `observe_hidden_text`, `verify_record`, `remove_metadata`,
  `create_file_list`) ride the standard input and output as
  line-delimited JSON, with `sieve-tray>=2.6.0` as the only runtime
  dependency.
- **Closed replies**: every tool answer carries counts, status words,
  checksums, digests and relative paths only - never the hidden text,
  the metadata values or the absolute paths - and the engine runs are
  isolated from the protocol stream on both the text and the
  descriptor layer.
- **Path safety**: the roots and the output folder must not contain
  each other, tool paths stay inside the roots (no `..`, no symbolic
  links, no special files), the outputs ride numbered folders that are
  never overwritten, and the `.obsidian/` / `.trash/` folders are
  skipped by default.
- **`--self-check` and `--print-config`**: the in-process check of the
  whole flow (exit 0 / 1 / 2) and the ready-to-paste configuration for
  Claude Desktop and Claude Code, built from the values you pass.
