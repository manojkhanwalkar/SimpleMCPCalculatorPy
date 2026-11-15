"""The Python port and the Java project, talking to each other (local only).

Set SIMPLE_MCP_CALCULATOR_JAVA to a built SimpleMCPCalculator checkout (``./mvnw package``) to
run these; without it, without a JDK, or without the jars, they are skipped, as in CI.

Python clients run against the Java server jars, and the Java client jars against the Python
servers (configured through Spring properties), so each side is shown to interoperate with the
other's real implementation, not just with captured responses.

Each run gets its own process group and is killed with it on timeout: a Java client can hang
after a failed start, with its server JVM still holding the pipes.
"""

import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

_ROOT = os.environ.get("SIMPLE_MCP_CALCULATOR_JAVA")
JAVA_ROOT = Path(_ROOT) if _ROOT else None

CALCULATOR_SERVER = "calculator-mcp-server/target/calculator-mcp-server.jar"
SCIENTIFIC_SERVER = (
    "ScientificCalculatorMCP/scientific-calculator-mcp-server/target/"
    "scientific-calculator-mcp-server.jar"
)
CALCULATOR_CLIENT = "calculator-mcp-client/target/calculator-mcp-client.jar"
SCIENTIFIC_CLIENT = (
    "ScientificCalculatorMCP/scientific-calculator-mcp-client/target/"
    "scientific-calculator-mcp-client.jar"
)
ROUTER_CLIENT = "calculator-router-client/target/calculator-router-client.jar"

RUN_TIMEOUT = 240
"""Seconds one run may take; the test timeout below is above it."""
pytestmark = pytest.mark.timeout(RUN_TIMEOUT + 60)


def _jar(relative: str) -> Path:
    if shutil.which("java") is None:
        pytest.skip("needs a JDK")
    if JAVA_ROOT is None:
        pytest.skip("set SIMPLE_MCP_CALCULATOR_JAVA to a built Java checkout")
    jar = JAVA_ROOT / relative
    if not jar.exists():
        pytest.skip(f"Java jar not built: {jar}")
    return jar


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run ``command`` in its own process group; on timeout kill the whole group."""
    proc = subprocess.Popen(  # noqa: S603 - fixed test command
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


# --- Python clients, Java servers -------------------------------------------------------------


def _java_server(name: str, relative: str, log_dir: Path) -> str:
    """A ``--<name>.server.command=`` option that runs a Java server jar, logging into
    ``log_dir`` (the JVM takes its home directory from the account, not from HOME)."""
    log = log_dir / f"{name}-java.log"
    return f"--{name}.server.command=java -jar {_jar(relative)} --logging.file.name={log}"


def _python_client(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "-m", f"simple_mcp_calculator.{module}", *args])


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
    tmp_path: Path, args: tuple[str, ...], stdout: str, status: int
) -> None:
    server = _java_server("calculator", CALCULATOR_SERVER, tmp_path)
    done = _python_client("calculator_client", server, *args)
    assert (done.stdout, done.returncode) == (stdout, status), done.stderr


def test_python_scientific_client_with_the_java_server(tmp_path: Path) -> None:
    server = _java_server("scientific", SCIENTIFIC_SERVER, tmp_path)
    done = _python_client("scientific_client", server, "log", "1024", "2")
    assert (done.stdout, done.returncode) == ("10.0\n", 0), done.stderr


def test_python_router_with_both_java_servers(tmp_path: Path) -> None:
    calculator = _java_server("calculator", CALCULATOR_SERVER, tmp_path)
    scientific = _java_server("scientific", SCIENTIFIC_SERVER, tmp_path)
    done = _python_client("router", calculator, scientific, "sqrt", "2")
    assert (done.stdout, done.returncode) == ("1.4142135623730951\n", 0), done.stderr


def test_python_router_mixing_a_python_and_a_java_server(tmp_path: Path) -> None:
    scientific = _java_server("scientific", SCIENTIFIC_SERVER, tmp_path)
    done = _python_client("router", scientific, "isPrime", "97")
    assert (done.stdout, done.returncode) == ("true\n", 0), done.stderr


# --- Java clients, Python servers -------------------------------------------------------------


def _python_server(connection: str, module: str) -> list[str]:
    """Spring properties that make a Java client's ``connection`` start a Python server."""
    prefix = f"--spring.ai.mcp.client.stdio.connections.{connection}"
    return [
        f"{prefix}.command={sys.executable}",
        f"{prefix}.args[0]=-m",
        f"{prefix}.args[1]=simple_mcp_calculator.{module}",
    ]


def _java_client(relative: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["java", "-jar", str(_jar(relative)), *args])


@pytest.mark.parametrize(
    ("args", "stdout", "status"),
    [
        (("add", "7", "5"), "12.0\n", 0),
        (("divide", "1", "0"), "Error: Division by zero\n", 1),
    ],
)
def test_java_calculator_client_with_the_python_server(
    args: tuple[str, ...], stdout: str, status: int
) -> None:
    server = _python_server("calculator", "calculator_server")
    done = _java_client(CALCULATOR_CLIENT, *server, *args)
    assert (done.stdout, done.returncode) == (stdout, status), done.stderr


@pytest.mark.parametrize(
    ("args", "stdout", "status"),
    [
        (("log", "1024", "2"), "10.0\n", 0),
        (("sqrt", "-4"), "Error: Square root of a negative number\n", 1),
    ],
)
def test_java_scientific_client_with_the_python_server(
    args: tuple[str, ...], stdout: str, status: int
) -> None:
    server = _python_server("scientific", "scientific_server")
    done = _java_client(SCIENTIFIC_CLIENT, *server, *args)
    assert (done.stdout, done.returncode) == (stdout, status), done.stderr


@pytest.mark.parametrize(
    ("args", "stdout"), [(("isPrime", "97"), "true\n"), (("log", "1000", "10"), "3.0\n")]
)
def test_java_router_with_both_python_servers(args: tuple[str, ...], stdout: str) -> None:
    servers = [
        *_python_server("calculator", "calculator_server"),
        *_python_server("scientific", "scientific_server"),
    ]
    done = _java_client(ROUTER_CLIENT, *servers, *args)
    assert (done.stdout, done.returncode) == (stdout, 0), done.stderr
