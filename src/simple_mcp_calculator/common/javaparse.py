"""``Double.parseDouble``: the number syntax the Java command-line clients accept.

Python's ``float()`` differs: it accepts ``1_000`` and Unicode whitespace, which Java rejects, and
rejects ``1d``, ``2.5f`` and hexadecimal ``0x1p3``, which Java accepts.
"""

import math
import re

_DIGITS = r"[0-9]+"
_EXP = r"[eE][+-]?[0-9]+"
_DECIMAL = rf"(?:{_DIGITS}(?:\.[0-9]*)?|\.{_DIGITS})(?:{_EXP})?"
_HEX = r"0[xX](?:[0-9a-fA-F]+\.?|[0-9a-fA-F]*\.[0-9a-fA-F]+)[pP][+-]?[0-9]+"
_NUMBER = re.compile(
    rf"(?P<sign>[+-]?)(?:(?P<special>NaN|Infinity)|(?P<hex>{_HEX})[fFdD]?|(?P<dec>{_DECIMAL})[fFdD]?)"
)


def java_parse_double(text: str) -> float:
    """Parse ``text`` as Java's ``Double.parseDouble`` does; ``ValueError`` where Java throws
    ``NumberFormatException``."""
    # String.trim(): strips every character <= U+0020, nothing else.
    match = _NUMBER.fullmatch(text.strip("".join(map(chr, range(0x21)))))
    if match is None:
        raise ValueError(f"not a Java double: {text!r}")
    negative = match["sign"] == "-"
    if match["special"] == "NaN":
        return math.nan
    if match["special"] == "Infinity":
        return -math.inf if negative else math.inf
    value = float.fromhex(match["hex"]) if match["hex"] else float(match["dec"])
    return -value if negative else value


def is_java_double(text: str) -> bool:
    try:
        java_parse_double(text)
    except ValueError:
        return False
    return True
