"""The Python calculator server against responses captured from the Java server (6794f98).

Two documented exceptions: ``exponent`` with a negative exponent may differ by one ulp (Java's
``Math.pow`` and C's ``pow`` round differently in rare cases; the Java spec itself only promises
1 ulp), and the port annotates every tool read-only (a decision for the port).
"""

import sys
from collections.abc import Iterator

import pytest

from simple_mcp_calculator.calculator_server.tools import SPEC
from tests.golden_support import Golden
from tests.rpc import RawSession

# Math.pow with a negative exponent can differ from C pow by 1 ulp (none in the captured set).
GOLDEN = Golden(SPEC, ulp_limits={"exponent": 1})


def test_golden_file_is_complete() -> None:
    assert len(GOLDEN.cases) > 6000
    assert {c["tool"] for c in GOLDEN.cases} >= {t.name for t in SPEC.tools}


def test_every_captured_call_matches_java() -> None:
    assert GOLDEN.in_process_mismatches() == []


def test_every_captured_result_matches_without_tolerance() -> None:
    """Integer powers are computed exactly, so even 9^17 and 1e21^10 match Java bit for bit."""
    assert GOLDEN.tolerated() == []


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RawSession]:
    log = tmp_path_factory.mktemp("logs") / "server.log"
    command = [sys.executable, "-m", "simple_mcp_calculator.calculator_server"]
    with RawSession([*command, f"--logging.file.name={log}"]) as session:
        yield session
        assert session.close() == ""


def test_initialize_matches_java(server: RawSession) -> None:
    assert server.initialize_result == GOLDEN.meta["initialize"]


def test_tools_list_matches_java_except_read_only_annotations(server: RawSession) -> None:
    assert server.request("tools/list")["result"] == GOLDEN.listing_with_read_only_annotations()


def test_sample_over_stdio_matches_java(server: RawSession) -> None:
    """Every 20th captured call plus the last of the one-operand and error cases (under the
    default burst of 400 calls)."""
    others = [c for c in GOLDEN.cases if c["tool"] not in {"add", "subtract", "multiply"}]
    sample = GOLDEN.cases[::20] + others[-25:]
    assert len(sample) < 400  # inside the default burst, so no call is rate-limited
    assert GOLDEN.stdio_mismatches(server, sample) == []
