"""Entry point: ``calculator-mcp-server`` or ``python -m simple_mcp_calculator.calculator_server``.

Speaks MCP on stdin/stdout; logs go to a private file (see ``common.logfile``).
"""

import sys
from collections.abc import Sequence

from simple_mcp_calculator.calculator_server.tools import SPEC
from simple_mcp_calculator.common.logfile import configure_logging
from simple_mcp_calculator.common.tool_server import serve_stdio


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging("calculator-mcp-server.log", sys.argv[1:] if argv is None else argv)
    serve_stdio(SPEC)


if __name__ == "__main__":
    main()
