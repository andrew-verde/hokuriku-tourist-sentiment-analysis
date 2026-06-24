"""
Small helper for creating a consistent project logger.

This module provides a setup function that creates a logger writing to both
terminal and a daily log file, with consistent formatting. Used throughout
the analysis pipeline to record what the scripts are doing.
"""

import logging
import os
from datetime import datetime


def setup_logger(name: str, log_level=logging.INFO) -> logging.Logger:
    """
    Create a logger that writes to both the terminal and a dated log file.

    Args:
        name: Logger name, usually ``__name__`` from the caller.
        log_level: Minimum level to record.

    Returns:
        A logger instance ready for reuse.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Keep logs in one shared folder so repeated runs land in the same place.
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # One file per day keeps the log history easy to scan and prevents files from
    # growing indefinitely.
    log_file = os.path.join(log_dir, f'analysis_{datetime.now().strftime("%Y%m%d")}.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)

    # Also send the same messages to the terminal while the script runs.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # Use the same line format everywhere so file and console output match.
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Avoid adding duplicate handlers if the caller asks for the same logger twice.
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
