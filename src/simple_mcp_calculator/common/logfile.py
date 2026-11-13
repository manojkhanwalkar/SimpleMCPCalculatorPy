"""The servers' private log file.

Stdout carries the MCP protocol, so a server logs to a file: ``~/.calculator-mcp/<name>``, created
owner-only (directory 0700, file 0600) so other local users can neither read it nor pre-create
it. If the home directory is not writable (e.g. a container user with HOME=/), a fresh private
temp directory is used instead, so startup never fails over logging. As in the Java servers,
``--logging.file.name=<path>`` wins, and the file rolls over at 10 MB keeping 7 old files
(Spring Boot's defaults), so it never grows without bound.
"""

import logging
import logging.handlers
import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

LOG_DIR_NAME = ".calculator-mcp"
OPTION = "--logging.file.name="
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 7
_FORMAT = "%(asctime)s %(levelname)-5s %(process)d --- [%(threadName)s] %(name)s : %(message)s"


def explicit_path(argv: Sequence[str]) -> Path | None:
    """The log file named by ``--logging.file.name=`` (the last one wins).

    Like the Java servers, an environment variable does not override the private default.
    """
    named = [a.removeprefix(OPTION) for a in argv if a.startswith(OPTION)]
    return Path(named[-1]) if named and named[-1] else None


class PrivateRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating log whose every file, including those it opens after a rollover, is 0600."""

    def _open(self):  # type: ignore[no-untyped-def]  # signature of the stdlib private hook
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        return open(fd, self.mode, encoding=self.encoding, errors=self.errors)


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


def _file_handler(path: Path) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = PrivateRotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    return handler


def configure_logging(file_name: str, argv: Sequence[str], home: Path | None = None) -> Path | None:
    """Send the root logger to the server's log file (never to stdout) and return its path.

    An explicit file that can't be opened falls back to the private default, as Logback keeps
    the Java server running; with no usable file at all, logging is switched off.
    """
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
        old.close()
    root.setLevel(logging.INFO)
    explicit = explicit_path(argv)
    candidates = [explicit] if explicit else []
    for path in [*candidates, private_log_file(file_name, home)]:
        if path is None:
            continue
        try:
            root.addHandler(_file_handler(path))
        except OSError as e:
            print(f"Cannot log to {path}: {e}", file=sys.stderr)
            continue
        return path
    root.addHandler(logging.NullHandler())
    return None
