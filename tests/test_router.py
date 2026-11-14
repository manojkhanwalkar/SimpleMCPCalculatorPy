"""The router (ports of CalculatorRouterEndToEndTest), against both real Python servers."""

import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from mcp import types

from simple_mcp_calculator.common.mcp_call import Connection, ServerCommand, connect
from simple_mcp_calculator.router.router import CalculatorRouter, required_parameters

CALCULATOR = ServerCommand.resolve("calculator", "simple_mcp_calculator.calculator_server", {})
SCIENTIFIC = ServerCommand.resolve("scientific", "simple_mcp_calculator.scientific_server", {})


@asynccontextmanager
async def both_servers() -> AsyncIterator[tuple[CalculatorRouter, list[Connection]]]:
    """A router over both real servers. (Not a fixture: anyio requires the connections to be
    opened and closed in the same task.)"""
    async with connect(CALCULATOR, SCIENTIFIC) as connections:
        yield await CalculatorRouter.create(connections), connections


ALL = {
    "add", "subtract", "multiply", "divide", "remainder", "exponent", "factorial", "isPrime",
    "parity", "sqrt", "ln", "log10", "log",
}  # fmt: skip


async def test_offers_every_operation_of_both_servers() -> None:
    """Ports: CalculatorRouterEndToEndTest.offersEveryOperationOfBothServers"""
    async with both_servers() as (router, _):
        assert set(router.routes) == ALL
        assert list(router.routes) == sorted(ALL)


async def test_routes_each_operation_to_the_server_that_offers_it() -> None:
    """Ports: CalculatorRouterEndToEndTest.routesEachOperationToTheServerThatOffersIt"""
    async with both_servers() as (router, _):
        for op in ("add", "subtract", "multiply", "divide", "remainder", "exponent", "factorial",
                   "isPrime", "parity"):  # fmt: skip
            assert router.routes[op].server == "calculator-mcp-server", op
        for op in ("sqrt", "ln", "log10", "log"):
            assert router.routes[op].server == "scientific-calculator-mcp-server", op


async def test_learns_parameter_names_in_order_from_the_servers() -> None:
    """Ports: CalculatorRouterEndToEndTest.learnsParameterNamesInOrderFromTheServers"""
    async with both_servers() as (router, _):
        assert router.routes["subtract"].parameters == ("a", "b")
        assert router.routes["factorial"].parameters == ("n",)
        assert router.routes["log"].parameters == ("x", "base")


async def test_calls_operations_on_both_servers() -> None:
    """Ports: CalculatorRouterEndToEndTest.callsOperationsOnBothServers"""
    async with both_servers() as (router, _):
        assert await router.calculate("subtract", [17.0, 5.0]) == "12.0"
        assert await router.calculate("factorial", [5.0]) == "120"
        assert await router.calculate("parity", [17.0]) == "odd"
        assert await router.calculate("sqrt", [144.0]) == "12.0"
        assert await router.calculate("log", [1024.0, 2.0]) == "10.0"


async def test_server_errors_come_back_as_errors() -> None:
    """Ports: CalculatorRouterEndToEndTest.serverErrorsComeBackAsErrors"""
    async with both_servers() as (router, _):
        assert await router.calculate("divide", [1.0, 0.0]) == "Error: Division by zero"
        assert await router.calculate("sqrt", [-4.0]) == "Error: Square root of a negative number"


async def test_bad_calls_are_rejected_before_reaching_a_server() -> None:
    """Ports: CalculatorRouterEndToEndTest.badCallsAreRejectedBeforeReachingAServer"""
    async with both_servers() as (router, _):
        assert await router.calculate("cube_root", [8.0]) == "Error: Unknown operation: cube_root"
        assert await router.calculate("log", [8.0]) == "Error: log takes 2 operand(s): x, base"
        assert await router.calculate("sqrt", [4.0, 2.0]) == "Error: sqrt takes 1 operand(s): x"


async def test_same_tool_on_two_servers_is_rejected() -> None:
    """Ports: CalculatorRouterEndToEndTest.sameToolOnTwoServersIsRejected"""
    async with both_servers() as (_, connections):
        scientific = connections[1]
        with pytest.raises(ValueError, match="offered by both"):
            await CalculatorRouter.create([scientific, scientific])


def test_a_schema_without_required_has_no_parameters() -> None:
    tool = types.Tool(name="t", input_schema={"type": "object"})
    assert required_parameters(tool) == ()


def _router(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed test command
        [sys.executable, "-m", "simple_mcp_calculator.router", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_the_router_cli_refuses_a_tool_offered_twice() -> None:
    """Java fails to start (IllegalStateException in CalculatorRouter); the port prints the
    same message as one error line and exits 1."""
    twice = (
        f"--calculator.server.command={sys.executable} -m simple_mcp_calculator.scientific_server"
    )
    done = _router(twice, "sqrt", "4")
    assert (done.returncode, done.stdout) == (1, "")
    assert done.stderr == (
        "Error: Tool 'ln' is offered by both scientific-calculator-mcp-server and "
        "scientific-calculator-mcp-server; can't tell which to call\n"
    )


@pytest.mark.parametrize(
    "args", [("log", "--", "1024", "2"), ("log", "1024", "2", "--"), ("--", "log", "1024", "2")]
)
def test_a_bare_double_dash_ends_the_options(args: tuple[str, ...]) -> None:
    """Spring's rule, as the Java clients follow it."""
    done = _router(*args)
    assert (done.returncode, done.stdout, done.stderr) == (0, "10.0\n", "")
