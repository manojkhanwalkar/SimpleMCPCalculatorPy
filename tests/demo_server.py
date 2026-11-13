"""A one-tool server for end-to-end tests of tool_server over real stdio."""

import sys

from simple_mcp_calculator.common.logfile import configure_logging
from simple_mcp_calculator.common.tool_server import Param, ServerSpec, Tool, serve_stdio


def _divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Division by zero")
    return a / b


SPEC = ServerSpec(
    name="calculator-mcp-server",
    version="1.0.0",
    instructions="Demo instructions",
    tools=(
        Tool(
            "divide",
            "Divide the first number by the second: a / b. Fails if b is 0",
            (Param("a", "Dividend"), Param("b", "Divisor (must not be 0)")),
            _divide,
        ),
    ),
)

if __name__ == "__main__":
    configure_logging("demo-server.log", sys.argv[1:])
    serve_stdio(SPEC)
