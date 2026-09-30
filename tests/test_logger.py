"""Application logs must not also be printed by root handlers."""

import io
import logging

from aniworld.logger import get_logger


def test_app_warning_is_not_duplicated_by_root_logging():
    app_output = io.StringIO()
    root_output = io.StringIO()
    app_handler = logging.StreamHandler(app_output)
    root_handler = logging.StreamHandler(root_output)
    logger = get_logger()
    root = logging.getLogger()
    logger.addHandler(app_handler)
    root.addHandler(root_handler)
    try:
        logger.warning("browse fetch failed")
        assert app_output.getvalue() == "browse fetch failed\n"
        assert root_output.getvalue() == ""
    finally:
        logger.removeHandler(app_handler)
        root.removeHandler(root_handler)
