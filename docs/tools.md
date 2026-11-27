# docs/tools.md — 道具の入力と応答の形

起動:

```
sieve-mcp-server --root DIR [--root DIR ...] --out DIR
                 [--max-read-chars N] [--max-file-bytes N] [--max-files N]
```

- `--root` は 1 つ以上・`--out` は必須。いずれも存在するフォルダで、互いを含んではいけない（違反は終了符号 2）。
- `--max-read-chars` は `read_handoff` の 1 回の長さの上限（既定 8,000・上限 20,000）。`--max-file-bytes` は 1 ファイルのバイト上限（既定 5 MiB）。`--max-files` は 1 回の実行のファイル数の上限（既定 512）。

すべての道具の入力は JSON Schema つきのオブジェクトで、`tools/list` の `inputSchema` が正。未知の鍵・欠けた鍵・型の違いは `invalid_arguments`。応答は `structuredContent`（下の形）と、同じ内容の JSON 文字列 1 個の `content` の両方で、失敗には `isError: true` がつく。

## 誤りの 8 語（閉じた一覧）

| 語 | 固定文 |
| --- | --- |
| `path_not_allowed` | The path is not allowed. |
| `not_found` | The path does not exist. |
| `not_a_regular_file` | The path is not a regular file. |
| `too_large` | The file or the folder exceeds the size limits. |
| `unsupported_type` | The file type is not supported. |
| `invalid_arguments` | The tool arguments are invalid. |
| `run_failed` | The engine run failed. |
| `read_not_allowed` | Reading this file is not allowed. |

失敗の応答は `{"ok": false, "code": <語>, "message": <固定文>}`。例外の文面・パス・ファイル名は入らない。

## パスの規則

- 道具の引数のパスは、`--root` からの相対パス。絶対パスは、その実体がいずれかの `--root`（読む側）または `--out`（読み返す側）の中にあるときだけ受け付ける。
- `..` を含む形・途中にシンボリックリンクを含む形・特殊ファイルは、常に `path_not_allowed` または `not_a_regular_file`。
- 応答に出るパスは、`--root` または `--out` からの相対パスで、区切りはどの OS でも `/`。

## prepare_for_sharing

- 入力: `path`（必須）・`name`（出力フォルダの名前・省略可）・`same_value`（省略可・真なら同じ値に同じ記号）。
- `path` はファイルでもフォルダでもよい。フォルダは Gate の ingest が `.obsidian/`・`.trash/` を読み飛ばす。
- 出力フォルダは `--out` の下の連番（`0001`、`0002`、…）。`name` を与えたときはその名前（英数字と `.`・`-`・`_`・64 文字まで・既存は `invalid_arguments`）。
- 応答: `output_dir`（`--out` からの相対）・`items`（`path`・`status`（`flagged` / `clean` / `unobserved`）・理由の語）・`hidden_kinds`（隠れた文字の種類の語ごとの件数: `zero_width_space`・`word_joiner`・`bom_mid_text`・`tag_chars`・`bidi_control`）・`handoff_files`（`handoff/` のファイル名と大きさ）・`record_digest`（`sha256:` つき・同じ中身なら場所が変わっても同じ値）。

## read_handoff

- 入力: `path`（必須・`--out` の下の `handoff/` の中）・`offset`・`limit`（省略可）。
- 読めるのは拡張子 `.txt` / `.md` / `.html` / `.csv` の UTF-8 のテキストだけ。`local/` は `read_not_allowed`、受領書の JSON は `unsupported_type`、UTF-8 でない本文も `unsupported_type`。
- 応答: `content`・`total_chars`・`next_offset`（終わりでは `null`）。

## observe_hidden_text

- 入力: `path`（必須）・`only_hidden`（省略可）。
- 応答は Tray の `check_paths` の形のまま（`check_version: 1`・`excluded_dirs`・`items`・`summary`）。`items` の `path` は root 相対の POSIX 形に置き換えたもの。本文・種類語の個数以外の文字列は出ない。

## verify_record

- 入力: `record`（`--out` の下の処理記録のパス）・`against`（対象のフォルダ）。
- 処理記録の種類で当てはめが変わる: `sieve-gate` と `sieve-clean` は `against` に記録の出力フォルダ（連番フォルダ）を取り、`sieve-manifest` は `against` に一覧の作成元（連番フォルダの下の `local/staging`）を取る。
- 応答: `overall`（`match` / `differs` / `not_verifiable`）・`scope`・`reasons`（`path` と理由語。理由語は `output_missing` / `output_changed` / `input_missing` / `input_changed` / `item_added` の閉じた集合）・`not_verifiable_reason`（`handoff_incomplete` / `receipt_unreadable` / `receipt_digest_mismatch` / `receipt_version_unsupported` / `settings_unavailable`）。

## remove_metadata

- 入力: `path`（必須・`.jpg` / `.jpeg` / `.png` / `.docx` / `.xlsx` / `.pptx` / `.pdf` が対象、それ以外は `not_applicable`）・`name`（省略可）。
- Tray の clean（`run_clean`）を呼ぶ。元のファイルは書き換えない。コピーは出力フォルダの `handoff/`、除去した値の記録は `local/`（読み返しの対象外）。
- 応答: `output_dir`・`items`（`path`・`status`（`cleaned` / `refused` / `not_applicable`）・`reason`・`format`・`categories_before`・`categories_after`（分類 8 語: `author`・`time`・`software`・`location`・`device`・`title_subject`・`thumbnail`・`custom`）・`content_checksum_match`・`output`）・`record_path`・`record_digest`。除去した値は応答に入らない。

## create_file_list

- 入力: `path`（必須）・`name`（省略可）。
- フォルダの対象は Tray の Gate ingest と同じ走査で `.obsidian/`・`.trash/` を落としてから、Tray の manifest に渡す（一時の staging で実行して消す）。
- 応答: `output_dir`・`file_count`・`overall_sha256`（木全体のチェックサム・64 文字）・`record_path`。
