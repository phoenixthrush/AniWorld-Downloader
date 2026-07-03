import logging
import os
import tempfile
from pathlib import Path

_global_logger = None

# ANSI color codes for console output
RESET = "\033[0m"

COLORS = {
    logging.DEBUG: "\033[36m",  # Cyan
    logging.INFO: "\033[32m",  # Green
    logging.WARNING: "\033[33m",  # Yellow
    logging.ERROR: "\033[31m",  # Red
    logging.CRITICAL: "\033[41m",  # Red background
}

TIME_COLOR = "\033[35m"  # Magenta
FUNC_COLOR = "\033[34m"  # Blue
MSG_COLOR = "\033[37m"  # White/Gray


class ColorFormatter(logging.Formatter):
    """Formatter for colored stdout logs."""

    def format(self, record):
        orig_levelname = record.levelname
        orig_msg = record.msg
        orig_args = record.args
        orig_func_info = getattr(record, "func_info", None)
        orig_message = getattr(record, "message", None)

        try:
            level_color = COLORS.get(record.levelno, RESET)
            record.levelname = f"{level_color}{record.levelname}{RESET}"

            cwd = os.getcwd()
            rel_path = os.path.relpath(record.pathname, cwd)
            record.func_info = (
                f"{FUNC_COLOR}{rel_path}:{record.lineno}:{record.funcName}{RESET}"
            )

            record.msg = f"{MSG_COLOR}{record.getMessage()}{RESET}"
            record.args = None

            formatted = super().format(record)

            # Color timestamp
            parts = formatted.split(" - ", 1)
            if len(parts) == 2:
                timestamp, rest = parts
                formatted = f"{TIME_COLOR}{timestamp}{RESET} - {rest}"

            return formatted
        finally:
            record.levelname = orig_levelname
            record.msg = orig_msg
            record.args = orig_args
            if orig_func_info is not None:
                record.func_info = orig_func_info
            elif hasattr(record, "func_info"):
                del record.func_info
            if orig_message is not None:
                record.message = orig_message
            elif hasattr(record, "message"):
                del record.message


class PlainFormatter(logging.Formatter):
    """Formatter for plain file logs (no color)."""

    def format(self, record):
        orig_func_info = getattr(record, "func_info", None)
        try:
            cwd = os.getcwd()
            rel_path = os.path.relpath(record.pathname, cwd)
            record.func_info = f"{rel_path}:{record.lineno}:{record.funcName}"
            return super().format(record)
        finally:
            if orig_func_info is not None:
                record.func_info = orig_func_info
            elif hasattr(record, "func_info"):
                del record.func_info


# TODO: This does not respect env debug mode
def get_logger(name=__name__, level=None):
    """Return a logger that writes to both file and stdout, colored in console."""
    global _global_logger
    if _global_logger is None:
        _global_logger = logging.getLogger("aniworld")
        _global_logger.handlers.clear()

        log_format = "%(asctime)s - %(levelname)s - %(func_info)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"

        # ------------------ File handler ------------------ #
        temp_dir = tempfile.gettempdir()
        log_file_path = Path(temp_dir) / "aniworld.log"
        file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
        file_handler.setFormatter(PlainFormatter(log_format, datefmt=date_format))
        _global_logger.addHandler(file_handler)

        # ------------------ Console handler ------------------ #
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColorFormatter(log_format, datefmt=date_format))
        _global_logger.addHandler(console_handler)

        # Determine log level from env or argument
        env_debug = os.getenv("ANIWORLD_DEBUG_MODE", "0")
        level = level or (logging.DEBUG if env_debug == "1" else logging.WARNING)
        _global_logger.setLevel(level)

        # Reduce noise from urllib3
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
        logging.getLogger("waitress.queue").setLevel(logging.ERROR)

    return _global_logger
