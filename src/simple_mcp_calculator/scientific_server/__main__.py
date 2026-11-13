"""Entry point: ``scientific-calculator-mcp-server`` or
``python -m simple_mcp_calculator.scientific_server``.

Speaks MCP on stdin/stdout; logs go to a private file (see ``common.logfile``).
"""

from collections.abc import Sequence

from simple_mcp_calculator.common.tool_server import run_server
from simple_mcp_calculator.scientific_server.tools import SPEC


def main(argv: Sequence[str] | None = None) -> None:
    run_server(SPEC, argv)


if __name__ == "__main__":
    main()
