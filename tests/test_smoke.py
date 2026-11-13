"""Smoke test: the package imports and reports the installed distribution's version."""

from importlib.metadata import version

import simple_mcp_calculator


def test_package_reports_its_version() -> None:
    assert simple_mcp_calculator.__version__ == version("simple-mcp-calculator")
