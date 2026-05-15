import logging

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
