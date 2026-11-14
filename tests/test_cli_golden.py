"""The Python command-line clients against the Java clients' captured output.

``tests/golden/cli.json`` was recorded from the Java client jars (commit 6794f98) by
``tests/golden/capture_cli.py``: each run's arguments, stdout, stderr and exit code. Each Python
client must print the same stdout and exit with the same code. Stderr matches too, except that
the usage line names the Python command instead of ``java -jar <client>.jar``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

GOLDEN = json.loads((Path(__file__).parent / "golden" / "cli.json").read_text())

MODULES = {
    "calculator-mcp-client": "simple_mcp_calculator.calculator_client",
    "scientific-calculator-mcp-client": "simple_mcp_calculator.scientific_client",
    "calculator-router-client": "simple_mcp_calculator.router",
}


def _cases(client: str) -> list[dict[str, Any]]:
    return [c for c in GOLDEN if c["client"] == client and not c.get("hung")]


def _python_stderr(client: str, java_stderr: str) -> str:
    return java_stderr.replace(f"java -jar {client}.jar", client)


def _run(client: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed test command
        [sys.executable, "-m", MODULES[client], *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, "PYTHONWARNINGS": "ignore"},
    )


def _check(client: str, case: dict[str, Any]) -> None:
    done = _run(client, case["args"])
    assert (done.stdout, done.returncode) == (case["stdout"], case["exit"])
    assert done.stderr == _python_stderr(client, case["stderr"])


def _ids(cases: list[dict[str, Any]]) -> list[str]:
    return [" ".join(c["args"]) or "(demo)" for c in cases]


CALCULATOR = _cases("calculator-mcp-client")
SCIENTIFIC = _cases("scientific-calculator-mcp-client")
ROUTER = _cases("calculator-router-client")


@pytest.mark.parametrize("case", CALCULATOR, ids=_ids(CALCULATOR))
def test_calculator_client_matches_java(case: dict[str, Any]) -> None:
    _check("calculator-mcp-client", case)


@pytest.mark.parametrize("case", SCIENTIFIC, ids=_ids(SCIENTIFIC))
def test_scientific_client_matches_java(case: dict[str, Any]) -> None:
    _check("scientific-calculator-mcp-client", case)


@pytest.mark.parametrize("case", ROUTER, ids=_ids(ROUTER))
def test_router_client_matches_java(case: dict[str, Any]) -> None:
    _check("calculator-router-client", case)


def test_golden_file_covers_both_clients() -> None:
    assert len(CALCULATOR) > 30
    assert len(SCIENTIFIC) > 20
    assert len(ROUTER) > 25


# Observed on the Java client jars after cli.json was captured (independent review of #8):
# Spring ends option parsing at a bare "--", and Java parses an oversized hex float as
# Infinity, which the client then sends as the string "Infinity".
_ADD_INFINITY = (
    "Error: Tool (add) input validation failed: Validation failed: "
    "JSON schema validation errors: [/a: string found, number expected]\n"
)
_SCIENTIFIC_USAGE = next(c["stderr"] for c in SCIENTIFIC if c["args"] == ["sqrt", "abc"])
OBSERVED = [
    ("calculator-mcp-client", ["add", "7", "5", "--"], "12.0\n", "", 0),
    ("calculator-mcp-client", ["add", "--", "7", "5"], "12.0\n", "", 0),
    ("calculator-mcp-client", ["add", "0x1p2000", "1"], _ADD_INFINITY, "", 1),
    ("scientific-calculator-mcp-client", ["sqrt", "4", "--"], "2.0\n", "", 0),
    ("scientific-calculator-mcp-client", ["log", "--", "8", "2"], "3.0\n", "", 0),
    ("scientific-calculator-mcp-client", ["sqrt", "0x1p2000"], "", _SCIENTIFIC_USAGE, 1),
]


@pytest.mark.parametrize(
    ("client", "args", "stdout", "java_stderr", "status"),
    OBSERVED,
    ids=[" ".join(o[1]) for o in OBSERVED],
)
def test_matches_java_runs_observed_after_capture(
    client: str, args: list[str], stdout: str, java_stderr: str, status: int
) -> None:
    _check(client, {"args": args, "stdout": stdout, "stderr": java_stderr, "exit": status})


def test_an_option_without_a_name_fails_like_spring() -> None:
    """Java: Spring reports "Invalid argument syntax: --=x" and exits 1."""
    done = _run("calculator-mcp-client", ["--=x", "add", "1", "2"])
    assert (done.returncode, done.stdout) == (1, "")
    assert "Invalid argument syntax: --=x" in done.stderr
