# AGENTS.md

公開面の文章: README・docs・CHANGELOG・Release 本文・パッケージの説明・コミットメッセージ・コードのコメント・テストの説明文は、利用者と開発者に向けた事実の短い文で書く。作業の経緯・内部の呼び名・日付つきの決定・開発環境の情報・絶対パス・テストの番号（README・docs・CHANGELOG）を書かない。CHANGELOG の版の節は、3〜5 項目の短文にする。`tools/check_public_text.py` が通ること。

## Build and test

- Python >= 3.10（Tray 2.6.0 と同じ下限）。
- 実行時の依存は `sieve-tray>=2.6.0` のみ（extras なし）。テストだけが
  公式 SDK（`pip install ".[test]"` で `mcp` が入る）。
- Test suite: `python -m pytest -v`。
- Package build: `python -m build`。
- Public-text watch: `python tools/check_public_text.py`
  (runs in CI; one file: `--text FILE`)。

## Working rules

1. **test-first**: 修正の前に、そのふるまいを固定するテストを書き、
   実装の前の赤と実装後の緑を確認する。既存のテストは、その版の変更で
   意味が変わらない限り修正しない。
2. **語彙の規律**: 道具の名前・誤りの 8 語・状態と理由の語は、Tray と
   プロトコルの規格の閉じた集合だけ。増やすときは CHANGELOG の最新の
   節で宣言してから入れる。
3. **応答の作法**: 応答に出るのは、`handoff/` の内容・件数と種類の語・
   チェックサム・相対パスだけ。隠れた文字の本文・メタデータの値・
   絶対パス・ファイルの中の自由な文字列は、どの応答にも出さない。
   標準出力はプロトコルのメッセージだけ（エンジンの実行中は捕まえる）。
4. **版の作法**: 版は `sieve_mcp_server/__init__.py` の `__version__` が
   唯一の静的な源。pyproject は dynamic attr で参照し、README ×2 の
   題字と CHANGELOG の最新の節と docs の登録表はそれと一致させる。
   版を固定するテストは `__version__` との比較の形にする。
5. **CI**: 3 OS（ubuntu / windows / macos × 3.12、ubuntu 3.10 の下限）。
   環境に依存する失敗はテスト側を直し、製品の不具合は次の版で直す。
   期待するパスは OS に依存しない形（`as_posix()`）で組み、子プロセスの
   標準入出力はバイト列で扱う。
6. **公開の順序**: PR の merge → `release.yml` の手動試走（build と wheel
   の self-check・`tools/build_mcpb.py` による `.mcpb` の組立と公式 CLI
   による検証・成果物の名前と版の一致の確認・CHANGELOG の本文の抽出と
   点検・`SHA256SUMS.txt` の作成を成果物として残し、Release は作らない）→
   試走の `.mcpb` を実機の Claude Desktop で確かめ、起動と 6 道具の呼び出し
   が確認できたときだけリポジトリ変数 `MCPB_ATTACH` を `yes` にする
   （起動しない版では変数を据え置きのまま、その版は `.mcpb` を外して
   公開する）→ PyPI への公開（手動）→ tag → GitHub Release（tag のときだけ
   来歴証明と、本文と `SHA256SUMS.txt`（`.mcpb` を添付するときは `.mcpb`
   を含む）の添付を行う）。同一版のタグ・資産の差し替えはしない。公式
   MCP レジストリへの登録は PyPI 公開のあとに実行し、その時点の要件
   （料金の有無を含む）は登録の実行時に確かめる。
7. **機械の見張り**: 公開面の点検は手作業に頼らず
   `tools/check_public_text.py` と baseline で守る。触った行の
   コメント/docstring は規則に合わせ、baseline は下げる方向で更新する。
