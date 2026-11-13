"""``calculator-mcp-client``: start the calculator server and call its tools.

    calculator-mcp-client              # list tools, then run a demo of every operation
    calculator-mcp-client add 7 5      # call a two-operand tool and print the result
    calculator-mcp-client factorial 5  # call a one-operand tool

``--name=value`` options may be mixed in (``--calculator.server.jar=…``,
``--calculator.server.command=…``). Exits with 1 on bad usage or when the server reports an error.
"""

import sys
from collections.abc import Sequence

from simple_mcp_calculator.common.javaparse import is_java_double, java_parse_double
from simple_mcp_calculator.common.mcp_call import (
    Arguments,
    Connection,
    ServerCommand,
    connect,
    jackson_number,
    run_client,
)

SERVER_MODULE = "simple_mcp_calculator.calculator_server"
USAGE = "Usage: calculator-mcp-client [<operation> <a> <b> | <operation> <n>]"


class CalculatorClient:
    """Turns calculator operations into ``tools/call`` requests (port of CalculatorClient)."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    async def list_operations(self) -> list[str]:
        return [t.name for t in await self._connection.list_tools()]

    async def calculate(self, operation: str, a: float, b: float | None = None) -> str:
        # The Java client sends any parsed double, NaN and Infinity included, as Jackson writes it.
        arguments = (
            {"n": jackson_number(a)}
            if b is None
            else {"a": jackson_number(a), "b": jackson_number(b)}
        )
        return await self._connection.call(operation, arguments)


async def _demo(calculator: CalculatorClient) -> None:
    print("Tools offered by the server: " + ", ".join(await calculator.list_operations()))
    for op in ("add", "subtract", "multiply", "divide", "remainder", "exponent"):
        print(f"{op:<9} 17, 5 = {await calculator.calculate(op, 17, 5)}")
    print(f"{'divide':<9} 1, 0  = {await calculator.calculate('divide', 1, 0)}")
    for op in ("factorial", "isPrime", "parity"):
        print(f"{op:<9} 17    = {await calculator.calculate(op, 17)}")
    print(f"{'factorial':<9} 2.5   = {await calculator.calculate('factorial', 2.5)}")


async def run(argv: Sequence[str]) -> int:
    args = Arguments.parse(argv)
    server = ServerCommand.resolve("calculator", SERVER_MODULE, args.options)
    async with connect(server) as (connection,):
        calculator = CalculatorClient(connection)
        ops = args.positional
        if not ops:
            await _demo(calculator)
            return 0
        if len(ops) == 3 and is_java_double(ops[1]) and is_java_double(ops[2]):
            result = await calculator.calculate(
                ops[0], java_parse_double(ops[1]), java_parse_double(ops[2])
            )
        elif len(ops) == 2 and is_java_double(ops[1]):
            result = await calculator.calculate(ops[0], java_parse_double(ops[1]))
        else:
            print(USAGE, file=sys.stderr)
            print("Operations: " + ", ".join(await calculator.list_operations()), file=sys.stderr)
            return 1
        print(result)
        return 1 if result.startswith("Error:") else 0


def main() -> None:
    sys.exit(run_client(run, sys.argv[1:]))


if __name__ == "__main__":
    main()
