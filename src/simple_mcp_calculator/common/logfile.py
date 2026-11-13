"""The servers' private log file.

Stdout carries the MCP protocol, so a server logs to a file: ``~/.calculator-mcp/<name>``, created
owner-only (directory 0700, file 0600) so other local users can neither read it nor pre-create
it. If the home directory is not writable (e.g. a container user with HOME=/), a fresh private
temp directory is used instead, so startup never fails over logging. As in the Java servers,
``--logging.file.name=<path>`` (or the LOGGING_FILE_NAME environment variable) wins.
"""

import logging
import os
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

LOG_DIR_NAME = ".calculator-mcp"
OPTION = "--logging.file.name="
ENV = "LOGGING_FILE_NAME"
_FORMAT = "%(asctime)s %(levelname)-5s %(process)d --- [%(threadName)s] %(name)s : %(message)s"


def explicit_path(argv: Sequence[str], env: Mapping[str, str] = os.environ) -> Path | None:
    """The log file named by ``--logging.file.name=`` (last one wins) or LOGGING_FILE_NAME."""
    named = [a.removeprefix(OPTION) for a in argv if a.startswith(OPTION)]
    if named:
        return Path(named[-1])
    return Path(env[ENV]) if env.get(ENV) else None


def _create_private(directory: Path, file_name: str) -> Path:
    file = directory / file_name
    if os.name != "posix":  # pragma: no cover - no POSIX permissions (Windows)
        directory.mkdir(parents=True, exist_ok=True)
        file.touch(exist_ok=True)
        return file
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Also tightens a directory or log left readable by others.
    directory.chmod(0o700)
    if file.is_symlink():
        raise OSError(f"refusing to log through a symlink: {file}")
    if not file.exists():
        os.close(os.open(file, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600))
    file.chmod(0o600)
    if not os.access(file, os.W_OK) or not stat.S_ISREG(file.lstat().st_mode):
        raise OSError(f"not a writable regular file: {file}")
    return file


def private_log_file(file_name: str, home: Path | None = None) -> Path | None:
    """``~/.calculator-mcp/<file_name>``, else a new private temp directory, else ``None``."""
    try:
        return _create_private((home or Path.home()) / LOG_DIR_NAME, file_name)
    except OSError, RuntimeError:
        pass
    try:
        return _create_private(Path(tempfile.mkdtemp(prefix="calculator-mcp-")), file_name)
    except OSError:
        return None


def configure_logging(
    file_name: str,
    argv: Sequence[str],
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> Path | None:
    """Send the root logger to the server's log file (never to stdout) and return its path.

    With no usable file, logging is switched off rather than risk writing to stdout.
    """
    path = explicit_path(argv, env) or private_log_file(file_name, home)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    if path is None:
        root.addHandler(logging.NullHandler())
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return path
