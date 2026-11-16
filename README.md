# SimpleMCPCalculatorPy

[![CI](https://github.com/manojkhanwalkar/SimpleMCPCalculatorPy/actions/workflows/ci.yml/badge.svg)](https://github.com/manojkhanwalkar/SimpleMCPCalculatorPy/actions/workflows/ci.yml)

A Python port of [SimpleMCPCalculator](https://github.com/manojkhanwalkar/SimpleMCPCalculator) (converted from commit `6794f98`). It is meant as a drop-in replacement: [MCP](https://modelcontextprotocol.io) servers that expose calculators as tools, and command-line clients that launch the servers and talk to them over **stdio** (JSON-RPC on the server's stdin/stdout). The servers answer every request exactly as the Java servers do: the same tools, schemas, results, error texts and command-line output, checked against thousands of responses captured from the Java jars.

```
calculator-mcp-client ──(MCP over stdin/stdout)──> calculator-mcp-server

                          ┌──(stdio)──> calculator-mcp-server
calculator-router-client ─┤
                          └──(stdio)──> scientific-calculator-mcp-server

scientific-calculator-mcp-client ──(stdio)──> scientific-calculator-mcp-server
```

| Command | What it is |
|---|---|
| `calculator-mcp-server` | MCP server with nine tools: `add`, `subtract`, `multiply`, `divide`, `remainder`, `exponent`, `factorial`, `isPrime`, `parity` |
| `scientific-calculator-mcp-server` | MCP server with four tools: `sqrt`, `ln`, `log10`, `log` |
| `calculator-mcp-client` | Starts the calculator server and calls its tools from the command line |
| `scientific-calculator-mcp-client` | Starts the scientific server and calls its tools |
| `calculator-router-client` | Starts **both** servers and sends each operation to the server that offers it |

## Requirements

- Python 3.14 and [uv](https://docs.astral.sh/uv/).

## Set up

```bash
uv sync
```

This creates `.venv/` with the five commands above. Run them with `uv run <command>`, or activate the environment first (`source .venv/bin/activate`).

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `add`, `subtract`, `multiply`, `divide` | `a`, `b` | `a + b`, `a - b`, `a * b`, `a / b`; error result if `b` is 0 for `divide` |
| `remainder` | `a`, `b` | `a % b` (sign of `a`); error result if `b` is 0 |
| `exponent` | `a`, `b` | `a` raised to the power `b` |
| `factorial` | `n` (whole number) | `n!`; error result unless `0 <= n <= 20` |
| `isPrime` | `n` (whole number) | `true` or `false` |
| `parity` | `n` (whole number) | `even` or `odd` |
| `sqrt` | `x` | square root; error result if `x < 0` |
| `ln`, `log10` | `x` | natural and base-10 logarithm; error result unless `x > 0` |
| `log` | `x`, `base` | logarithm of `x` in `base`; exact whole numbers for exact powers (`log 1000 10` is `3.0`) |

Results are written as Java writes doubles (`22.0`, `1.0E21`). A result that overflows or is undefined (`exponent 10 400`, `exponent -8 0.5`) is an error result, not `Infinity` or `NaN`. The one exception, as in Java: `remainder` of an infinite `a` (sent as `1e400`) returns `"NaN"`. Whole-number tools reject fractions and anything beyond 2^53. Every tool is read-only and idempotent.

## Use the clients

```bash
# Demo: list the server's tools and call each one
uv run calculator-mcp-client

# One tool: <operation> <a> <b>, or <operation> <n>
uv run calculator-mcp-client add 7 5          # 12.0
uv run calculator-mcp-client divide 1 0       # Error: Division by zero (exit code 1)
uv run calculator-mcp-client factorial 5      # 120
uv run calculator-mcp-client parity 7.5       # Error: Not a whole number: 7.5 (exit code 1)

uv run scientific-calculator-mcp-client sqrt 144      # 12.0
uv run scientific-calculator-mcp-client log 1024 2    # 10.0

# The router: all 13 operations, each sent to the server that offers it
uv run calculator-router-client                 # operation list, then a demo
uv run calculator-router-client log 1024 2      # 10.0  (scientific server)
uv run calculator-router-client isPrime 97      # true  (calculator server)
uv run calculator-router-client log 8           # Error: log takes 2 operand(s): x, base
```

On success the result goes to stdout and the exit code is 0. Every failure exits with 1:

- A server's error, an unknown operation or a wrong operand count prints `Error: …` on stdout.
- Operands that aren't numbers print the usage line and the operation list on stderr.
- A server that can't be started prints `Error: Cannot start the server: <name> (<command>): <reason>` on stderr (for example `calculator (java -jar calc.jar): …`), ending with the server's last stderr line if it wrote one. The Java clients print Spring Boot's startup failure report instead.
- Any other failure, such as a malformed option, prints `Error: <message>` on stderr.

Ctrl+C exits with 130 and SIGTERM with 143. In both cases the servers are shut down first.

Numbers are parsed as Java parses them: `1d`, `0x1p3` and `+5` are numbers, and `1_000` is not. Options follow Spring Boot's rules: `--name=value` can appear anywhere, and a bare `--` ends the options, so `log -- 8 2` works. On a terminal, control characters in server text are shown as `�`; output to a file or pipe is left as is.

### Point a client at another server

Each client starts its servers with the same Python interpreter by default. To use a different server, mix one of these options into the arguments:

```bash
# A Java server jar (the Java clients' own option)
uv run calculator-mcp-client --calculator.server.jar=/path/to/calculator-mcp-server.jar add 7 5

# The same, from the environment (Spring's relaxed binding)
CALCULATOR_SERVER_JAR=/path/to/calculator-mcp-server.jar uv run calculator-mcp-client add 7 5

# Any command (split like a shell would, never run through one)
uv run calculator-router-client --scientific.server.command="/path/to/other-server --flag" sqrt 2
```

The router takes `--calculator.server.…` and `--scientific.server.…` (and `CALCULATOR_SERVER_JAR` / `SCIENTIFIC_SERVER_JAR`). A command option wins over a jar option, which wins over the environment variable.

## Run a server on its own

With stdio there is no port: whoever connects starts the server. To try one by hand:

```bash
uv run calculator-mcp-server
```

Then paste JSON-RPC lines:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"manual","version":"1"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add","arguments":{"a":7,"b":5}}}
```

Stdout is the protocol channel, so the server logs to `~/.calculator-mcp/<server>.log` (owner-only, rolled at 10 MB, 7 kept). Override with `--logging.file.name=<path>`.

Each server limits tool calls to 200 a second (burst 400) and 8 at once; over-limit calls get an error result. Set `CALCULATOR_MCP_RATE`, `CALCULATOR_MCP_BURST` and `CALCULATOR_MCP_MAX_CONCURRENT` in **the server's own environment** to change that: for example in the `env` of a Claude Desktop server entry. Setting them where you run one of the clients has no effect (see below). A malformed value stops the server at start-up with one line, `Error: Invalid request limits: …`, and exit status 1. Ctrl+C on a server started by hand stops it, with exit status 130, once stdin has a line or closes.

## Use the servers from Claude Code or Claude Desktop

```bash
claude mcp add calculator -- uv run --directory "$(pwd)" calculator-mcp-server
claude mcp add scientific-calculator -- uv run --directory "$(pwd)" scientific-calculator-mcp-server
```

For Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "calculator": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/SimpleMCPCalculatorPy", "calculator-mcp-server"]
    },
    "scientific-calculator": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/SimpleMCPCalculatorPy", "scientific-calculator-mcp-server"]
    }
  }
}
```

## Differences from the Java version

These are deliberate. The [design doc](https://claude.ai/artifact/PSoGdkgiSTdJsUwGLjuT8m) explains each one.

- **Annotations:** the basic calculator's tools are annotated read-only, idempotent and closed-world, like the scientific tools. Java sends Spring's defaults (destructive, open-world).
- **Request limits:** the servers have a token bucket and a concurrency cap. Java has none.
- **`isPrime`** uses deterministic Miller-Rabin instead of trial division: the same answers, in microseconds near 2^53.
- **Unexpected exceptions** return `Internal error` without internal details.
- **Logarithms:** `ln`, `log10` and `log` can differ from Java in the last digit (1–2 ulps) on some inputs. Java's HotSpot intrinsics and the C library round differently. A negative-exponent `exponent` can differ by 1 ulp for the same reason.
- **Clients:** the usage line names the Python command, and the clients start the Python servers by default (`--….server.jar=` still runs a Java jar).
- **Failures in the clients** are one line on stderr with exit status 1. Java's clients instead print a Spring Boot start-up failure, and for a missing server jar or a tool offered by two servers, they print a stack trace on stdout and then hang.
- **Signals:** Ctrl+C exits 130 and SIGTERM 143, after the servers are shut down.
- **Terminal output:** control characters in server text are neutralised on a terminal.
- **Servers started by a client** get the MCP SDK's minimal environment (`HOME`, `PATH`, `SHELL`, `TERM`, `USER`, `LOGNAME`), not the client's. So `CALCULATOR_MCP_*` set for a client never reaches its servers, and `JAVA_HOME` or `JAVA_TOOL_OPTIONS` never reaches a server started with `--….server.jar`.
- **MCP client name:** the clients introduce themselves to servers with the Python SDK's default `clientInfo` name, not `calculator-mcp-client` and so on.
- **Log file:** a symlink (or anything that isn't a regular file) at the log path is refused, and the server logs to a fresh private temp directory instead.
- **Protocol errors** that the SDK raises (an unknown method, a malformed request) use the Python MCP SDK's wording. `NaN` and `Infinity` literals in a request are accepted, while Java's server dies on them.

## Speed

The Python servers start about 4.5 times faster than the Java ones, and a router call takes about a fifth of the time (the router starts its two servers' handshakes concurrently).

| Measurement | Python | Java |
|---|---|---|
| Calculator server: launch until it answers `initialize` | 1.3 s | 5.9 s (5.5–6.1) |
| Scientific server: launch until it answers `initialize` | 1.3 s (1.2–1.3) | 5.7 s (5.6–6.8) |
| `calculator-router-client sqrt 2`, which starts both servers | 3.8 s (3.76–3.82) | 18.8 s (18.6–19.8) |

The servers were launched directly (`.venv/bin/python -m …` and `java -jar …`, not through `uv run`), and the router through its console script and its jar. Each figure is the median of 9 runs (5 for the router), with the range in brackets, on an otherwise idle 8-core x86-64 Linux machine (1-minute load below 1.0 at the start) with Python 3.14 and Java 26. Your figures will differ; the ratios are the point.

## Compliance

The calculators handle numbers only: no personal, payment or financial data, no tracking, no user interface and no AI decisions. So neither the compliance check (SOX, PII, PCI) nor the digital-regulation check (GDPR, EU digital laws) applies. The design doc lists what would change that.

## Development

```bash
uv run pytest                 # tests, with a 95% coverage gate
uv run ruff check .           # lint
uv run ruff format --check .  # formatting
uv run mypy                   # strict type check
```

The golden tests compare the servers and clients with responses captured from the Java project. To capture them again, you need Java 25 or newer: build the Java project (`./mvnw package`), then run:

```bash
python -I tests/golden/capture.py /path/to/SimpleMCPCalculator      # servers
python -I tests/golden/capture_cli.py /path/to/SimpleMCPCalculator  # command-line clients (about 30 min)
```

With a built Java project, the cross-language tests also run the Python clients against the Java servers, and the Java clients against the Python servers:

```bash
SIMPLE_MCP_CALCULATOR_JAVA=/path/to/SimpleMCPCalculator uv run pytest tests/test_cross_language.py
```

Without that variable, or without a JDK, they are skipped (as in CI).

To work in IntelliJ IDEA, run `uv sync` once, then *File → Open* this folder. IntelliJ needs the Python plugin. The first time, add an interpreter (*Existing → `.venv/bin/python`*) named `uv (SimpleMCPCalculatorPy)`, the name the project files refer to.
