"""The Python clients against the Java servers (local only).

Set SIMPLE_MCP_CALCULATOR_JAVA to a built SimpleMCPCalculator checkout (``./mvnw package``) to
run these; without it, or without a JDK, they are skipped, as in CI. They show the Python
clients and the Java servers interoperate, which the golden tests show only one side at a time.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = os.environ.get("SIMPLE_MCP_CALCULATOR_JAVA")
JAVA_ROOT = Path(_ROOT) if _ROOT else None
CALCULATOR_JAR = "calculator-mcp-server/target/calculator-mcp-server.jar"
SCIENTIFIC_JAR = (
    "ScientificCalculatorMCP/scientific-calculator-mcp-server/target/"
    "scientific-calculator-mcp-server.jar"
)


def _jar(relative: str) -> Path:
    if shutil.which("java") is None:
        pytest.skip("needs a JDK")
    if JAVA_ROOT is None:
        pytest.skip("set SIMPLE_MCP_CALCULATOR_JAVA to a built Java checkout")
    jar = JAVA_ROOT / relative
    if not jar.exists():
        pytest.skip(f"Java server jar not built: {jar}")
    return jar


def _client(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed test command
        [sys.executable, "-m", f"simple_mcp_calculator.{module}", *args],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "stdout", "status"),
    [
        (("add", "7", "5"), "12.0\n", 0),
        (("divide", "1", "0"), "Error: Division by zero\n", 1),
        (("factorial", "2.5"), "Error: Not a whole number: 2.5\n", 1),
        (("cube_root", "8", "1"), "Error: Unknown tool: invalid_tool_name\n", 1),
    ],
)
def test_python_calculator_client_with_the_java_server(
    args: tuple[str, ...], stdout: str, status: int
) -> None:
    jar = _jar(CALCULATOR_JAR)
    done = _client("calculator_client", f"--calculator.server.jar={jar}", *args)
    assert (done.stdout, done.returncode) == (stdout, status), done.stderr


def test_python_scientific_client_with_the_java_server() -> None:
    jar = _jar(SCIENTIFIC_JAR)
    done = _client("scientific_client", f"--scientific.server.jar={jar}", "log", "1024", "2")
    assert (done.stdout, done.returncode) == ("10.0\n", 0), done.stderr


def test_python_router_with_both_java_servers() -> None:
    calculator, scientific = _jar(CALCULATOR_JAR), _jar(SCIENTIFIC_JAR)
    options = (f"--calculator.server.jar={calculator}", f"--scientific.server.jar={scientific}")
    assert _client("router", *options, "isPrime", "97").stdout == "true\n"
    assert _client("router", *options, "sqrt", "2").stdout == "1.4142135623730951\n"


def test_python_router_mixing_a_python_and_a_java_server() -> None:
    scientific = _jar(SCIENTIFIC_JAR)
    done = _client("router", f"--scientific.server.jar={scientific}", "log", "1000", "10")
    assert (done.stdout, done.returncode) == ("3.0\n", 0), done.stderr
