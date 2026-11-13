"""Java ``Math`` functions whose results differ from Python's ``math`` module."""

import math

_EXACT_MAX_EXPONENT = 64
_EXACT_MAX_BITS = 1100
"""Beyond about 2^1024 the result overflows anyway; 1100 bits leaves room for rounding."""


def _exact_integer_power(a: float, b: float) -> float | None:
    """``a ** b`` correctly rounded, for a whole ``a`` and a whole ``0 <= b <= 64`` whose exact
    value is cheap. (For negative exponents Java's ``Math.pow`` is not correctly rounded and
    agrees with C's ``pow`` instead.)

    C's ``pow`` and Java's ``Math.pow`` can round an exact result that falls halfway between two
    doubles differently (``9 ** 17``); computing it exactly and rounding once agrees with Java.
    """
    if not (a.is_integer() and b.is_integer()) or a == 0 or not 0 <= b <= _EXACT_MAX_EXPONENT:
        return None
    base, exponent = int(a), int(b)
    if base.bit_length() * exponent > _EXACT_MAX_BITS:
        return None
    value = base**exponent
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def java_pow(a: float, b: float) -> float:
    """``Math.pow``. Python's ``math.pow`` raises where Java returns an infinity or NaN, returns
    1.0 for ``1 ^ NaN`` and ``(±1) ^ ±Infinity``, which Java defines as NaN, and can round an
    exact integer power differently."""
    if math.isnan(b) or (abs(a) == 1 and math.isinf(b)):
        return math.nan
    if math.isfinite(a) and math.isfinite(b):
        exact = _exact_integer_power(a, b)
        if exact is not None:
            return exact
    try:
        return math.pow(a, b)
    except OverflowError:
        # A negative base to an odd whole power overflows to -Infinity, as in Java.
        odd = b.is_integer() and abs(b) < 2**53 and int(b) % 2 == 1
        return -math.inf if a < 0 and odd else math.inf
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
