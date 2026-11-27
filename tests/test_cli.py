"""MC-T10: the two auxiliary commands - the in-process self-check with
its 0 / 1 / 2 contract and the configuration printer that never
invents an absolute path."""

import json
import subprocess
import sys

from helpers import REPO_ROOT


def test_mct10_self_check_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "sieve_mcp_server", "--self-check"],
        capture_output=True, timeout=300, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, (
        "rc=%d\nstdout=%s\nstderr=%s"
        % (proc.returncode,
           proc.stdout.decode("utf-8", "replace")[-2000:],
           proc.stderr.decode("utf-8", "replace")[-2000:]))
    body = json.loads(proc.stdout.decode("utf-8"))
    assert body["self-check"] == "ok"
    assert body["checks"] >= 10


def test_mct10_self_check_contract_forms():
    from sieve_mcp_server import selfcheck
    # the difference form answers 1, the broken form answers 2
    def run_diff():
        raise selfcheck._Difference(["one difference"])

    def run_broken():
        raise RuntimeError("broken")

    orig = selfcheck._run
    selfcheck._run = run_diff
    try:
        assert selfcheck.run_self_check() == 1
    finally:
        selfcheck._run = orig
    selfcheck._run = run_broken
    try:
        assert selfcheck.run_self_check() == 2
    finally:
        selfcheck._run = orig


def test_mct10_print_config_carries_the_given_values_only(tmp_path,
                                                          capsys):
    from sieve_mcp_server.printconfig import print_config
    root_value = "share-root"
    out_value = "share-out"
    rc = print_config([root_value], out_value)
    assert rc == 0
    text = capsys.readouterr().out
    config = json.loads(text.split("\n\n")[0])
    entry = config["mcpServers"]["sieve-mcp"]
    assert entry["command"] == "sieve-mcp-server"
    assert entry["args"] == ["--root", root_value, "--out", out_value]
    # no absolute path of the running machine is invented
    assert sys.executable not in text
    assert str(tmp_path) not in text
    assert "# Claude Code:" in text
    assert text.rstrip().endswith(
        "claude mcp add sieve-mcp -- sieve-mcp-server "
        "--root share-root --out share-out")


def test_mct10_print_config_without_values_exits_two():
    from sieve_mcp_server.cli import main
    assert main(["--print-config"]) == 2
    assert main([]) == 2
