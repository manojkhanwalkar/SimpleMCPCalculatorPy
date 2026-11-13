"""Java ``Math`` functions whose results differ from Python's ``math`` module."""

import math


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


def require_finite(result: float) -> float:
    """Reject results Java would print as "Infinity" or "NaN" in a successful result
    (``requireFinite`` in both Java tool classes)."""
    if math.isnan(result):
        raise ArithmeticError("Result is undefined")
    if math.isinf(result):
        raise ArithmeticError("Result is too large")
    return result
