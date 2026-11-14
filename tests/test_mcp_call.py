"""Client plumbing shared by the three command-line clients."""

import io
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pytest
from mcp import types

from simple_mcp_calculator.common.mcp_call import (
    EXIT_INTERRUPTED,
    EXIT_TERMINATED,
    Arguments,
    Connection,
    ServerCommand,
    StderrTail,
    connect,
    emit,
    error_line,
    first_line,
    jackson_number,
    result_text,
    run_client,
    terminal_safe,
)


def test_spring_style_options_mix_with_positional_arguments() -> None:
    args = Arguments.parse(["add", "--calculator.server.jar=/x.jar", "7", "-5", "--flag"])
    assert args.positional == ["add", "7", "-5"]
    assert args.options == {"calculator.server.jar": "/x.jar", "flag": ""}


@pytest.mark.parametrize(
    ("argv", "positional", "options"),
    [
        (["add", "7", "5", "--"], ["add", "7", "5"], {}),
        (["add", "--", "7", "5"], ["add", "7", "5"], {}),
        (["--a=1", "--", "--b=2", "--", "x"], ["--b=2", "--", "x"], {"a": "1"}),
    ],
)
def test_a_bare_double_dash_ends_the_options_as_in_spring(
    argv: list[str], positional: list[str], options: dict[str, str]
) -> None:
    """Spring's SimpleCommandLineArgsParser drops the ``--`` and treats the rest as
    positional, even ``--x=y``."""
    args = Arguments.parse(argv)
    assert (args.positional, args.options) == (positional, options)


def test_an_option_without_a_name_is_invalid_as_in_spring() -> None:
    with pytest.raises(ValueError, match=r"^Invalid argument syntax: --=x$"):
        Arguments.parse(["--=x", "add", "1", "2"])


def test_the_jar_can_come_from_the_environment_as_with_spring_relaxed_binding() -> None:
    env = {"CALCULATOR_SERVER_JAR": "/env/s.jar"}
    assert ServerCommand.resolve("calculator", "pkg", {}, env) == ServerCommand(
        "java", ("-jar", "/env/s.jar")
    )
    options = {"calculator.server.jar": "/opt/s.jar"}
    assert ServerCommand.resolve("calculator", "pkg", options, env).args == ("-jar", "/opt/s.jar")


def test_first_line_breaks_only_where_java_does() -> None:
    assert first_line("a\x0bb\x0cc\x85d\u2028e\nf") == "a\x0bb\x0cc\x85d\u2028e"
    assert first_line("a\r\nb") == "a"
    assert first_line("a\rb") == "a"
    assert first_line("") == ""
    assert first_line("\nsecond") == ""


def test_error_line_names_a_message_less_exception_by_type() -> None:
    assert error_line(RuntimeError("bad\nmore")) == "Error: bad"
    assert error_line(RuntimeError("\nmore")) == "Error: "
    assert error_line(TimeoutError()) == "Error: TimeoutError"


