"""``scientific-calculator-mcp-client``: start the scientific server and call its tools.

    scientific-calculator-mcp-client              # list tools, then run a demo of every operation
    scientific-calculator-mcp-client sqrt 144     # call a one-operand tool and print the result
    scientific-calculator-mcp-client log 1024 2   # call log with x and base

``--name=value`` options may be mixed in (``--scientific.server.jar=…``,
``--scientific.server.command=…``). Exits with 1 on bad usage or when the server reports an error.
"""

import math
import sys
from collections.abc import Sequence

from simple_mcp_calculator.common.javaparse import java_parse_double
from simple_mcp_calculator.common.mcp_call import (
    Arguments,
    Connection,
    ServerCommand,
    connect,
    run_client,
)

SERVER_MODULE = "simple_mcp_calculator.scientific_server"
USAGE = "Usage: scientific-calculator-mcp-client [<operation> <x> | log <x> <base>]"


class ScientificCalculatorClient:
    """Turns scientific operations into ``tools/call`` requests (port of
    ScientificCalculatorClient)."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    async def list_operations(self) -> list[str]:
        return [t.name for t in await self._connection.list_tools()]

    async def calculate(self, operation: str, x: float, base: float | None = None) -> str:
        arguments = {"x": x} if base is None else {"x": x, "base": base}
        return await self._connection.call(operation, arguments)


def is_finite_number(text: str) -> bool:
    """NaN and Infinity parse as doubles but can't be sent as JSON numbers, so they are
    rejected here."""
    try:
        return math.isfinite(java_parse_double(text))
    except ValueError:
        return False


async def _demo(calculator: ScientificCalculatorClient) -> None:
    print("Tools offered by the server: " + ", ".join(await calculator.list_operations()))
    print(f"{'sqrt':<5} 144     = {await calculator.calculate('sqrt', 144)}")
    print(f"{'sqrt':<5} 2       = {await calculator.calculate('sqrt', 2)}")
    print(f"{'log10':<5} 1000    = {await calculator.calculate('log10', 1000)}")
    print(f"{'log':<5} 1024, 2 = {await calculator.calculate('log', 1024, 2)}")
    print(f"{'ln':<5} 10      = {await calculator.calculate('ln', 10)}")
    print(f"{'sqrt':<5} -4      = {await calculator.calculate('sqrt', -4)}")
    print(f"{'ln':<5} 0       = {await calculator.calculate('ln', 0)}")


async def run(argv: Sequence[str]) -> int:
    args = Arguments.parse(argv)
    server = ServerCommand.resolve("scientific", SERVER_MODULE, args.options)
    async with connect(server) as (connection,):
        calculator = ScientificCalculatorClient(connection)
        if not args.positional:
            await _demo(calculator)
            return 0
        operation, *operands = args.positional
        operations = await calculator.list_operations()
        # log takes x and base; every other tool takes x alone
        expected = 2 if operation == "log" else 1
        if (
            operation not in operations
            or len(operands) != expected
            or not all(is_finite_number(o) for o in operands)
        ):
            print(USAGE, file=sys.stderr)
            print("Operations: " + ", ".join(operations), file=sys.stderr)
            return 1
        values = [java_parse_double(o) for o in operands]
        result = await calculator.calculate(operation, *values)
        print(result)
        return 1 if result.startswith("Error:") else 0


def main() -> None:
    sys.exit(run_client(run, sys.argv[1:]))


if __name__ == "__main__":
    main()
