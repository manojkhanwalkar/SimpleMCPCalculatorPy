"""The scientific calculator's four tools (port of ``ScientificTools.java``).

Every tool is a pure function, so each is annotated read-only, idempotent and closed-world, as in
Java. A ``ValueError`` or ``ArithmeticError`` becomes the tool's error result.
"""

import math

from simple_mcp_calculator.common.javafmt import java_rint
from simple_mcp_calculator.common.javamath import java_pow, require_finite
from simple_mcp_calculator.common.tool_server import READ_ONLY, Param, ServerSpec, Tool

_EXACT_POWER_TOLERANCE = 1e-9


def _require_positive(x: float) -> None:
    if x <= 0:
        raise ValueError("Logarithm is only defined for x > 0")


def sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("Square root of a negative number")
    # Adding 0.0 turns sqrt(-0.0) = -0.0 into 0.0, as in Java.
    return require_finite(math.sqrt(x) + 0.0)


def ln(x: float) -> float:
    _require_positive(x)
    return require_finite(math.log(x))


def log10(x: float) -> float:
    _require_positive(x)
    return require_finite(math.log10(x))


def log(x: float, base: float) -> float:
    _require_positive(x)
    if base <= 0 or base == 1:
        raise ValueError("Logarithm base must be > 0 and not 1")
    result = require_finite(math.log(x) / math.log(base))
    # ln(x) / ln(base) is a little off for exact powers (log 1000 base 10 = 2.9999999999999996),
    # so return the whole number when base raised to it gives x back exactly.
    whole = java_rint(result)
    exact = abs(result - whole) < _EXACT_POWER_TOLERANCE and java_pow(base, whole) == x
    return whole if exact else result


_X_LOG = "Number to take the logarithm of (must be > 0)"

# Listed in the order the Java server lists them (alphabetical).
TOOLS = (
    Tool(
        "ln",
        "Natural logarithm (base e) of x. Fails unless x > 0",
        (Param("x", _X_LOG),),
        ln,
        READ_ONLY,
    ),
    Tool(
        "log",
        "Logarithm of x in the given base: log_base(x). Fails unless x > 0, base > 0 and base != 1",
        (Param("x", _X_LOG), Param("base", "Base of the logarithm (must be > 0 and not 1)")),
        log,
        READ_ONLY,
    ),
    Tool(
        "log10",
        "Base-10 logarithm of x. Fails unless x > 0",
        (Param("x", _X_LOG),),
        log10,
        READ_ONLY,
    ),
    Tool(
        "sqrt",
        "Square root of x. Fails if x is negative",
        (Param("x", "Number to take the square root of (must not be negative)"),),
        sqrt,
        READ_ONLY,
    ),
)

SPEC = ServerSpec(
    name="scientific-calculator-mcp-server",
    version="1.0.0",
    instructions=(
        "Scientific calculator tools: sqrt (square root), ln (natural log), log10, and log"
        " (logarithm of x in any base)."
    ),
    tools=TOOLS,
)
