# docs/protocol.md — プロトコルの対応と出所

## 対応するプロトコルの版

- `initialize` で返す版の一覧（handshake の 4 版）:
  `2024-11-05`・`2025-03-26`・`2025-06-18`・`2025-11-25`。
- 交渉の規則: クライアントの要求版がこの一覧にあればそのまま返し、なければ `2025-11-25` を返す。版の不一致で接続は切らない。
- 出所: 公式 SDK（`mcp` 2.3.0・`mcp-types` 2.3.0）の実物。`KNOWN_PROTOCOL_VERSIONS` と `HANDSHAKE_PROTOCOL_VERSIONS` の一覧、交渉の規則（要求版が handshake の一覧になければ最新 handshake 版を返す 1 関数）は、SDK のソースを実取得して写した値で、記憶から書いていない。

## メッセージの形

- 1 メッセージ = 1 行の JSON・区切りは `\n` のみ・書いたら毎回 flush。UTF-8。標準入出力はバイト列で扱い（`sys.stdin.buffer` と、起動時に確保した標準出力の複製ディスクリプタ）、OS の改行変換に預けない。
- 出所: SDK の標準入出力トランスポートの実物（1 メッセージ 1 行の JSON・`\n` 区切り・毎回 flush の形）。
- `initialize` の応答の必須項目: `protocolVersion`・`capabilities`・`serverInfo`（名前と版）。任意で `instructions`（安全の一文）。
- `tools/list` の結果: `tools`（`name`・`description`・`inputSchema`）。`tools/call` の結果: `content`（必須）と `structuredContent`（任意）。道具の失敗は `isError: true` で運ぶ。
- JSON-RPC の誤り符号: `-32700`（parse error）・`-32600`（invalid request）・`-32601`（method not found）・`-32602`（invalid params）・`-32603`（internal error）。未知のメソッドは `-32601` で答え、サーバーは動き続ける。

## 標準出力の隔離

- 道具の実行中、サーバーは Python のテキスト層（`sys.stdout` / `sys.stderr`）と OS のディスクリプタ層（fd 1 / fd 2）の両方を差し替え、エンジンが書くものをすべて捕まえて捨てる。プロトコルの書き込みは、起動時に確保した複製ディスクリプタだけを使う。
- そのため、内部でエンジンの CLI 入口を呼ぶ経路（Gate の Redact 呼び出しがテキストストリームを UTF-8 に再設定する経路を含む）のあとでも、プロトコルの流れは壊れない。

## クライアントの設定の形（出所つき）

- Claude Code: `claude mcp add [options] <name> -- <command> [args...]`（scope は local / project / user・プロジェクト共有は `.mcp.json`・`claude mcp add-json`）。出所: 公式の Claude Code ドキュメントの MCP のページ（実取得）。
- Claude Desktop: `claude_desktop_config.json` の `mcpServers`（`command` と `args`）。設置場所の標準形は macOS `~/Library/Application Support/Claude/claude_desktop_config.json`・Windows `%APPDATA%\Claude\claude_desktop_config.json`（複数の案内記事が一致して報じる形。Microsoft Store 版では場所が仮想化されるという報告がある）。公式文書は取得できていないので、README では「標準的な場所」として短く書き、確定は利用者の環境で行う。
- `--print-config` は、この `mcpServers` の形と `claude mcp add` の例を、与えられた `--root` / `--out` の値から出す。サーバー自身の絶対パスを勝手に埋めない（コマンドはコンソールスクリプトの名前のまま）。

## 未実測の項目（明記）

- PyPI 公開後の `pip install sieve-mcp-server` による `--self-check`（wheel からの同等の手順は試験で実測済み）。
- Claude Desktop・Claude Code からの実接続と 6 道具の呼び出し（利用者の環境で確認する。`--self-check` と `--print-config` が接続前の確認に使える）。
- Claude Desktop 設定ファイルの設置場所の公式文書による確定。
