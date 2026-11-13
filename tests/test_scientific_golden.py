"""The Python scientific server against responses captured from the Java server (6794f98).

Errors, listing and initialize must match exactly. Numeric results of ``ln``, ``log10`` and
``log`` may differ by an ulp or two: HotSpot's ``Math.log``/``Math.log10`` intrinsics round
differently from the C library on some non-round inputs (2,000,000 doubles measured: ``log10``
up to 2 ulps, ``ln`` up to 1). ``sqrt`` is exact.
"""

from collections.abc import Iterator

import pytest

from simple_mcp_calculator.scientific_server.tools import SPEC
from tests.golden_support import Golden, server_session
from tests.rpc import RawSession

GOLDEN = Golden(SPEC, ulp_limits={"ln": 1, "log10": 2, "log": 2})


def test_golden_file_is_complete() -> None:
    assert len(GOLDEN.cases) > 2000
    assert {c["tool"] for c in GOLDEN.cases} >= {t.name for t in SPEC.tools}


def test_every_captured_call_matches_java() -> None:
    assert GOLDEN.in_process_mismatches() == []


def test_only_the_logarithms_need_the_tolerance() -> None:
    tolerated = GOLDEN.tolerated()
    assert {c["tool"] for c in tolerated} <= {"ln", "log10", "log"}
    assert len(tolerated) < len(GOLDEN.cases) // 10


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RawSession]:
    with server_session(
        "simple_mcp_calculator.scientific_server", tmp_path_factory.mktemp("logs")
    ) as session:
        yield session


def test_initialize_matches_java(server: RawSession) -> None:
    assert server.initialize_result == GOLDEN.meta["initialize"]


def test_tools_list_matches_java(server: RawSession) -> None:
    assert server.request("tools/list")["result"] == GOLDEN.meta["tools"]


def test_sample_over_stdio_matches_java(server: RawSession) -> None:
    """All calls would exceed the default burst of 400, so send every sixth one."""
    sample = GOLDEN.cases[::6]
    assert len(sample) < 400
    assert GOLDEN.stdio_mismatches(server, sample) == []
