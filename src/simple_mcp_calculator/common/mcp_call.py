"""Client side of the calculators: start a server over stdio and call its tools.

Ports what the three Java clients share: Spring-style ``--name=value`` options mixed with
positional arguments, the server command each connection launches, and turning a
``tools/call`` into the text the command line prints (``Error: <first line>`` on failure).
"""

import math
import os
import re
import shlex
import signal
import sys
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, TextIO

import anyio
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from simple_mcp_calculator.common.javafmt import java_double_str

REQUEST_TIMEOUT_SECONDS = 20.0
"""Spring AI's default MCP client request timeout."""

EXIT_INTERRUPTED = 130
EXIT_TERMINATED = 143

_STDERR_TAIL_BYTES = 4096


@dataclass(frozen=True, slots=True)
class Arguments:
    """A command line split as Spring Boot's ``SimpleCommandLineArgsParser`` splits it:
    ``--name[=value]`` options anywhere, the rest positional; a bare ``--`` ends the options
    (everything after it is positional, even ``--x=y``), and an option with no name
    (``--=x``) is an error."""

    positional: list[str]
    options: dict[str, str]

    @classmethod
    def parse(cls, argv: Sequence[str]) -> Arguments:
        """Raises ``ValueError("Invalid argument syntax: …")`` as Spring does."""
        positional: list[str] = []
        options: dict[str, str] = {}
        end_of_options = False
        for arg in argv:
            if end_of_options:
                positional.append(arg)
            elif arg == "--":
                end_of_options = True
            elif arg.startswith("--"):
                name, _, value = arg[2:].partition("=")
                if not name:
                    raise ValueError(f"Invalid argument syntax: {arg}")
                options[name] = value
            else:
                positional.append(arg)
        return cls(positional, options)


@dataclass(frozen=True, slots=True)
class ServerCommand:
    """How a client starts one server.

    In order of precedence: ``--<name>.server.command=<command>`` runs any command (split like
    a shell would, never run through one); ``--<name>.server.jar=<jar>`` or the
    ``<NAME>_SERVER_JAR`` environment variable runs a Java server jar (the Java clients' option,
    with Spring's relaxed binding); otherwise the Python server module, run by this interpreter.
    """

    command: str
    args: tuple[str, ...]

    @classmethod
    def resolve(
        cls,
        name: str,
        default_module: str,
        options: Mapping[str, str],
        env: Mapping[str, str] = os.environ,
    ) -> ServerCommand:
        """Raises ``ValueError`` for a ``--<name>.server.command=`` that names no program."""
        if (command := options.get(f"{name}.server.command")) is not None:
            words = shlex.split(command)
            if not words:
                raise ValueError(f"--{name}.server.command= names no command")
            return cls(words[0], tuple(words[1:]))
        if jar := options.get(f"{name}.server.jar") or env.get(f"{name.upper()}_SERVER_JAR"):
            return cls("java", ("-jar", jar))
        return cls(sys.executable, ("-m", default_module))


def jackson_number(x: float) -> float | str:
    """A double as Jackson writes it into JSON: non-finite values become the strings ``"NaN"``,
    ``"Infinity"`` and ``"-Infinity"`` (which a server then rejects as the wrong type)."""
    return x if math.isfinite(x) else java_double_str(x)


_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def first_line(text: str) -> str:
    """Java's ``text.lines().findFirst().orElse("")``: lines end only at \\n, \\r or \\r\\n
    (unlike ``str.splitlines``, which also splits at \\v, \\f, \\x1c-\\x1e, \\x85, ...)."""
    return _LINE_BREAK.split(text, maxsplit=1)[0]


def error_line(error: BaseException) -> str:
    """``Error: <first line of the message>``; an exception with no message is named by its
    type, as Java names one whose message is null."""
    message = str(error)
    return f"Error: {first_line(message) if message else type(error).__name__}"


def result_text(result: types.CallToolResult) -> str:
    """The text a Java client prints for a tool result."""
    text = "\n".join(c.text for c in result.content if isinstance(c, types.TextContent))
    return f"Error: {first_line(text)}" if result.is_error else text


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def terminal_safe(text: str, stream: TextIO) -> str:
    """Text from a server, made safe to print: on a terminal, control characters other than
    newline and tab (which could move the cursor or rewrite the screen) become U+FFFD. Output
    to a file or pipe is left byte-for-byte as Java prints it."""
    return _CONTROL.sub("\N{REPLACEMENT CHARACTER}", text) if stream.isatty() else text


def emit(text: str, stream: TextIO | None = None) -> None:
    """Print a line that may contain server text (see ``terminal_safe``)."""
    out = sys.stdout if stream is None else stream
    print(terminal_safe(text, out), file=out)


