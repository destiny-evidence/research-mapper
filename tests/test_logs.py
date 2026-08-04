import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from research_mapper.logs import (
    _log_dir,
    _prune_old_logs,
    _state_dir_base,
    configure_file_logging,
)


@pytest.fixture
def root_handlers_before():
    """
    Snapshots the root logger's handlers before a test runs, and removes/closes
    whatever the test added afterwards. Diffing against this snapshot (rather than
    filtering globally by handler type) avoids false positives from pytest's own
    logging-capture handlers already attached to the root logger.
    """
    root = logging.getLogger()
    before = set(root.handlers)
    yield before
    for handler in set(root.handlers) - before:
        root.removeHandler(handler)
        handler.close()


# ---------------------------------------------------------------------------
# _state_dir_base — the per-platform branching logic, kept as plain string logic
# (rather than joined via _log_dir's Path) since pathlib in Python 3.13+ refuses
# to instantiate a WindowsPath on a non-Windows system, making the "nt" branch
# untestable via a real Path on this (Linux/macOS) test environment.
# ---------------------------------------------------------------------------


def test_state_dir_base_posix_uses_xdg_state_home_when_set(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.setenv("XDG_STATE_HOME", "/custom/state")
    assert _state_dir_base() == "/custom/state"


def test_state_dir_base_posix_defaults_to_dot_local_state(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert _state_dir_base() == "~/.local/state"


def test_state_dir_base_windows_uses_localappdata_when_set(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    assert _state_dir_base() == "C:/Users/test/AppData/Local"


def test_state_dir_base_windows_defaults_when_localappdata_unset(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert _state_dir_base() == "~/AppData/Local"


def test_log_dir_joins_app_subpath_onto_state_dir_base(monkeypatch):
    monkeypatch.setattr("research_mapper.logs._state_dir_base", lambda: "/custom/state")
    assert _log_dir() == Path("/custom/state/research-mapper/logs")


# ---------------------------------------------------------------------------
# configure_file_logging — must set up a working DEBUG-level file handler when
# possible, and must NEVER raise, even when the log directory can't be created.
# ---------------------------------------------------------------------------


def test_configure_file_logging_attaches_debug_handler(tmp_path, root_handlers_before):
    log_dir = tmp_path / "logs"
    with patch("research_mapper.logs._log_dir", return_value=log_dir):
        log_path = configure_file_logging()

    assert log_path is not None
    assert log_path.parent == log_dir
    assert log_path.exists()
    added = set(logging.getLogger().handlers) - root_handlers_before
    assert len(added) == 1
    (handler,) = added
    assert isinstance(handler, logging.FileHandler)
    assert handler.level == logging.DEBUG


def test_configure_file_logging_returns_none_on_failure(tmp_path, root_handlers_before):
    """
    Regression test: if the log directory can't be created (permissions, read-only
    filesystem, etc.), setup must be skipped silently rather than crashing the app.
    """
    log_dir = tmp_path / "logs"
    with (
        patch("research_mapper.logs._log_dir", return_value=log_dir),
        patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")),
    ):
        log_path = configure_file_logging()

    assert log_path is None
    added = set(logging.getLogger().handlers) - root_handlers_before
    assert added == set()


# ---------------------------------------------------------------------------
# _prune_old_logs — bounds unbounded growth of the log directory.
# ---------------------------------------------------------------------------


def test_prune_old_logs_keeps_only_the_most_recent(tmp_path):
    for i in range(25):
        (tmp_path / f"research-mapper-{i:020d}.log").write_text("x")

    _prune_old_logs(tmp_path, keep=20)

    remaining = sorted(p.name for p in tmp_path.glob("research-mapper-*.log"))
    assert len(remaining) == 20
    assert remaining[0] == f"research-mapper-{5:020d}.log"
    assert remaining[-1] == f"research-mapper-{24:020d}.log"
