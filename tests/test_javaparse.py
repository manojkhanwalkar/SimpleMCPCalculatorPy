"""java_parse_double against Double.parseDouble on the JVM (tests/data/java_parse.txt)."""

import json
import math
import struct
from pathlib import Path

import pytest

from simple_mcp_calculator.common.javaparse import is_java_double, java_parse_double

FIXTURE = Path(__file__).parent / "data" / "java_parse.txt"


def _cases() -> list[tuple[str, str]]:
    cases = []
    for line in FIXTURE.read_text().splitlines():
        text, _, result = line.rpartition(" ")
        cases.append((json.loads(text), result))
    return cases


def _bits(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", value))[0], "x")


@pytest.mark.parametrize(("text", "java"), _cases())
def test_matches_double_parse_double(text: str, java: str) -> None:
    if java == "NFE":
        with pytest.raises(ValueError, match="not a Java double"):
            java_parse_double(text)
        assert not is_java_double(text)
        return
    value = java_parse_double(text)
    expected = struct.unpack(">d", int(java, 16).to_bytes(8, "big"))[0]
    if math.isnan(expected):
        assert math.isnan(value)
    else:
        assert _bits(value) == java
    assert is_java_double(text)
