"""The basic calculator's nine tools (port of ``CalculatorTools.java``).

Every tool takes JSON numbers as doubles. A ``ValueError`` or ``ArithmeticError`` becomes the
tool's error result, so the connection survives bad input. The arithmetic follows Java's
``double`` rules, which differ from Python's in a few places noted below.
"""

import math

from simple_mcp_calculator.common.javafmt import java_double_str, java_rint
from simple_mcp_calculator.common.tool_server import READ_ONLY, Param, ServerSpec, Tool

MAX_FACTORIAL = 20
"""20! is the largest factorial that fits in a Java ``long``."""

MAX_EXACT_WHOLE_NUMBER = 2**53
"""Largest whole number a double represents exactly."""

_MILLER_RABIN_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
"""The first 12 primes make Miller-Rabin exact for every n below 3.1e23 (so every n < 2^64),
far beyond 2^53."""


def _finite(result: float) -> float:
    """Overflow (10 ^ 400) and undefined results (-8 ^ 0.5) would otherwise reach the client as
    "Infinity" or "NaN" in a successful result."""
    if math.isnan(result):
        raise ArithmeticError("Result is undefined")
    if math.isinf(result):
        raise ArithmeticError("Result is too large")
    return result


def _nonzero(divisor: float) -> None:
    if divisor == 0:
        raise ValueError("Division by zero")


def whole_number(n: float) -> int:
    """Integer tools take a number so that 7.5 is rejected instead of silently truncated to 7.
    Beyond 2^53 a double can't hold every whole number exactly, so those are rejected too."""
    if n != java_rint(n):
        raise ValueError(f"Not a whole number: {java_double_str(n)}")
    if abs(n) > MAX_EXACT_WHOLE_NUMBER:
        raise ValueError(f"Whole number out of range (|n| <= 2^53): {java_double_str(n)}")
    return int(n)


def java_pow(a: float, b: float) -> float:
    """``Math.pow``. Python's ``math.pow`` raises where Java returns an infinity or NaN, and
    returns 1.0 for ``1 ^ NaN`` and ``(±1) ^ ±Infinity``, which Java defines as NaN."""
    if math.isnan(b) or (abs(a) == 1 and math.isinf(b)):
        return math.nan
    try:
        return math.pow(a, b)
    except OverflowError:
        return math.inf
    except ValueError:
        # 0 to a negative power is infinite; a negative base to a fractional power is NaN.
        return math.inf if a == 0 else math.nan


def add(a: float, b: float) -> float:
    return _finite(a + b)


def subtract(a: float, b: float) -> float:
    return _finite(a - b)


def multiply(a: float, b: float) -> float:
    return _finite(a * b)


def divide(a: float, b: float) -> float:
    _nonzero(b)
    return _finite(a / b)


def remainder(a: float, b: float) -> float:
    """Java's ``a % b`` on doubles (the sign follows the dividend). Like the Java tool, the
    result is not checked for finiteness: ``Infinity % 2`` is ``NaN``."""
    _nonzero(b)
    try:
        return math.fmod(a, b)
    except ValueError:
        return math.nan


def exponent(a: float, b: float) -> float:
    return _finite(java_pow(a, b))


def factorial(n: float) -> int:
    value = whole_number(n)
    if not 0 <= value <= MAX_FACTORIAL:
        raise ValueError(f"Factorial is only defined here for 0 to {MAX_FACTORIAL}")
    return math.factorial(value)


def is_prime(n: float) -> bool:
    """Deterministic Miller-Rabin: the same answers as the Java tool's trial division, in
    O(log n) steps instead of up to 47 million near 2^53."""
    value = whole_number(n)
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    d, s = value - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for base in _MILLER_RABIN_BASES:
        if base % value == 0:
            continue
        x = pow(base, d, value)
        if x in (1, value - 1):
            continue
        for _ in range(s - 1):
            x = x * x % value
            if x == value - 1:
                break
        else:
            return False
    return True


def parity(n: float) -> str:
    return "even" if whole_number(n) % 2 == 0 else "odd"


_A, _B = "First operand", "Second operand"

# Every tool is a pure function, so each is annotated read-only, idempotent and closed-world.
# The Java server sends Spring's defaults (destructive, open-world) instead; this port marks
# them as the scientific server's tools are, by the user's decision (design doc, Open questions).
# Listed in the order the Java server lists them (alphabetical).
TOOLS = (
    Tool(
        "add",
        "Add two numbers: a + b",
        (Param("a", _A), Param("b", _B)),
        add,
        READ_ONLY,
    ),
    Tool(
        "divide",
        "Divide the first number by the second: a / b. Fails if b is 0",
        (Param("a", "Dividend"), Param("b", "Divisor (must not be 0)")),
        divide,
        READ_ONLY,
    ),
    Tool(
        "exponent",
        "Raise the first number to the power of the second: a ^ b. "
        "Fails if the result is not a finite number",
        (Param("a", "Base"), Param("b", "Exponent")),
        exponent,
        READ_ONLY,
    ),
    Tool(
        "factorial",
        f"Factorial of a whole number: n!. Fails unless 0 <= n <= {MAX_FACTORIAL}",
        (Param("n", f"Whole number from 0 to {MAX_FACTORIAL}"),),
        factorial,
        READ_ONLY,
    ),
    Tool(
        "isPrime",
        "Whether a whole number is prime. Returns true or false",
        (Param("n", "Whole number to test"),),
        is_prime,
        READ_ONLY,
    ),
    Tool(
        "multiply",
        "Multiply two numbers: a * b",
        (Param("a", "First factor"), Param("b", "Second factor")),
        multiply,
        READ_ONLY,
    ),
    Tool(
        "parity",
        'Whether a whole number is even or odd. Returns "even" or "odd"',
        (Param("n", "Whole number to test"),),
        parity,
        READ_ONLY,
    ),
    Tool(
        "remainder",
        "Remainder of dividing the first number by the second: a % b. Fails if b is 0",
        (Param("a", "Dividend"), Param("b", "Divisor (must not be 0)")),
        remainder,
        READ_ONLY,
    ),
    Tool(
        "subtract",
        "Subtract the second number from the first: a - b",
        (Param("a", "Number to subtract from"), Param("b", "Number to subtract")),
        subtract,
        READ_ONLY,
    ),
)

SPEC = ServerSpec(
    name="calculator-mcp-server",
    version="1.0.0",
    instructions=(
        "Calculator tools: add, subtract, multiply, divide, remainder and exponent on two numbers"
        " (a, b); factorial, isPrime and parity (even/odd) on one whole number (n)."
    ),
    tools=TOOLS,
)