@dataclass
class Connection:
    """An initialized MCP session with one server."""

    session: ClientSession
    server_name: str

    async def list_tools(self) -> list[types.Tool]:
        return (await self.session.list_tools()).tools

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool and return its text, or ``Error: <message>`` if the tool reported an
        error or the request failed (an unknown tool, a timeout or a dead server)."""
        try:
            result = await self.session.call_tool(name, arguments)
        except Exception as e:
            return error_line(e)
        if not isinstance(result, types.CallToolResult):  # pragma: no cover - other result kinds
            return "Error: Unexpected result"
        return result_text(result)


class ServerStartError(Exception):
    """A server could not be started or did not complete the MCP handshake."""


class StderrTail:
    """A server's stderr, of which only the last few kilobytes are kept (to explain a failed
    start without letting a chatty server use unbounded memory)."""

    def __init__(self, limit: int = _STDERR_TAIL_BYTES) -> None:
        read_fd, write_fd = os.pipe()
        self.writer: TextIO = os.fdopen(write_fd, "w")
        self._read_fd = read_fd
        self._limit = limit
        self._tail = bytearray()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        while chunk := os.read(self._read_fd, 65536):
            with self._lock:
                self._tail += chunk
                del self._tail[: -self._limit]
        os.close(self._read_fd)

    def close(self, wait: float = 1.0) -> None:
        """Stop writing; give the reader up to ``wait`` seconds to see the server's last words."""
        if not self.writer.closed:
            self.writer.close()
        self._thread.join(wait)

    def last_line(self) -> str:
        with self._lock:
            text = self._tail.decode("utf-8", "replace")
        lines = [line.strip() for line in _LINE_BREAK.split(text) if line.strip()]
        return lines[-1] if lines else ""


@asynccontextmanager
async def connect(*servers: ServerCommand) -> AsyncIterator[list[Connection]]:
    """Start each server, initialize a session with it, and close them all on exit (which
    stops the server processes). A failure to start or initialize is a ``ServerStartError``
    carrying the server's last stderr line, if it wrote one."""
    async with AsyncExitStack() as stack:
        connections = []
        for server in servers:
            tail = StderrTail()
            stack.callback(tail.close)
            try:
                params = StdioServerParameters(command=server.command, args=list(server.args))
                read, write = await stack.enter_async_context(
                    stdio_client(params, errlog=tail.writer)
                )
                session = await stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=REQUEST_TIMEOUT_SECONDS)
                )
                init = await session.initialize()
            except Exception as e:
                tail.close()
                cause = _leaf(e)
                reason = first_line(str(cause)) or type(cause).__name__
                if detail := tail.last_line():
                    reason = f"{reason} ({detail})"
                raise ServerStartError(f"{server.command}: {reason}") from e
            connections.append(Connection(session, init.server_info.name))
        yield connections


def _leaf(error: BaseException) -> BaseException:
    """The first underlying error inside (nested) exception groups."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def _find(error: BaseException, kind: type[BaseException]) -> BaseException | None:
    """The first ``kind`` error in ``error`` or (nested) inside its exception groups."""
    if isinstance(error, kind):
        return error
    if isinstance(error, BaseExceptionGroup):
        for inner in error.exceptions:
            if (found := _find(inner, kind)) is not None:
                return found
    return None


async def _until_terminated(cancel: anyio.CancelScope, terminated: list[bool]) -> None:
    with anyio.open_signal_receiver(signal.SIGTERM) as signals:
        async for _ in signals:
            terminated.append(True)
            cancel.cancel()
            return


async def _supervised(run: Callable[[Sequence[str]], Awaitable[int]], argv: Sequence[str]) -> int:
    """``run(argv)``, cancelled cleanly on SIGTERM so the servers are still shut down (the SDK
    starts each in its own session, so they would otherwise be orphaned)."""
    terminated: list[bool] = []
    status = EXIT_TERMINATED
    async with anyio.create_task_group() as group:
        group.start_soon(_until_terminated, group.cancel_scope, terminated)
        status = await run(argv)
        group.cancel_scope.cancel()
    return EXIT_TERMINATED if terminated else status


def run_client(run: Callable[[Sequence[str]], Awaitable[int]], argv: Sequence[str]) -> int:
    """Run a client's ``run(argv)`` and return its exit status. Failures become one line on
    stderr and status 1 instead of a traceback: ``Error: Cannot start the server: …`` when a
    server can't be started or reached, else ``Error: <message>``. Ctrl+C exits 130 and SIGTERM
    143, after the servers are shut down."""
    try:
        return anyio.run(_supervised, run, argv)
    except BaseException as e:
        # Errors raised inside the task group arrive wrapped in exception groups.
        if _find(e, KeyboardInterrupt) is not None:
            return EXIT_INTERRUPTED
        if (requested := _find(e, SystemExit)) is not None:
            raise requested from None
        if not isinstance(e, Exception):
            raise
        if (start := _find(e, ServerStartError)) is not None:
            print(f"Error: Cannot start the server: {start}", file=sys.stderr)
        else:
            print(error_line(_leaf(e)), file=sys.stderr)
        return 1
