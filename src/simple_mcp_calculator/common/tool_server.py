"""A stdio MCP server whose wire contract matches the Java (Spring AI) calculator servers.

Spring AI shapes what a client sees: the tool listing (titles, default annotations, draft 2020-12
schemas with ``format: double``), the text of each result (``Double.toString``), the two-line text
of a tool error, the one-line text of a schema-validation error and the JSON-RPC error for an
unknown tool. The high-level ``MCPServer`` changes several of these, so this module builds on the
SDK's low-level ``Server`` and reproduces them explicitly.

It also adds what the Java servers lack: a token bucket and a concurrency cap on tool calls.
"""

import logging
import math
import os
import sys
import threading
import time
import warnings
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import anyio
import anyio.to_thread
from mcp import types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPDeprecationWarning, MCPError

from simple_mcp_calculator.common.javafmt import java_double_str
from simple_mcp_calculator.common.logfile import configure_logging

log = logging.getLogger(__name__)

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

type ToolValue = float | int | bool | str
type Handler = Callable[..., ToolValue]


@dataclass(frozen=True, slots=True)
class Param:
    """A number parameter of a tool (every calculator parameter is a JSON number)."""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class Hints:
    """MCP tool annotations. The defaults are Spring AI's, used when a Java tool sets none."""

    read_only: bool = False
    destructive: bool = True
    idempotent: bool = False
    open_world: bool = True


READ_ONLY = Hints(read_only=True, destructive=False, idempotent=True, open_world=False)


@dataclass(frozen=True, slots=True)
class Tool:
    """One tool: its listing and the function that computes it.

    The handler receives the parameters as floats, in ``params`` order. It signals bad input or
    an undefined result by raising ``ValueError`` or ``ArithmeticError``; the message becomes the
    tool's error text.
    """

    name: str
    description: str
    params: tuple[Param, ...]
    handler: Handler
    hints: Hints = Hints()

    def listing(self) -> types.Tool:
        """The ``tools/list`` entry, shaped as Spring AI writes it."""
        return types.Tool(
            name=self.name,
            title=self.name,
            description=self.description,
            input_schema={
                "$schema": SCHEMA_DIALECT,
                "properties": {
                    p.name: {"description": p.description, "format": "double", "type": "number"}
                    for p in self.params
                },
                "required": [p.name for p in self.params],
                "type": "object",
            },
            annotations=types.ToolAnnotations(
                title="",
                read_only_hint=self.hints.read_only,
                destructive_hint=self.hints.destructive,
                idempotent_hint=self.hints.idempotent,
                open_world_hint=self.hints.open_world,
            ),
        )


@dataclass(frozen=True, slots=True)
class ServerSpec:
    """Identity and tools of one server."""

    name: str
    version: str
    instructions: str
    tools: tuple[Tool, ...]


# --- arguments ------------------------------------------------------------------------------


def _json_kind(value: object) -> str:
    match value:
        case bool():
            return "boolean"
        case str():
            return "string"
        case list() | tuple():
            return "array"
        case dict():
            return "object"
        case _:
            return "unknown"


def validate(tool: Tool, arguments: Mapping[str, Any] | None) -> list[str]:
    """Schema errors in the Java validator's wording and order: wrong types first (in parameter
    order), then missing parameters. ``null`` counts as missing; extra arguments are ignored."""
    args = arguments or {}
    wrong = [
        f"/{p.name}: {_json_kind(args[p.name])} found, number expected"
        for p in tool.params
        if args.get(p.name) is not None
        and (isinstance(args[p.name], bool) or not isinstance(args[p.name], int | float))
    ]
    missing = [
        f": required property '{p.name}' not found" for p in tool.params if args.get(p.name) is None
    ]
    return wrong + missing


def to_double(value: float) -> float:
    """A JSON number as Java's ``double``: integers beyond the double range become infinite."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def format_value(value: ToolValue) -> str:
    """A tool's return value as the text Spring AI puts in the result."""
    match value:
        case bool():
            return "true" if value else "false"
        case int():
            return str(value)
        case float() if math.isfinite(value):
            return java_double_str(value)
        case float():
            # Jackson writes non-finite doubles as JSON strings: "NaN", "Infinity", "-Infinity".
            return f'"{java_double_str(value)}"'
        case _:
            return value


def _text_result(text: str, *, is_error: bool) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], is_error=is_error
    )


def tool_error(message: str) -> types.CallToolResult:
    """A failed tool call. Spring AI repeats the exception message on two lines."""
    return _text_result(f"{message}\n{message}", is_error=True)


# --- limits ---------------------------------------------------------------------------------

# Refilling in float steps can leave 0.999... tokens where exactly 1 is due.
_EPSILON = 1e-9


