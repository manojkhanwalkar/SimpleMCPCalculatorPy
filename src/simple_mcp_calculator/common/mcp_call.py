"""Client side of the calculators: start a server over stdio and call its tools.

Ports what the three Java clients share: Spring-style ``--name=value`` options mixed with
positional arguments, the server command each connection launches, and turning a
``tools/call`` into the text the command line prints (``Error: <first line>`` on failure).
"""

import math
import os
import shlex
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from simple_mcp_calculator.common.javafmt import java_double_str

REQUEST_TIMEOUT_SECONDS = 20.0
"""Spring AI's default MCP client request timeout."""


@dataclass(frozen=True, slots=True)
class Arguments:
    """A command line split as Spring Boot splits it: ``--name=value`` options anywhere, the
    rest positional."""

    positional: list[str]
    options: dict[str, str]

    @classmethod
    def parse(cls, argv: Sequence[str]) -> Arguments:
        positional: list[str] = []
        options: dict[str, str] = {}
        for arg in argv:
            if arg.startswith("--") and len(arg) > 2:
                name, _, value = arg[2:].partition("=")
                options[name] = value
            else:
                positional.append(arg)
        return cls(positional, options)


@dataclass(frozen=True, slots=True)
class ServerCommand:
    """How a client starts one server.

    Default: the Python server module, run by this interpreter. ``--<name>.server.jar=<jar>``
    runs a Java server jar (the Java clients' option); ``--<name>.server.command=<command>``
    runs any command (split like a shell would, never run through one).
    """

    command: str
    args: tuple[str, ...]

    @classmethod
    def resolve(cls, name: str, default_module: str, options: dict[str, str]) -> ServerCommand:
        """Raises ``ValueError`` for a ``--<name>.server.command=`` that names no program."""
        if (command := options.get(f"{name}.server.command")) is not None:
            words = shlex.split(command)
            if not words:
                raise ValueError(f"--{name}.server.command= names no command")
            return cls(words[0], tuple(words[1:]))
        if jar := options.get(f"{name}.server.jar"):
            return cls("java", ("-jar", jar))
        return cls(sys.executable, ("-m", default_module))


def jackson_number(x: float) -> float | str:
    """A double as Jackson writes it into JSON: non-finite values become the strings ``"NaN"``,
    ``"Infinity"`` and ``"-Infinity"`` (which a server then rejects as the wrong type)."""
    return x if math.isfinite(x) else java_double_str(x)


def _first_line(text: str) -> str:
    return text.splitlines()[0] if text else ""


def result_text(result: types.CallToolResult) -> str:
    """The text a Java client prints for a tool result."""
    text = "\n".join(c.text for c in result.content if isinstance(c, types.TextContent))
    return f"Error: {_first_line(text)}" if result.is_error else text


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
            return f"Error: {_first_line(str(e)) or type(e).__name__}"
        if not isinstance(result, types.CallToolResult):  # pragma: no cover - other result kinds
            return "Error: Unexpected result"
        return result_text(result)


@asynccontextmanager
async def connect(*servers: ServerCommand) -> AsyncIterator[list[Connection]]:
    """Start each server, initialize a session with it, and close them all on exit (which
    stops the server processes). The servers' stderr is discarded, as the Java clients log it
    below their WARN threshold."""
    async with AsyncExitStack() as stack:
        # Opening /dev/null never blocks.
        errlog = stack.enter_context(open(os.devnull, "w"))  # noqa: SIM115, ASYNC230
        connections = []
        for server in servers:
            params = StdioServerParameters(command=server.command, args=list(server.args))
            read, write = await stack.enter_async_context(stdio_client(params, errlog=errlog))
            session = await stack.enter_async_context(
                ClientSession(read, write, read_timeout_seconds=REQUEST_TIMEOUT_SECONDS)
            )
            init = await session.initialize()
            connections.append(Connection(session, init.server_info.name))
        yield connections


def _leaf(error: BaseException) -> BaseException:
    """The first underlying error inside (nested) exception groups."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def run_client(run: Callable[[Sequence[str]], Awaitable[int]], argv: Sequence[str]) -> int:
    """Run a client's ``run(argv)`` and return its exit status. A server that can't be started
    or reached is reported on stderr with status 1 instead of a traceback, as the Java clients
    report a failed start."""
    try:
        return anyio.run(run, argv)
    except Exception as e:
        cause = _leaf(e)
        print(
            f"Error: Cannot start the server: {_first_line(str(cause)) or type(cause).__name__}",
            file=sys.stderr,
        )
        return 1
