import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_RETENTION = 20

_ANSI = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[35m",  # magenta
}
_RESET = "\033[0m"


class ColourFormatter(logging.Formatter):
    """
    Custom log formatting & styling.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record and style it.
        :param record:
        :return: String formatted log record.
        """
        colour = _ANSI.get(record.levelno, "")
        return f"{colour}{super().format(record)}{_RESET}"


def _state_dir_base() -> str:
    """
    :return: the platform's local state directory, before joining on the app subpath.
    """
    if os.name == "nt":
        return os.environ.get("LOCALAPPDATA", "~/AppData/Local")
    return os.environ.get("XDG_STATE_HOME", "~/.local/state")


def _log_dir() -> Path:
    """
    :return: the platform's local state directory for research-mapper's log files.
    """
    return Path(_state_dir_base()).expanduser() / "research-mapper" / "logs"


def _prune_old_logs(log_dir: Path, keep: int = _LOG_RETENTION) -> None:
    """
    Deletes the oldest log files in `log_dir`, keeping only the `keep` most recent
    (filenames are zero-padded timestamps, so lexicographic order is chronological order).
    :param log_dir: the directory containing research-mapper log files.
    :param keep: how many of the most recent log files to retain.
    :return: Nothing.
    """
    existing = sorted(log_dir.glob("research-mapper-*.log"))
    for stale in existing[:-keep] if keep else existing:
        stale.unlink(missing_ok=True)


def configure_file_logging() -> Path | None:
    """
    Attaches a DEBUG-level file handler to the root logger, writing to a fresh
    timestamped file per run under the platform's local state directory. Never raises —
    if the directory can't be created or written to, file logging is silently skipped
    and the app continues console-only.
    :return: the log file path if file logging was set up, else None.
    """
    log_dir = _log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        _prune_old_logs(log_dir)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"research-mapper-{timestamp}.log"
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(handler)
    except OSError as exc:
        logger.warning("Could not set up file logging: %s", exc)
        return None
    return log_path
