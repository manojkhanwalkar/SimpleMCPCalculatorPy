"""Unit tests of the basic calculator's tools: ports of CalculatorToolsTest.java plus Java
``double`` corner cases the port has to reproduce explicitly."""

import math
from collections.abc import Callable

import pytest

from simple_mcp_calculator.calculator_server import tools
from simple_mcp_calculator.common.tool_server import READ_ONLY


def test_basic_arithmetic() -> None:
    """Ports: CalculatorToolsTest.basicArithmetic"""
    assert tools.add(7, 5) == 12
    assert tools.subtract(7, 5) == 2
    assert tools.multiply(7, 5) == 35
    assert tools.divide(7, 5) == 1.4
    assert tools.remainder(7, 5) == 2


def test_negative_and_fractional_operands() -> None:
    """Ports: CalculatorToolsTest.negativeAndFractionalOperands"""
    assert tools.add(-5, 2.5) == -2.5
    assert tools.remainder(-7, 3) == -1
    assert tools.remainder(7.5, 2) == 1.5


def test_division_by_zero_is_rejected() -> None:
    """Ports: CalculatorToolsTest.divisionByZeroIsRejected"""
    with pytest.raises(ValueError, match=r"^Division by zero$"):
        tools.divide(1, 0)
    with pytest.raises(ValueError, match=r"^Division by zero$"):
        tools.remainder(1, 0)
    with pytest.raises(ValueError, match=r"^Division by zero$"):
        tools.divide(1, -0.0)


def test_exponent() -> None:
    """Ports: CalculatorToolsTest.exponent"""
    assert tools.exponent(2, 10) == 1024
    assert tools.exponent(7, 0) == 1
    assert tools.exponent(2, -2) == 0.25
    assert tools.exponent(9, 0.5) == 3


@pytest.mark.parametrize(
    ("tool", "a", "b", "message"),
    [
        (tools.exponent, 10, 400, "Result is too large"),
        (tools.exponent, -8, 0.5, "Result is undefined"),
        (tools.exponent, 0, -1, "Result is too large"),
        (tools.multiply, 1e308, 10, "Result is too large"),
        (tools.divide, 1e308, 1e-10, "Result is too large"),
        (tools.add, 1.7976931348623157e308, 1.7976931348623157e308, "Result is too large"),
    ],
)
def test_non_finite_results_are_rejected(
    tool: Callable[[float, float], float], a: float, b: float, message: str
) -> None:
    """Ports: CalculatorToolsTest.nonFiniteResultsAreRejected"""
    with pytest.raises(ArithmeticError, match=f"^{message}$"):
        tool(a, b)


def test_factorial() -> None:
    """Ports: CalculatorToolsTest.factorial"""
    assert tools.factorial(0) == 1
    assert tools.factorial(1) == 1
    assert tools.factorial(5) == 120
    assert tools.factorial(20) == 2_432_902_008_176_640_000


def test_factorial_rejects_out_of_range_and_fractional_input() -> None:
    """Ports: CalculatorToolsTest.factorialRejectsOutOfRangeAndFractionalInput"""
    for n in (-1, 21):
        with pytest.raises(ValueError, match=r"^Factorial is only defined here for 0 to 20$"):
            tools.factorial(n)
    with pytest.raises(ValueError, match=r"^Not a whole number: 2\.5$"):
        tools.factorial(2.5)


def test_is_prime() -> None:
    """Ports: CalculatorToolsTest.isPrime"""
    for p in (2, 3, 5, 7, 11, 13, 97, 7919):
        assert tools.is_prime(p), p
    for n in (-7, 0, 1, 4, 9, 15, 25, 91, 7917):
        assert not tools.is_prime(n), n
    assert tools.is_prime(2_147_483_647)
    with pytest.raises(ValueError, match=r"^Not a whole number"):
        tools.is_prime(7.5)


def test_parity() -> None:
    """Ports: CalculatorToolsTest.parity"""
    assert tools.parity(0) == "even"
    assert tools.parity(42) == "even"
    assert tools.parity(17) == "odd"
    assert tools.parity(-3) == "odd"
    assert tools.parity(-4) == "even"
    with pytest.raises(ValueError, match=r"^Not a whole number"):
        tools.parity(1.5)
    with pytest.raises(ValueError, match=r"^Not a whole number: NaN$"):
        tools.parity(math.nan)
    with pytest.raises(
        ValueError, match=r"^Whole number out of range \(\|n\| <= 2\^53\): 1\.0E300$"
    ):
        tools.parity(1e300)


# --- beyond the Java tests: semantics the port reproduces explicitly ---------------------


def _trial_division(n: int) -> bool:
    """The Java tool's algorithm, as the reference for Miller-Rabin."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i <= n // i:
        if n % i == 0:
            return False
        i += 2
    return True


def test_miller_rabin_agrees_with_trial_division() -> None:
    for n in range(-5, 20_000):
        assert tools.is_prime(n) == _trial_division(n), n
    # Strong pseudoprimes to several small bases, and the largest prime below 2^53.
    for n in (3_215_031_751, 3_825_123_056_546_413_051, 2_152_302_898_747, 341_550_071_728_321):
        if n <= tools.MAX_EXACT_WHOLE_NUMBER:
            assert not tools.is_prime(n), n
    assert tools.is_prime(9_007_199_254_740_881)
    assert not tools.is_prime(9_007_199_254_740_880)
    assert not tools.is_prime(2**53)


def test_whole_number_bounds() -> None:
    assert tools.whole_number(2**53) == 2**53
    assert tools.whole_number(-(2**53)) == -(2**53)
    assert tools.whole_number(-0.0) == 0
    with pytest.raises(ValueError, match=r"Whole number out of range \(\|n\| <= 2\^53\): Infinity"):
        tools.whole_number(math.inf)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (1.0, math.inf, math.nan),  # C99 says 1.0; Java says NaN
        (-1.0, math.inf, math.nan),
        (1.0, -math.inf, math.nan),
        (-0.0, -1.0, math.inf),  # math.pow raises; Java: -Infinity (still "too large")
        (-8.0, 1 / 3, math.nan),
        (10.0, 400.0, math.inf),
        (2.0, 0.5, math.sqrt(2)),
        (math.inf, 0.0, 1.0),
    ],
)
def test_java_pow(a: float, b: float, expected: float) -> None:
    result = tools.java_pow(a, b)
    if math.isnan(expected):
        assert math.isnan(result)
    elif math.isinf(expected):
        assert math.isinf(result)
    else:
        assert result == expected


def test_remainder_of_infinity_is_nan_not_an_error() -> None:
    """Java's remainder has no finiteness check: Infinity % 2 is a successful NaN."""
    assert math.isnan(tools.remainder(math.inf, 2))
    assert tools.remainder(5, math.inf) == 5


def test_every_tool_is_annotated_read_only() -> None:
    """Decided for the port: pure functions are read-only, idempotent and closed-world, unlike
    the Java server's Spring defaults (destructive, open-world)."""
    assert [t.name for t in tools.TOOLS] == [
        "add", "divide", "exponent", "factorial", "isPrime",
        "multiply", "parity", "remainder", "subtract",
    ]  # fmt: skip
    assert all(t.hints == READ_ONLY for t in tools.TOOLS)
