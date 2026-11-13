"""Unit tests of the scientific calculator's tools: ports of ScientificToolsTest.java."""

import math
from collections.abc import Callable

import pytest

from simple_mcp_calculator.common.javafmt import java_double_str
from simple_mcp_calculator.common.tool_server import READ_ONLY
from simple_mcp_calculator.scientific_server import tools

DELTA = 1e-12


def test_square_root() -> None:
    """Ports: ScientificToolsTest.squareRoot"""
    assert tools.sqrt(0) == 0
    assert java_double_str(tools.sqrt(-0.0)) == "0.0"
    assert tools.sqrt(1) == 1
    assert tools.sqrt(144) == 12
    assert tools.sqrt(2.25) == 1.5
    assert tools.sqrt(2) == math.sqrt(2)


def test_square_root_of_negative_is_rejected() -> None:
    """Ports: ScientificToolsTest.squareRootOfNegativeIsRejected"""
    for x in (-1, -0.001):
        with pytest.raises(ValueError, match=r"^Square root of a negative number$"):
            tools.sqrt(x)


def test_natural_logarithm() -> None:
    """Ports: ScientificToolsTest.naturalLogarithm"""
    assert tools.ln(1) == 0
    assert tools.ln(math.e) == pytest.approx(1, abs=DELTA)
    assert tools.ln(1 / math.e) == pytest.approx(-1, abs=DELTA)


def test_base10_logarithm() -> None:
    """Ports: ScientificToolsTest.base10Logarithm"""
    assert tools.log10(1) == 0
    assert tools.log10(1000) == 3
    assert tools.log10(0.01) == -2


def test_logarithm_in_any_base() -> None:
    """Ports: ScientificToolsTest.logarithmInAnyBase"""
    assert tools.log(1024, 2) == pytest.approx(10, abs=DELTA)
    assert tools.log(81, 3) == pytest.approx(4, abs=DELTA)
    assert tools.log(5, 25) == pytest.approx(0.5, abs=DELTA)
    assert tools.log(8, 0.5) == pytest.approx(-3, abs=DELTA)
    assert tools.log(10, 2) == math.log(10) / math.log(2)


def test_logarithm_of_exact_power_is_exact() -> None:
    """Ports: ScientificToolsTest.logarithmOfExactPowerIsExact"""
    assert tools.log(1000, 10) == 3
    assert tools.log(1e15, 10) == 15
    assert tools.log(243, 3) == 5
    assert tools.log(125, 5) == 3
    assert tools.log(1, 7) == 0


def test_logarithm_of_non_positive_is_rejected() -> None:
    """Ports: ScientificToolsTest.logarithmOfNonPositiveIsRejected"""
    message = r"^Logarithm is only defined for x > 0$"
    calls: list[Callable[[], float]] = [
        lambda: tools.ln(0),
        lambda: tools.ln(-5),
        lambda: tools.log10(0),
        lambda: tools.log(-8, 2),
    ]
    for call in calls:
        with pytest.raises(ValueError, match=message):
            call()


def test_invalid_base_is_rejected() -> None:
    """Ports: ScientificToolsTest.invalidBaseIsRejected"""
    for base in (1, 0, -2):
        with pytest.raises(ValueError, match=r"^Logarithm base must be > 0 and not 1$"):
            tools.log(8, base)


def test_non_finite_input_is_rejected() -> None:
    """Ports: ScientificToolsTest.nonFiniteInputIsRejected"""
    calls: list[Callable[[], float]] = [
        lambda: tools.sqrt(math.nan),
        lambda: tools.sqrt(math.inf),
        lambda: tools.ln(math.inf),
        lambda: tools.log(8, math.nan),
    ]
    for call in calls:
        with pytest.raises(ArithmeticError):
            call()


def test_log_of_one_in_a_base_below_one_is_negative_zero_as_in_java() -> None:
    """Math.rint keeps the sign of -0.0, so Java returns -0.0 here; the port does too."""
    assert java_double_str(tools.log(1, 0.5)) == "-0.0"


def test_every_tool_is_annotated_read_only() -> None:
    assert [t.name for t in tools.TOOLS] == ["ln", "log", "log10", "sqrt"]
    assert all(t.hints == READ_ONLY for t in tools.TOOLS)


def test_exact_power_is_found_where_c_pow_rounds_differently() -> None:
    """9^17 lies halfway between two doubles; Java's Math.pow and the port round it the same
    way, so log recognises the exact power (Java: 17.0) and the neighbour is not one."""
    assert tools.log(16677181699666568, 9) == 17.0
    assert java_double_str(tools.log(16677181699666570, 9)) == "16.999999999999996"
