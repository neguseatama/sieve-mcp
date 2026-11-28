[English](README.md) | **日本語**

# Sieve-MCP v0.1.1（sieve-mcp-server）

**ローカルのファイルを、共有できる形で AI ツールへ渡す MCP サーバー**

Sieve-MCP は、Claude Desktop・Claude Code などの MCP クライアント向けの小さなサーバーです。[Sieve Tray](https://github.com/neguseatama/sieve-tray) のエンジンをインストールした軽量なラッパーとして動きます。AI が、あなたが許したフォルダの中のファイルやフォルダを名指すと、応答は「その材料がどんなものか」と「渡してよいコピーがどこにできたか」を運びます - 件数・状態の語・チェックサム・ダイジェスト・相対パスです。パッケージの名前は `sieve-mcp-server`、プロダクト名は Sieve-MCP です。

```
pip install sieve-mcp-server
```

実行時の依存は `sieve-tray>=2.6.0,<3` だけ（自動で入る・extra は不要）。Python は 3.10 以上です。

## 設定

### Claude Desktop

`claude_desktop_config.json`（標準的な場所: macOS は `~/Library/Application Support/Claude/`、Windows は `%APPDATA%\Claude\`）に次の形を加えます。

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

`--root` はサーバーが読んでよいフォルダ（1 つ以上）・`--out` は実行の結果を書くフォルダで、両者が互いを含んではいけません。`sieve-mcp-server --print-config --root ... --out ...` はあなたの指定から上の設定を画面に出し、`sieve-mcp-server --self-check` は流れ全体を 1 プロセスで実行して、すべてが期待どおりなら終了符号 0 で終わります。

### Claude Desktop（.mcpb バンドル）

リポジトリのリリースページから `sieve-mcp-0.1.1.mcpb` をダウンロードして、Claude Desktop の画面にドラッグします。インストーラーが 2 つのフォルダ（許すフォルダと出力フォルダ）を尋ね、設定を書き込みます。2 つは互いに異なる別々のフォルダにします（どちらが相手を含んでもいけません）。

> 公式の MCP レジストリにもこのサーバーを登録してあります。レジストリに対応したクライアントはそこから入れます（リポジトリ直下の `server.json` がその登録の形です）。

## 道具の一覧

| 道具 | すること | 応答の中身 |
| --- | --- | --- |
| `prepare_for_sharing` | 隠れた文字を除き、同じ値を同じ記号で覆い、新しい出力フォルダ（`handoff/` と `local/`）に書き出す | 項目ごとの状態の語・隠れた文字の種類ごとの件数・`handoff/` のファイル名と大きさ・処理記録のダイジェスト |
| `read_handoff` | 前の出力の `handoff/` の UTF-8 のテキストを、区切って読む | テキストの区切り・全体の長さ・続きの位置 |
| `observe_hidden_text` | ファイルやフォルダを、何も書かずに観測する | チェックの形（`check_version: 1`）: ファイルごとの状態の語と種類ごとの件数 |
| `verify_record` | 処理記録をフォルダに対して確かめ直す | `match` / `differs` / `not_verifiable` と、閉じた語の理由 |
| `remove_metadata` | JPEG・PNG・Office・PDF からメタデータを除いたコピーを作る | 分類 8 語の前後の件数・再観測の結果・出力の相対パス |
| `create_file_list` | ファイルごとのハッシュと木全体のチェックサムつきの一覧を作る | ファイルの数・フォルダ全体のチェックサム・処理記録のパス |

## 応答が安全に保たれるしかけ

応答に出るのは件数・状態の語・チェックサム・相対パスだけです。隠れた文字の本文・メタデータの値・レイヤー名・絶対パスはどの応答にも入らず、エンジンが実行中に標準出力に書くものは捕まえて捨てるので、プロトコルの流れには JSON のメッセージだけが乗ります。サーバーは `--root` のフォルダの中だけを読み（`..`・シンボリックリンク・特殊ファイルは拒否）、書き込みは `--out` の下の、上書きしない連番フォルダだけに限り、元のファイルは変えず、フォルダの対象では `.obsidian/` と `.trash/` を既定で読み飛ばします。`--numbered-names` を付けて起動すると、応答に出るファイルの名前が連番に変わり、番号と元の名前の対応表は実行ごとの `local/` フォルダにだけ書かれます。

## 保証の範囲

できること: あなたが許したフォルダの中のファイルに対して Sieve Tray のエンジンを実行し、渡してよいコピーを AI に渡します。応答は件数・状態の語・チェックサム・相対パスだけを運び、元のファイルは変わりません。

しないこと: 観測の対象は、エンジンが一覧している隠れた文字とメタデータの種類で、その外の形は見つかりません。マルウェアの検査はしません。AI がどのファイルを名指すかは、クライアントの使い方で制御するもので、サーバーが制御するものではありません。本ソフトウェアは MIT ライセンスのとおり、無保証で提供されます。

## 開発

- Test suite: `python -m pytest -v`（プロトコルの試験は公式 SDK でも走ります。`pip install ".[test]"`）。
- 公開面の点検: `python tools/check_public_text.py`。
- docs: `docs/tools.md`（道具の形）と `docs/protocol.md`（プロトコルの版と出所）。

---

## 📄 ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照してください。

---

## 👤 Author

* **Kai IWASAKI**

Copyright (c) 2026 Kai IWASAKI

mcp-name: io.github.neguseatama/sieve-mcp
