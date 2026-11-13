"""Java number semantics the MCP contract depends on.

The Java servers write results with ``Double.toString`` and round with ``Math.rint``; both differ
from Python's ``repr`` and ``round``. These functions reproduce Java's behaviour exactly.
"""

import math
from decimal import Decimal

# Double.toString switches to computerized scientific notation outside [1e-3, 1e7).
_PLAIN_MIN = 1e-3
_PLAIN_MAX = 1e7


def _significant_digits(x: float) -> tuple[str, int]:
    """Return the digits of ``x`` (no leading or trailing zeros) and the decimal exponent of the
    first one, using the shortest representation that round-trips, as Java does.

    Java prints at least two significant digits: when the shortest form has one, it uses the
    two-digit decimal closest to the exact value (``5e-324`` -> ``4.9E-324``).
    """
    _, digits, exponent = Decimal(repr(abs(x))).normalize().as_tuple()
    if not isinstance(exponent, int):  # pragma: no cover - callers pass finite values
        raise ValueError(f"not finite: {x!r}")
    if len(digits) == 1:
        mantissa, exp = f"{abs(x):.1e}".split("e")
        two = mantissa.replace(".", "")
        text = two.rstrip("0") or "0"
        return text, int(exp)
    text = "".join(map(str, digits))
    return text, exponent + len(digits) - 1


def java_double_str(x: float) -> str:
    """Format ``x`` exactly as Java's ``Double.toString(x)``."""
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    sign = "-" if math.copysign(1.0, x) < 0 else ""
    if x == 0:
        return f"{sign}0.0"
    digits, exp = _significant_digits(x)
    if _PLAIN_MIN <= abs(x) < _PLAIN_MAX:
        if exp >= 0:
            whole = digits[: exp + 1].ljust(exp + 1, "0")
            fraction = digits[exp + 1 :] or "0"
        else:
            whole = "0"
            fraction = "0" * (-exp - 1) + digits
        return f"{sign}{whole}.{fraction}"
    return f"{sign}{digits[0]}.{digits[1:] or '0'}E{exp}"


def java_rint(x: float) -> float:
    """``Math.rint``: round half to even, keeping the sign (``rint(-0.3)`` is ``-0.0``)."""
    if not math.isfinite(x):
        return x
    return math.copysign(float(round(x)), x)