class _Stream(io.StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_control_characters_are_neutralised_only_on_a_terminal() -> None:
    text = "ok\x1b[2J\x07\x9b\tend\n"
    assert terminal_safe(text, _Stream(tty=False)) == text
    assert terminal_safe(text, _Stream(tty=True)) == "ok\ufffd[2J\ufffd\ufffd\tend\n"
    out = _Stream(tty=True)
    emit("x\x1by", out)
    assert out.getvalue() == "x\ufffdy\n"


def test_stderr_tail_keeps_only_the_end() -> None:
    tail = StderrTail(limit=16)
    tail.writer.write("early line\n" + "x" * 100 + "\nlast words\n")
    tail.writer.flush()
    tail.close()
    assert tail.last_line() == "last words"
    assert StderrTail().last_line() == ""


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


def _client(*args: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed test command
        [sys.executable, "-m", "simple_mcp_calculator.calculator_client", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.mark.parametrize(
    ("option", "detail"),
    [
        (f"--calculator.server.command={sys.executable} -c 'raise SystemExit(3)'", ""),
        ("--calculator.server.command=/no/such/server", "No such file"),
        (
            f"--calculator.server.command={sys.executable} -c "
            "'import sys; sys.stderr.write(\"boom: bad config\\n\"); sys.exit(2)'",
            "(boom: bad config)",
        ),
    ],
)
def test_a_server_that_cannot_start_is_one_error_line_and_status_1(
    option: str, detail: str
) -> None:
    done = _client(option, "add", "1", "2")
    assert done.returncode == 1
    assert done.stdout == ""
    assert done.stderr.startswith("Error: Cannot start the server: ")
    assert detail in done.stderr
    assert "Traceback" not in done.stderr


@pytest.mark.skipif(shutil.which("java") is None, reason="needs a JDK")
def test_a_missing_jar_says_why() -> None:
    done = _client("--calculator.server.jar=/no/such.jar", "add", "1", "2")
    assert done.returncode == 1
    assert "Error: Cannot start the server: java: " in done.stderr
    assert "/no/such.jar" in done.stderr


@pytest.mark.parametrize(
    ("args", "stderr"),
    [
        (
            ("--calculator.server.command='unbalanced", "add", "1", "2"),
            "Error: No closing quotation\n",
        ),
        (
            ("--calculator.server.command=", "add", "1", "2"),
            "Error: --calculator.server.command= names no command\n",
        ),
        (("--=x", "add", "1", "2"), "Error: Invalid argument syntax: --=x\n"),
    ],
)
def test_other_failures_are_plain_error_lines(args: Sequence[str], stderr: str) -> None:
    done = _client(*args)
    assert (done.returncode, done.stdout, done.stderr) == (1, "", stderr)


def test_ctrl_c_exits_130_quietly() -> None:
    async def interrupted(_argv: Sequence[str]) -> int:
        raise KeyboardInterrupt

    assert run_client(interrupted, []) == EXIT_INTERRUPTED


def test_an_unexpected_failure_is_not_blamed_on_the_server(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def broken(_argv: Sequence[str]) -> int:
        raise RuntimeError("boom\ndetails")

    assert run_client(broken, []) == 1
    assert capsys.readouterr().err == "Error: boom\n"


@pytest.mark.parametrize(
    ("sig", "status"), [(signal.SIGTERM, EXIT_TERMINATED), (signal.SIGINT, EXIT_INTERRUPTED)]
)
def test_a_signal_shuts_the_server_down_too(
    tmp_path: Path, sig: signal.Signals, status: int
) -> None:
    """The SDK starts each server in its own session, so a signal to the client never reaches
    it; the client must cancel cleanly and stop the (here hung) server itself."""
    pid_file = tmp_path / "server.pid"
    server = Path(__file__).with_name("hanging_server.py")
    client = subprocess.Popen(  # noqa: S603 - fixed test command
        [
            sys.executable, "-m", "simple_mcp_calculator.calculator_client",
            f"--calculator.server.command={sys.executable} {server} {pid_file}",
            "add", "1", "2",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )  # fmt: skip
    deadline = time.monotonic() + 30
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    server_pid = int(pid_file.read_text())
    client.send_signal(sig)
    _, stderr = client.communicate(timeout=30)
    assert client.returncode == status, stderr
    assert "Traceback" not in stderr
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(server_pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    os.kill(server_pid, signal.SIGKILL)
    pytest.fail("the server outlived the client")


def test_a_requested_exit_is_not_turned_into_an_error() -> None:
    async def exits(_argv: Sequence[str]) -> int:
        raise SystemExit(5)

    with pytest.raises(SystemExit) as exit_info:
        run_client(exits, [])
    assert exit_info.value.code == 5


class _Abort(BaseException):
    pass


def test_other_base_exceptions_propagate() -> None:
    async def aborts(_argv: Sequence[str]) -> int:
        raise _Abort

    with pytest.raises(BaseException) as raised:  # noqa: PT011 - wrapped in a group by anyio
        run_client(aborts, [])
    assert _find_abort(raised.value)


def _find_abort(error: BaseException) -> bool:
    if isinstance(error, _Abort):
        return True
    return isinstance(error, BaseExceptionGroup) and any(map(_find_abort, error.exceptions))
