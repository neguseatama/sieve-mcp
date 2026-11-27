"""The public-text watch: the checker and the baseline.

The watch keeps the user-facing files (the two README files, the docs
directory, pyproject.toml, AGENTS.md, the newest CHANGELOG section) at
zero findings, and the Python sources at their per-file baseline of
the comment/docstring lines that carry a forbidden item (the counts
only ever shrink; a changed count in either direction fails, so the
baseline rides the change that touched the lines).

The checker lives in ``tools/``; the tools directory is not part of
the sdist, so these tests skip when it is absent (the sdist's test
run) and run in the repository tree.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(_ROOT))
sys.path.append(str(_ROOT / "tools"))

try:
    import check_public_text as cpt  # noqa: E402
except ImportError:  # the sdist does not ship tools/
    cpt = None

_BASELINE = json.loads(
    (_ROOT / "tests" / "public_text_baseline.json").read_text(
        encoding="utf-8"))

_TOOLS_PRESENT = cpt is not None


class TestPublicTextWatch(unittest.TestCase):

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_scan_text_flags_each_kind(self):
        cases = [
            ("design chat", "design chat"),
            ("dev chat", "dev chat"),
            ("design request", "design request"),
            ("red-first", "red-first"),
            ("golden", "golden"),
            ("mold", "mold"),
            ("sandbox", "sandbox"),
            ("chat_ja", "設計チャット"),
            ("request_ja", "依頼書"),
            ("decision_ja", "裁定"),
            ("nickname_ja", "金型"),
            ("absolute_path", "see /home/user/notes"),
            ("section_mark", "see §3.1 of the plan"),
        ]
        for name, line in cases:
            with self.subTest(case=name):
                self.assertEqual(len(cpt.scan_text(line)), 1)

        # the scoped items only fire on their own targets
        self.assertEqual(len(cpt.scan_text("pin MC-T12",
                                           test_numbers=True)), 1)
        self.assertEqual(cpt.scan_text("pin MC-T12"), [])
        self.assertEqual(len(cpt.scan_text("fixed on 2026-11-27",
                                           dates=True)), 1)
        self.assertEqual(cpt.scan_text("fixed on 2026-11-27"), [])

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_required_targets_are_at_zero(self):
        findings, _noted, mismatches = cpt.scan_repository()
        self.assertEqual(findings, [])
        self.assertEqual(mismatches, [])

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_text_mode_checks_one_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "note.txt"
            p.write_text("a clean line\n", encoding="utf-8")
            self.assertEqual(cpt.scan_text(p.read_text(encoding="utf-8"),
                                           test_numbers=True), [])
            p.write_text("mentions the dev chat and pin MC-T12\n",
                         encoding="utf-8")
            findings = cpt.scan_text(p.read_text(encoding="utf-8"),
                                     test_numbers=True)
            self.assertEqual(len(findings), 2)

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_text_mode_over_a_real_release_body(self):
        # the release body is built from the newest CHANGELOG section -
        # extracting and checking that body must pass at zero findings
        from check_public_text import _latest_changelog_section
        changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        heading, body = _latest_changelog_section(changelog)
        self.assertTrue(heading.startswith("## ["))
        self.assertEqual(cpt.scan_text(body, test_numbers=True), [])

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_baseline_counts_the_flagged_lines(self):
        # the baseline counts the comment/docstring lines that carry a
        # forbidden item (not the total line count)
        from check_public_text import (_iter_python_files,
                                       _python_scan_lines, scan_text)
        counted = {}
        for path in _iter_python_files(_ROOT):
            rel = path.relative_to(_ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            counted[rel] = sum(
                1 for line in _python_scan_lines(text) if scan_text(line))
        for rel, expected in _BASELINE.items():
            self.assertEqual(counted.get(rel, 0), expected, rel)
        for rel, actual in counted.items():
            if actual:
                self.assertIn(rel, _BASELINE, rel)

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_a_stale_or_grown_count_fails(self):
        # the match runs both ways: a grown count is the red itself, a
        # shrunk one asks for the baseline update
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# ok\n", encoding="utf-8")
            (root / "README.ja.md").write_text("# ok\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\n",
                                                 encoding="utf-8")
            (root / "AGENTS.md").write_text("# ok\n", encoding="utf-8")
            (root / "pkg.py").write_text(
                '# a golden mention\nx = 1\n', encoding="utf-8")
            (root / "tests").mkdir()
            baseline = root / "baseline.json"
            cpt_scan = cpt.scan_repository

            baseline.write_text(json.dumps({"pkg.py": 1}),
                                encoding="utf-8")
            cpt._BASELINE = baseline
            try:
                findings, _noted, mismatches = cpt_scan(root)
                self.assertEqual(findings, [])
                self.assertEqual(mismatches, [])

                baseline.write_text(json.dumps({"pkg.py": 2}),
                                    encoding="utf-8")
                _f, _n, mismatches = cpt_scan(root)
                self.assertEqual(mismatches, [("pkg.py", 2, 1)])

                baseline.write_text(json.dumps({}), encoding="utf-8")
                _f, _n, mismatches = cpt_scan(root)
                self.assertEqual(mismatches, [("pkg.py", 0, 1)])
            finally:
                cpt._BASELINE = _ROOT / "tests" / "public_text_baseline.json"

    @unittest.skipUnless(_TOOLS_PRESENT, "tools/ is not in the sdist")
    def test_watch_writes_utf8_stdout_on_any_console_encoding(self):
        # the flagged-line summary prints Japanese words; a captured
        # pipe with a legacy codepage must not break the watch
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "cp1252"
        proc = subprocess.run(
            [sys.executable,
             str(_ROOT / "tools" / "check_public_text.py")],
            capture_output=True, env=env,
            encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(
            proc.returncode, 0,
            "rc=%d\n=== stdout ===\n%s\n=== stderr ===\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:]))
        # the baseline starts at zero lines, so nothing is "recorded"
        self.assertNotIn("recorded", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
