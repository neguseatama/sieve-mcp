"""The suite-wide fixtures: fresh root and output folders per test."""

import pytest

from helpers import build_fixture


@pytest.fixture
def root_dir(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    build_fixture(root)
    return root


@pytest.fixture
def out_dir(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    return out


@pytest.fixture
def anyio_backend():
    return "asyncio"
