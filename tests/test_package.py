"""MC-T11 (the package carries exactly one runtime dependency and a
fresh venv runs the self-check from the wheel) and MC-T12 (the version
pins, the docs, the public-text watch and the release wiring)."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from helpers import REPO_ROOT

TOOL_NAMES = ["prepare_for_sharing", "read_handoff", "observe_hidden_text",
              "verify_record", "remove_metadata", "create_file_list"]


def _build_wheel(tmp: Path) -> Path:
    dist = tmp / "dist"
    dist.mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(REPO_ROOT),
         "--no-deps", "-w", str(dist)],
        capture_output=True, check=True, timeout=600)
    wheels = list(dist.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _wheel_texts(wheel: Path) -> dict:
    texts = {}
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            if name.endswith(("METADATA", "entry_points.txt")):
                texts[name.split("/")[-1]] = \
                    zf.read(name).decode("utf-8")
    return texts


def test_mct11_wheel_metadata_declares_one_runtime_dependency(tmp_path):
    wheel = _build_wheel(tmp_path)
    meta = _wheel_texts(wheel)["METADATA"]
    requires = [ln for ln in meta.splitlines()
                if ln.startswith("Requires-Dist:")]
    # the extras (pytest, mcp) ride the test extra - the runtime side
    # is the one dependency without an extra marker
    runtime = [ln for ln in requires if "extra ==" not in ln]
    assert len(runtime) == 1, requires
    assert "sieve-tray" in runtime[0]
    assert ">=2.6.0" in runtime[0]
    assert "Requires-Python: >=3.10" in meta
    entries = _wheel_texts(wheel)["entry_points.txt"]
    assert "sieve-mcp-server = sieve_mcp_server.cli:main" in entries


def test_mct11_fresh_venv_install_and_self_check(tmp_path):
    wheel = _build_wheel(tmp_path)
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)],
                   capture_output=True, check=True, timeout=300)
    py = venv / "Scripts" / "python.exe" if sys.platform == "win32" \
        else venv / "bin" / "python"
    subprocess.run([str(py), "-m", "pip", "install", str(wheel)],
                   capture_output=True, check=True, timeout=600)
    proc = subprocess.run(
        [str(py), "-m", "sieve_mcp_server", "--self-check"],
        capture_output=True, timeout=600)
    assert proc.returncode == 0, (
        proc.stdout.decode("utf-8", "replace")[-2000:]
        + proc.stderr.decode("utf-8", "replace")[-2000:])


def test_mct12_version_pins_across_the_release_surface():
    from sieve_mcp_server import __version__
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.startswith("# Changelog")
    assert "## [%s]" % __version__ in changelog.splitlines()[2]
    for name in ("README.md", "README.ja.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert __version__ in text, name
        assert "sieve-mcp-server" in text, name
        assert "pip install sieve-mcp-server" in text, name
    # the docs register the six tools
    docs = (REPO_ROOT / "docs" / "tools.md").read_text(encoding="utf-8")
    for tool in TOOL_NAMES:
        assert tool in docs, tool
    protocol_doc = (REPO_ROOT / "docs" / "protocol.md").read_text(
        encoding="utf-8")
    for version in ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"):
        assert version in protocol_doc, version


def test_mct12_public_text_watch_runs_green():
    proc = subprocess.run(
        [sys.executable, "tools/check_public_text.py"],
        capture_output=True, timeout=300, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, (
        proc.stdout.decode("utf-8", "replace")[-4000:])
    baseline = json.loads(
        (REPO_ROOT / "tests" / "public_text_baseline.json").read_text(
            encoding="utf-8"))
    assert baseline == {}


def test_mct12_public_text_watch_flags_the_red_inputs():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import check_public_text as cpt
    assert len(cpt.scan_text("the design chat decided")) == 1
    assert len(cpt.scan_text("see /home/user/notes")) == 1
    assert len(cpt.scan_text("see §3 of the plan")) == 1
    assert len(cpt.scan_text("pin MC-T12", test_numbers=True)) == 1
    assert len(cpt.scan_text("fixed on 2026-11-27", dates=True)) == 1
    assert cpt.scan_text("a clean factual line") == []


def test_mct12_ci_and_release_wiring():
    test_yml = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(
        encoding="utf-8")
    for os_name in ("ubuntu-24.04", "windows-latest", "macos-15"):
        assert os_name in test_yml, os_name
    assert '"3.10"' in test_yml
    assert "tools/check_public_text.py" in test_yml
    assert "origin/main..HEAD" in test_yml
    release_yml = (REPO_ROOT / ".github" / "workflows" / "release.yml") \
        .read_text(encoding="utf-8")
    assert "tools/extract_changelog.py" in release_yml
    assert "--text release_body.md" in release_yml
    assert "SHA256SUMS.txt" in release_yml
    assert "actions/attest" in release_yml
    assert "workflow_dispatch" in release_yml
    # the manual trial run covers the release body and the checksums
    # list: the extraction (with the version read from the package's
    # single source when no tag exists), its public-text watch and the
    # SHA256SUMS list run before the single push guard, and the trial's
    # results stay as named build artifacts; the provenance attestation
    # and the release attach wait for a tag push behind the one guard
    guard = "if: github.event_name == 'push'"
    assert release_yml.count(guard) == 1
    guard_at = release_yml.index(guard)
    trial_steps = ("tools/extract_changelog.py", "--text release_body.md",
                   "sha256sum *.whl *.tar.gz",
                   'test -f "artifacts/sieve_mcp_server-')
    trial_at = [release_yml.index(step) for step in trial_steps]
    assert max(trial_at) < guard_at
    publish_steps = ("actions/attest", "action-gh-release")
    publish_at = [release_yml.index(step) for step in publish_steps]
    assert min(publish_at) > guard_at
    assert "sieve_mcp_server/__init__.py" in release_yml
    assert "import sieve_mcp_server" in release_yml
    # the release version is checked against the artifact names before
    # anything else consumes the run: the tag names it on a tag push,
    # the package's single source names it on the trial, and the
    # checked value rides the environment into the extraction
    for name_line in ('test -f "artifacts/sieve_mcp_server-'
                      '${VERSION}.tar.gz"',
                      'test -f "artifacts/sieve_mcp_server-'
                      '${VERSION}-py3-none-any.whl"'):
        assert name_line in release_yml
    assert 'echo "RELEASE_VERSION=${VERSION}" >> "${GITHUB_ENV}"' \
        in release_yml
    assert 'extract_changelog.py "${RELEASE_VERSION}"' in release_yml
    for artifact in ("name: dist", "name: SHA256SUMS.txt",
                     "name: release-body"):
        assert artifact in release_yml


def test_mct12_the_release_rides_the_bundle_lane_and_the_attach_gate():
    release_yml = (REPO_ROOT / ".github" / "workflows" / "release.yml") \
        .read_text(encoding="utf-8")
    # the bundle lane rides the trial run too: the recipe is the
    # checked-in script and the official CLI validates and packs it
    assert "tools/build_mcpb.py" in release_yml
    assert "@anthropic-ai/mcpb" in release_yml
    assert "name: mcpb" in release_yml
    assert "tools/build_mcpb.py" in release_yml.split("workflow_dispatch")[1]
    # the bundle rides the checksums list and the release attach only
    # when the repository variable says the trial bundle passed on the
    # real Desktop; the ship step stages its assets into one folder, so
    # the attach step's glob never matches an empty set
    assert release_yml.count("vars.MCPB_ATTACH") == 2
    assert release_yml.count('[ "${MCPB_ATTACH}" = "yes" ]') == 2
    sums_at = release_yml.index("sha256sum *.whl *.tar.gz")
    bundle_sums_at = release_yml.index('sha256sum sieve-mcp-*.mcpb')
    assert bundle_sums_at > sums_at
    assert "release-assets" in release_yml
    guard = "if: github.event_name == 'push'"
    assert release_yml.count(guard) == 1
    guard_at = release_yml.index(guard)
    assert release_yml.index("release-assets") > guard_at


def test_mct21_the_release_body_stays_clean():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import check_public_text as cpt
    import extract_changelog as ec
    from sieve_mcp_server import __version__
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    body = ec.extract(changelog, __version__)
    assert body.strip(), __version__
    # the body the release attaches reads as facts only
    assert cpt.scan_text(body) == []
