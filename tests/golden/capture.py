"""Capture golden MCP responses from the Java servers (stdlib only; needs Java 25+).

Usage, from this repository's root, with the Java project built (``./mvnw package``):

    python -I tests/golden/capture.py /path/to/SimpleMCPCalculator [calculator|scientific]

Writes ``tests/golden/<server>.jsonl``. The first line holds the server's ``initialize`` result
and ``tools/list`` result. Every further line is one ``tools/call``: the tool, its arguments as
the raw JSON text sent (so values such as ``1e400`` survive) and the server's ``result`` or
JSON-RPC ``error``.
"""

import itertools
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
PROTOCOL_VERSION = "2025-11-25"

# Raw JSON number texts: edge cases of IEEE-754 doubles and of Java's formatting.
NUMBERS = [
    "0",
    "-0.0",
    "1",
    "-1",
    "2",
    "3",
    "5",
    "7",
    "9",
    "10",
    "17",
    "-7",
    "-8",
    "0.5",
    "2.5",
    "7.5",
    "0.1",
    "1e-7",
    "1e-10",
    "400",
    "1e10",
    "1e16",
    "1e21",
    "123456789.123",
    "9007199254740992",
    "1e308",
    "1.7976931348623157e308",
    "5e-324",
    "-2.5",
    "0.001",
    "1e400",
    "-1e400",
]
WHOLE = [
    "0",
    "-0.0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "15",
    "17",
    "20",
    "21",
    "-1",
    "-3",
    "-4",
    "-7",
    "42",
    "91",
    "97",
    "7917",
    "7919",
    "2.5",
    "1.5",
    "7.5",
    "2147483647",
    "999999999989",
    "9007199254740881",
    "9007199254740880",
    "9007199254740992",
    "9007199254740994",
    "-9007199254740992",
    "1e300",
    "1e-300",
    "1e400",
    "-1e400",
]
POSITIVE = [
    "0",
    "-0.0",
    "1",
    "2",
    "2.25",
    "144",
    "1000",
    "0.01",
    "1024",
    "2.718281828459045",
    "0.36787944117144233",
    "1e15",
    "1e-300",
    "1e308",
    "1.7976931348623157e308",
    "5e-324",
    "-1",
    "-4",
    "-0.001",
    "8",
    "81",
    "243",
    "125",
    "25",
    "0.5",
    "7",
    "10",
    "3",
    "1e400",
]
# Arguments that fail schema validation, or that are not plain numbers.
BAD_PAIRS = [
    "{}",
    '{"a":1}',
    '{"a":"x","b":1}',
    '{"a":1,"b":2,"c":3}',
    '{"a":null,"b":1}',
    '{"a":true,"b":1}',
    '{"a":"7","b":"5"}',
    '{"a":"x"}',
    '{"b":"x"}',
    '{"a":[1],"b":{}}',
    '{"b":null,"a":"s"}',
    '{"a":true,"b":false}',
    '{"b":"y","a":"x"}',
    "null",
    '{"a":12345678901234567890123,"b":0}',
    '{"a":1,"b":2.0e0}',
]


def _pairs(tools: list[str], first: str, second: str, values: list[str]) -> list[tuple[str, str]]:
    return [
        (tool, f'{{"{first}":{a},"{second}":{b}}}')
        for tool in tools
        for a, b in itertools.product(values, values)
    ]


def _singles(tools: list[str], name: str, values: list[str]) -> list[tuple[str, str]]:
    return [(tool, f'{{"{name}":{v}}}') for tool in tools for v in values]


SERVERS = {
    "calculator": (
        "calculator-mcp-server/target/calculator-mcp-server.jar",
        _pairs(
            ["add", "subtract", "multiply", "divide", "remainder", "exponent"], "a", "b", NUMBERS
        )
        + _singles(["factorial", "isPrime", "parity"], "n", WHOLE)
        + [("add", args) for args in BAD_PAIRS]
        + [("factorial", "{}"), ("factorial", '{"n":"5"}'), ("nosuch", '{"a":1}')],
    ),
    "scientific": (
        "ScientificCalculatorMCP/scientific-calculator-mcp-server/target/"
        "scientific-calculator-mcp-server.jar",
        _singles(["sqrt", "ln", "log10"], "x", POSITIVE)
        + _pairs(["log"], "x", "base", POSITIVE)
        + [("sqrt", "{}"), ("sqrt", '{"x":"4"}'), ("log", '{"x":8}'), ("nosuch", '{"x":1}')],
    ),
}


REPLY_TIMEOUT = 30.0
MAX_ATTEMPTS = 3


class Session:
    """One Java server process, driven over raw JSON-RPC.

    The Java SDK's stdio transport occasionally drops a response ("Failed to enqueue message" in
    its log), so every reply has a deadline; the caller restarts the server and retries.
    """

    def __init__(self, jar: Path, log: Path) -> None:
        self.proc = subprocess.Popen(  # noqa: S603 - fixed command
            ["java", "-jar", str(jar), f"--logging.file.name={log}"],  # noqa: S607
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        assert self.proc.stdout is not None
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.buffer = b""
        self.next_id = 0
        init = self.request(
            "initialize",
            json.dumps(
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "golden", "version": "1"},
                }
            ),
            timeout=120,  # JVM start-up
        )
        self.initialize_result = init["result"]
        self.send('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    def _readline(self, deadline: float) -> bytes:
        assert self.proc.stdout is not None
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError("no reply from the Java server")
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                raise EOFError("the Java server closed stdout")
            self.buffer += chunk
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line

    def request(
        self, method: str, params_json: str | None = None, timeout: float = REPLY_TIMEOUT
    ) -> dict[str, object]:
        self.next_id += 1
        params = f',"params":{params_json}' if params_json is not None else ""
        self.send(f'{{"jsonrpc":"2.0","id":{self.next_id},"method":"{method}"{params}}}')
        deadline = time.monotonic() + timeout
        while True:
            reply: dict[str, object] = json.loads(self._readline(deadline))
            if reply.get("id") == self.next_id:
                return reply

    def send(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line.encode() + b"\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        self.proc.wait(timeout=30)

    def kill(self) -> None:
        self.proc.kill()
        self.proc.wait()


def capture(java_root: Path, server: str) -> Path:
    jar_path, calls = SERVERS[server]
    jar = java_root / jar_path
    restarts = 0
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "server.log"
        session = Session(jar, log)
        tools = session.request("tools/list")
        lines = [
            json.dumps(
                {"initialize": session.initialize_result, "tools": tools["result"]}, sort_keys=True
            )
        ]
        for tool, arguments in calls:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    reply = session.request(
                        "tools/call", f'{{"name":"{tool}","arguments":{arguments}}}'
                    )
                    break
                except TimeoutError:
                    if attempt == MAX_ATTEMPTS - 1:
                        raise
                    session.kill()
                    restarts += 1
                    session = Session(jar, log)
            entry: dict[str, object] = {"tool": tool, "arguments": arguments}
            entry.update({k: reply[k] for k in ("result", "error") if k in reply})
            lines.append(json.dumps(entry, sort_keys=True))
        session.close()
    out = HERE / f"{jar.stem}.jsonl"
    out.write_text("\n".join(lines) + "\n")
    if restarts:
        print(f"{jar.stem}: restarted the Java server {restarts} time(s) after a dropped reply")
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1])
    for name in sys.argv[2:] or list(SERVERS):
        path = capture(root, name)
        print(f"{path}: {len(path.read_text().splitlines()) - 1} calls")
