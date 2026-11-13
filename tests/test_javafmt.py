"""java_double_str and java_rint against the JVM's own output."""

import math
import struct
from pathlib import Path

import pytest

from simple_mcp_calculator.common.javafmt import java_double_str, java_rint

FIXTURE = Path(__file__).parent / "data" / "java_doubles.txt"


def _cases() -> list[tuple[float, str, str]]:
    cases = []
    for line in FIXTURE.read_text().splitlines():
        bits, text, rint_text = line.split()
        value = struct.unpack(">d", int(bits, 16).to_bytes(8, "big"))[0]
        cases.append((value, text, rint_text))
    return cases


def test_matches_java_on_5000_random_doubles() -> None:
    """Bit patterns, subnormals and every exponent range, as printed by Double.toString."""
    mismatches = [
        (v, want, java_double_str(v)) for v, want, _ in _cases() if java_double_str(v) != want
    ]
    assert mismatches == []


def test_rint_matches_java_on_5000_random_doubles() -> None:
    mismatches = [(v, want) for v, _, want in _cases() if java_double_str(java_rint(v)) != want]
    assert mismatches == []


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0.0, "0.0"),
        (-0.0, "-0.0"),
        (22.0, "22.0"),
        (3.4, "3.4"),
        (0.001, "0.001"),
        (0.000999, "9.99E-4"),
        (9999999.0, "9999999.0"),
        (1e7, "1.0E7"),
        (1.0000000001e10, "1.0000000001E10"),
        (1e21, "1.0E21"),
        (5e-324, "4.9E-324"),
        (1.7976931348623157e308, "1.7976931348623157E308"),
        (1.2345678901234568e22, "1.2345678901234568E22"),
        (-2.5, "-2.5"),
        (math.inf, "Infinity"),
        (-math.inf, "-Infinity"),
        (math.nan, "NaN"),
    ],
)
def test_known_values(value: float, text: str) -> None:
    """Values seen in the Java servers' golden responses."""
    assert java_double_str(value) == text


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2.5, "2.0"), (3.5, "4.0"), (-0.3, "-0.0"), (-2.5, "-2.0"), (math.inf, "Infinity")],
)
def test_rint_rounds_half_even_and_keeps_sign(value: float, expected: str) -> None:
    assert java_double_str(java_rint(value)) == expected
