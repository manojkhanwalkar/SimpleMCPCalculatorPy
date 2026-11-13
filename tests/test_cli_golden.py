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


@pytest.mark.parametrize("case", CALCULATOR, ids=_ids(CALCULATOR))
def test_calculator_client_matches_java(case: dict[str, Any]) -> None:
    _check("calculator-mcp-client", case)


@pytest.mark.parametrize("case", SCIENTIFIC, ids=_ids(SCIENTIFIC))
def test_scientific_client_matches_java(case: dict[str, Any]) -> None:
    _check("scientific-calculator-mcp-client", case)


def test_golden_file_covers_both_clients() -> None:
    assert len(CALCULATOR) > 30
    assert len(SCIENTIFIC) > 20
