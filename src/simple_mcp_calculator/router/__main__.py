"""``calculator-router-client``: start both servers and route each operation to the one that
offers it.

    calculator-router-client               # list every operation with its server, then a demo
    calculator-router-client add 7 5       # routed to calculator-mcp-server
    calculator-router-client log 1024 2    # routed to scientific-calculator-mcp-server

``--name=value`` options may be mixed in (``--calculator.server.jar=…``,
``--scientific.server.jar=…``, or ``--….server.command=…``); a bare ``--`` ends them. Exits with 1
on bad usage or when a server reports an error, 130 on Ctrl+C and 143 on SIGTERM.
"""

import math
import sys
from collections.abc import Sequence
from typing import TextIO

from simple_mcp_calculator.common.javafmt import java_double_str
from simple_mcp_calculator.common.javaparse import java_parse_double
from simple_mcp_calculator.common.mcp_call import (
    Arguments,
    ServerCommand,
    connect,
    emit,
    run_client,
)
from simple_mcp_calculator.router.router import CalculatorRouter

USAGE = "Usage: calculator-router-client [<operation> <operand>...]"
SERVERS = (
    ("calculator", "simple_mcp_calculator.calculator_server"),
    ("scientific", "simple_mcp_calculator.scientific_server"),
)


def is_finite_number(text: str) -> bool:
    """NaN and Infinity parse as doubles but can't be sent as JSON numbers, so they are
    rejected here."""
    try:
        return math.isfinite(java_parse_double(text))
    except ValueError:
        return False


def print_operations(router: CalculatorRouter, out: TextIO) -> None:
    emit("Operations:", out)
    for name, route in router.routes.items():
        emit(f"  {name:<10} {', '.join(route.parameters):<12} -> {route.server}", out)


def _java_list(values: Sequence[float]) -> str:
    """``List.toString`` of Doubles: ``[17.0, 5.0]``."""
    return "[" + ", ".join(java_double_str(v) for v in values) + "]"


DEMO: tuple[tuple[str, tuple[float, ...]], ...] = (
    ("add", (17.0, 5.0)),
    ("factorial", (5.0,)),
    ("parity", (17.0,)),
    ("sqrt", (144.0,)),
    ("log", (1024.0, 2.0)),
    ("divide", (1.0, 0.0)),
    ("cube_root", (8.0,)),
)


async def _demo(router: CalculatorRouter) -> None:
    print_operations(router, sys.stdout)
    emit("")
    for operation, operands in DEMO:
        result = await router.calculate(operation, operands)
        emit(f"{operation:<10} {_java_list(operands):<13} = {result}")


async def run(argv: Sequence[str]) -> int:
    args = Arguments.parse(argv)
    servers = [ServerCommand.resolve(name, module, args.options) for name, module in SERVERS]
    async with connect(*servers) as connections:
        router = await CalculatorRouter.create(connections)
        if not args.positional:
            await _demo(router)
            return 0
        operation, *operands = args.positional
        if not all(is_finite_number(o) for o in operands):
            emit(USAGE, sys.stderr)
            print_operations(router, sys.stderr)
            return 1
        result = await router.calculate(operation, [java_parse_double(o) for o in operands])
        emit(result)
        return 1 if result.startswith("Error:") else 0


def main() -> None:
    sys.exit(run_client(run, sys.argv[1:]))


if __name__ == "__main__":
    main()
