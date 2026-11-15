"""Session-wide test settings."""

import os
import tempfile

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Point HOME at a throwaway directory, so no server started by a test (Python, or a Java
    client's server) writes its log into the real ~/.calculator-mcp/."""
    del config
    os.environ["HOME"] = tempfile.mkdtemp(prefix="calculator-mcp-test-home-")
