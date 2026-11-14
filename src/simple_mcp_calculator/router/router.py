"""Send each operation to whichever connected server offers a tool of that name (port of
``CalculatorRouter.java``).

The routing table is built once from every server's ``tools/list``, so a tool added to either
server is picked up without changing this module. Operands are positional: they are matched, in
order, to the tool's required parameters (``a, b`` for add, ``n`` for factorial, ``x, base`` for
log, ...).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from mcp import types

from simple_mcp_calculator.common.mcp_call import Connection


@dataclass(frozen=True, slots=True)
class Route:
    """Where an operation is sent and which parameters it takes, in order."""

    connection: Connection
    server: str
    parameters: tuple[str, ...]


def required_parameters(tool: types.Tool) -> tuple[str, ...]:
    """The input schema's ``required`` list, which the servers write in parameter order."""
    required = (tool.input_schema or {}).get("required")
    return tuple(str(p) for p in required) if isinstance(required, list) else ()


class CalculatorRouter:
    def __init__(self, routes: dict[str, Route]) -> None:
        self._routes = dict(sorted(routes.items()))

    @classmethod
    async def create(cls, connections: Sequence[Connection]) -> CalculatorRouter:
        """Learn every server's tools. Raises ``ValueError`` if two servers offer a tool with
        the same name (Java: IllegalStateException)."""
        routes: dict[str, Route] = {}
        for connection in connections:
            for tool in await connection.list_tools():
                existing = routes.get(tool.name)
                if existing is not None:
                    raise ValueError(
                        f"Tool '{tool.name}' is offered by both {existing.server} and "
                        f"{connection.server_name}; can't tell which to call"
                    )
                routes[tool.name] = Route(
                    connection, connection.server_name, required_parameters(tool)
                )
        return cls(routes)

    @property
    def routes(self) -> dict[str, Route]:
        """Every operation offered by any server, by name, with the server it is routed to."""
        return self._routes

    async def calculate(self, operation: str, operands: Sequence[float]) -> str:
        """Call ``operation`` on the server that offers it and return the text result, or
        ``Error: <message>`` if the operation is unknown, the operand count is wrong, or the
        server reports an error."""
        route = self._routes.get(operation)
        if route is None:
            return f"Error: Unknown operation: {operation}"
        if len(operands) != len(route.parameters):
            return f"Error: {operation} takes {len(route.parameters)} operand(s): " + ", ".join(
                route.parameters
            )
        return await route.connection.call(
            operation, dict(zip(route.parameters, operands, strict=True))
        )