class Limits:
    """Token bucket (rate) plus a cap on calls in flight. Thread-safe; never blocks or queues."""

    def __init__(
        self,
        rate: float,
        burst: int,
        max_concurrent: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(rate) or rate <= 0 or burst < 1 or max_concurrent < 1:
            raise ValueError("rate must be finite and > 0, burst and max_concurrent >= 1")
        self._rate = rate
        self._burst = float(burst)
        self._max_concurrent = max_concurrent
        self._clock = clock
        self._tokens = float(burst)
        self._stamp = clock()
        self._in_flight = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Limits:
        """Defaults: 200 calls/s, burst 400, 8 in flight; override with CALCULATOR_MCP_RATE,
        CALCULATOR_MCP_BURST and CALCULATOR_MCP_MAX_CONCURRENT. A malformed value is a
        ``ValueError`` that names the setting."""

        def setting[T](name: str, default: str, parse: Callable[[str], T]) -> T:
            text = env.get(name, default)
            try:
                return parse(text)
            except ValueError:
                kind = "a whole number" if parse is int else "a number"
                raise ValueError(f"{name} must be {kind}, got {text!r}") from None

        try:
            return cls(
                rate=setting("CALCULATOR_MCP_RATE", "200", float),
                burst=setting("CALCULATOR_MCP_BURST", "400", int),
                max_concurrent=setting("CALCULATOR_MCP_MAX_CONCURRENT", "8", int),
            )
        except ValueError as e:
            raise ValueError(f"Invalid request limits: {e}") from None

    def try_acquire(self) -> float | None:
        """Take a slot. ``None`` when granted (call ``release`` afterwards); otherwise the seconds
        to wait before retrying."""
        with self._lock:
            now = self._clock()
            self._tokens = min(self._burst, self._tokens + (now - self._stamp) * self._rate)
            self._stamp = now
            if self._in_flight >= self._max_concurrent:
                return 1 / self._rate
            if self._tokens < 1 - _EPSILON:
                return (1 - self._tokens) / self._rate
            self._tokens -= 1
            self._in_flight += 1
            return None

    def release(self) -> None:
        with self._lock:
            self._in_flight -= 1


# --- calls ----------------------------------------------------------------------------------


UNKNOWN_TOOL_MESSAGE = "Unknown tool: invalid_tool_name"


def call_tool(
    tools: Mapping[str, Tool], limits: Limits, name: str, arguments: Mapping[str, Any] | None
) -> types.CallToolResult:
    """Run one ``tools/call`` and return its result, as the Java server would.

    Raises ``MCPError`` (JSON-RPC -32602) for an unknown tool, like Spring AI.
    """
    tool = tools.get(name)
    if tool is None:
        raise MCPError(types.INVALID_PARAMS, UNKNOWN_TOOL_MESSAGE, f"Tool not found: {name}")
    errors = validate(tool, arguments)
    if errors:
        return _text_result(
            f"Tool ({name}) input validation failed: Validation failed: "
            f"JSON schema validation errors: [{', '.join(errors)}]",
            is_error=True,
        )
    retry_after = limits.try_acquire()
    if retry_after is not None:
        log.warning("Rejected %s: over the request limit", name)
        return tool_error(f"Too many requests; retry after {retry_after:.3f} s")
    try:
        args = arguments or {}
        value = tool.handler(*(to_double(args[p.name]) for p in tool.params))
    except (ValueError, ArithmeticError) as e:
        log.debug("%s failed: %s", name, e)
        return tool_error(str(e) or type(e).__name__)
    except Exception:
        # Like Spring AI, an unexpected failure is a tool error, not a broken connection;
        # unlike it, no internal detail reaches the client.
        log.exception("%s raised unexpectedly", name)
        return tool_error("Internal error")
    finally:
        limits.release()
    log.debug("%s -> %r", name, value)
    return _text_result(format_value(value), is_error=False)


def call_handler(
    tools: Mapping[str, Tool], limits: Limits
) -> Callable[[Any, types.CallToolRequestParams], Awaitable[types.CallToolResult]]:
    """The ``tools/call`` handler. Each call runs in a worker thread, so a slow tool never
    blocks pings, cancellations or other requests, and the concurrency cap in ``limits`` bounds
    how many run at once (calls beyond it are rejected, not queued)."""

    async def on_call_tool(_ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        return await anyio.to_thread.run_sync(
            call_tool, tools, limits, params.name, params.arguments
        )

    return on_call_tool


def build_server(spec: ServerSpec, limits: Limits) -> Server[Any]:
    """A low-level MCP server for ``spec``, advertising exactly what the Java server does."""
    tools = tools_by_name(spec.tools)
    listing = types.ListToolsResult(tools=[t.listing() for t in spec.tools])

    async def on_list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
        return listing

    on_call_tool = call_handler(tools, limits)

    async def on_set_logging_level(_ctx: Any, _params: Any) -> types.EmptyResult:
        return types.EmptyResult()

    # The Java servers advertise the logging capability, which MCP has since deprecated; keep
    # advertising it for parity without printing the SDK's warning.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MCPDeprecationWarning)
        return Server(
            spec.name,
            version=spec.version,
            instructions=spec.instructions,
            on_list_tools=on_list_tools,
            on_call_tool=on_call_tool,
            on_set_logging_level=on_set_logging_level,
        )


def serve_stdio(spec: ServerSpec, limits: Limits | None = None) -> None:
    """Serve ``spec`` on stdin/stdout until the client closes the connection."""
    server = build_server(spec, limits or Limits.from_env())
    options = server.create_initialization_options(
        notification_options=NotificationOptions(tools_changed=True)
    )

    async def main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, options)

    log.info("%s %s starting on stdio", spec.name, spec.version)
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        # Ctrl+C on a server started by hand: no traceback, and the conventional exit status
        # 130 (as the JVM gives). The SDK's stdin reader only notices once stdin has a line or
        # closes, so the server stops then.
        log.info("%s interrupted", spec.name)
        raise SystemExit(130) from None
    log.info("%s stopped", spec.name)


def run_server(spec: ServerSpec, argv: Sequence[str] | None = None) -> None:
    """A server's entry point: log to ``~/.calculator-mcp/<server name>.log`` (or
    ``--logging.file.name=``), then serve ``spec`` on stdio."""
    configure_logging(f"{spec.name}.log", sys.argv[1:] if argv is None else argv)
    serve_stdio(spec)


def tools_by_name(tools: Sequence[Tool]) -> dict[str, Tool]:
    """Index tools by name, refusing duplicates."""
    index: dict[str, Tool] = {}
    for t in tools:
        if t.name in index:
            raise ValueError(f"duplicate tool name: {t.name}")
        index[t.name] = t
    return index
