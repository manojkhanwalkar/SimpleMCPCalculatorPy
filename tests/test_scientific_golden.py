"""The Python scientific server against responses captured from the Java server (6794f98).

No tolerance: every result, error and listing must match exactly (the Java tools are already
annotated read-only, so the listing matches as captured).
"""

import sys
from collections.abc import Iterator

import pytest

from simple_mcp_calculator.scientific_server.tools import SPEC
from tests.golden_support import Golden
from tests.rpc import RawSession

GOLDEN = Golden(SPEC)


def test_golden_file_is_complete() -> None:
    assert len(GOLDEN.cases) > 900
    assert {c["tool"] for c in GOLDEN.cases} >= {t.name for t in SPEC.tools}


def test_every_captured_call_matches_java() -> None:
    assert GOLDEN.in_process_mismatches() == []


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RawSession]:
    log = tmp_path_factory.mktemp("logs") / "server.log"
    command = [sys.executable, "-m", "simple_mcp_calculator.scientific_server"]
    with RawSession([*command, f"--logging.file.name={log}"]) as session:
        yield session
        assert session.close() == ""


def test_initialize_matches_java(server: RawSession) -> None:
    assert server.initialize_result == GOLDEN.meta["initialize"]


def test_tools_list_matches_java(server: RawSession) -> None:
    assert server.request("tools/list")["result"] == GOLDEN.meta["tools"]


def test_every_captured_call_matches_java_over_stdio(server: RawSession) -> None:
    """All 932 calls exceed the default burst of 400, so send every third one."""
    sample = GOLDEN.cases[::3]
    assert len(sample) < 400
    assert GOLDEN.stdio_mismatches(server, sample) == []
