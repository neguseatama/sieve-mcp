# Changelog

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
