"""The servers' private log file (port of usePrivateLogFile in the Java server applications)."""

import logging
import os
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from simple_mcp_calculator.common import logfile


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_creates_owner_only_directory_and_file(tmp_path: Path) -> None:
    path = logfile.private_log_file("server.log", home=tmp_path)
    assert path == tmp_path / ".calculator-mcp" / "server.log"
    assert _mode(path.parent) == 0o700
    assert _mode(path) == 0o600


def test_tightens_permissions_left_open_by_an_older_version(tmp_path: Path) -> None:
    directory = tmp_path / ".calculator-mcp"
    directory.mkdir(mode=0o755)
    old = directory / "server.log"
    old.write_text("old\n")
    old.chmod(0o644)
    path = logfile.private_log_file("server.log", home=tmp_path)
    assert path == old
    assert _mode(directory) == 0o700
    assert _mode(old) == 0o600
    assert old.read_text() == "old\n"


def test_refuses_a_symlinked_log_and_falls_back_to_temp(tmp_path: Path) -> None:
    directory = tmp_path / ".calculator-mcp"
    directory.mkdir(mode=0o700)
    target = tmp_path / "elsewhere.txt"
    target.write_text("")
    (directory / "server.log").symlink_to(target)
    path = logfile.private_log_file("server.log", home=tmp_path)
    assert path is not None
    assert path.parent != directory
    assert path.name == "server.log"
    assert _mode(path.parent) == 0o700


def test_falls_back_to_private_temp_dir_when_home_is_unusable(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "home-is-a-file"
    not_a_dir.write_text("")
    path = logfile.private_log_file("server.log", home=not_a_dir)
    assert path is not None
    assert path.parent.name.startswith("calculator-mcp-")
    assert Path(tempfile.gettempdir()) in path.parents
    assert _mode(path.parent) == 0o700


def test_returns_none_when_nothing_is_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_temp(**_: object) -> str:
        raise OSError("no temp dir")

    monkeypatch.setattr(tempfile, "mkdtemp", no_temp)
    not_a_dir = tmp_path / "home-is-a-file"
    not_a_dir.write_text("")
    assert logfile.private_log_file("server.log", home=not_a_dir) is None


def test_explicit_option_wins_last_one_counts() -> None:
    argv = ["--logging.file.name=/a.log", "add", "--logging.file.name=/b.log"]
    assert logfile.explicit_path(argv, env={}) == Path("/b.log")


def test_environment_variable_is_used_when_no_option() -> None:
    assert logfile.explicit_path([], env={"LOGGING_FILE_NAME": "/c.log"}) == Path("/c.log")
    assert logfile.explicit_path([], env={}) is None


def test_configure_logging_writes_to_the_file_not_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "logs" / "explicit.log"
    path = logfile.configure_logging("server.log", [f"--logging.file.name={target}"], env={})
    assert path == target
    logging.getLogger("demo").info("hello file")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "hello file" in target.read_text()
    assert capsys.readouterr().out == ""


def test_configure_logging_goes_silent_without_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logfile, "private_log_file", lambda *_a, **_k: None)
    assert logfile.configure_logging("server.log", [], env={}, home=tmp_path) is None
    assert all(isinstance(h, logging.NullHandler) for h in logging.getLogger().handlers)


def test_default_location_is_the_home_directory(tmp_path: Path) -> None:
    path = logfile.configure_logging("server.log", [], env={}, home=tmp_path)
    assert path == tmp_path / ".calculator-mcp" / "server.log"
    assert os.access(path, os.W_OK)


def test_a_directory_in_place_of_the_log_falls_back_to_temp(tmp_path: Path) -> None:
    (tmp_path / ".calculator-mcp" / "server.log").mkdir(parents=True)
    path = logfile.private_log_file("server.log", home=tmp_path)
    assert path is not None
    assert path.parent.name.startswith("calculator-mcp-")
