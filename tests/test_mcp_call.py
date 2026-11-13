"""Client plumbing shared by the three command-line clients."""

import math
import subprocess
import sys

import pytest
from mcp import types

from simple_mcp_calculator.common.mcp_call import (
    Arguments,
    Connection,
    ServerCommand,
    connect,
    jackson_number,
    result_text,
)


def test_spring_style_options_mix_with_positional_arguments() -> None:
    args = Arguments.parse(["add", "--calculator.server.jar=/x.jar", "7", "-5", "--flag", "--"])
    assert args.positional == ["add", "7", "-5", "--"]
    assert args.options == {"calculator.server.jar": "/x.jar", "flag": ""}


def test_server_command_defaults_to_this_interpreter() -> None:
    command = ServerCommand.resolve("calculator", "pkg.server", {})
    assert command == ServerCommand(sys.executable, ("-m", "pkg.server"))


def test_server_command_runs_a_java_jar() -> None:
    command = ServerCommand.resolve("calculator", "pkg", {"calculator.server.jar": "/a b/s.jar"})
    assert command == ServerCommand("java", ("-jar", "/a b/s.jar"))


def test_server_command_is_split_like_a_shell_but_never_run_by_one() -> None:
    options = {"calculator.server.command": "'my server' --opt 'a b' ; rm -rf /"}
    command = ServerCommand.resolve("calculator", "pkg", options)
    assert command == ServerCommand("my server", ("--opt", "a b", ";", "rm", "-rf", "/"))


def test_command_option_wins_over_jar() -> None:
    options = {"calculator.server.jar": "/s.jar", "calculator.server.command": "srv"}
    assert ServerCommand.resolve("calculator", "pkg", options).command == "srv"


def _result(texts: list[str], *, error: bool) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=t) for t in texts], is_error=error
    )


def test_result_text() -> None:
    assert result_text(_result(["22.0"], error=False)) == "22.0"
    assert result_text(_result(["a", "b"], error=False)) == "a\nb"
    assert result_text(_result(["Division by zero\nDivision by zero"], error=True)) == (
        "Error: Division by zero"
    )
    assert result_text(_result([], error=True)) == "Error: "


async def test_calls_against_a_real_server() -> None:
    server = ServerCommand.resolve("calculator", "simple_mcp_calculator.calculator_server", {})
    async with connect(server) as (connection,):
        assert connection.server_name == "calculator-mcp-server"
        assert await connection.call("add", {"a": 17, "b": 5}) == "22.0"
        assert await connection.call("divide", {"a": 1, "b": 0}) == "Error: Division by zero"
        # An unknown tool is a JSON-RPC error, which becomes an error line instead of raising.
        assert await connection.call("cube_root", {"x": 8}) == (
            "Error: Unknown tool: invalid_tool_name"
        )


async def test_a_server_that_cannot_start_fails_to_connect() -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011 - the SDK's error type is not part of the contract
        async with connect(ServerCommand(sys.executable, ("-c", "import sys; sys.exit(3)"))):
            pass


class _Failing:
    async def call_tool(self, name: str, arguments: dict[str, object]) -> types.CallToolResult:
        raise TimeoutError


async def test_transport_failure_without_a_message_names_the_exception() -> None:
    connection = Connection(_Failing(), "s")  # type: ignore[arg-type]
    assert await connection.call("add", {}) == "Error: TimeoutError"


def test_non_finite_numbers_are_sent_as_jackson_writes_them() -> None:
    assert jackson_number(2.5) == 2.5
    assert jackson_number(math.nan) == "NaN"
    assert jackson_number(math.inf) == "Infinity"
    assert jackson_number(-math.inf) == "-Infinity"


def test_an_empty_server_command_is_rejected() -> None:
    with pytest.raises(ValueError, match="names no command"):
        ServerCommand.resolve("calculator", "pkg", {"calculator.server.command": "  "})


@pytest.mark.parametrize(
    ("option", "message"),
    [
        (f"--calculator.server.command={sys.executable} -c 'raise SystemExit(3)'", ""),
        ("--calculator.server.command=/no/such/server", "No such file"),
        ("--calculator.server.command='unbalanced", "No closing quotation"),
        ("--calculator.server.command=", "names no command"),
    ],
)
def test_a_server_that_cannot_start_is_one_error_line_and_status_1(
    option: str, message: str
) -> None:
    done = subprocess.run(  # noqa: S603 - fixed test command
        [sys.executable, "-m", "simple_mcp_calculator.calculator_client", option, "add", "1", "2"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout == ""
    assert done.stderr.startswith("Error: Cannot start the server: ")
    assert message in done.stderr
    assert "Traceback" not in done.stderr
