# Centralized Forensic Logging System with SHA-256 Hash-Chain Audit Support
from __future__ import annotations

import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from modules.core.paths import LOG_DIR

_LOG_DIR = LOG_DIR
_LOG_FILE = _LOG_DIR / 'ethicalarmor_forensic.log'
_LAST_HASH = '0' * 64


def get_forensic_logger(name: str = 'ethicalarmor') -> logging.Logger:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger


def log_hash_chained_event(action: str, detail: str) -> str:
    global _LAST_HASH
    logger = get_forensic_logger('ethicalarmor.audit')
    payload = f'{_LAST_HASH}|{action}|{detail}'
    current_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    _LAST_HASH = current_hash
    logger.info('AUDIT_CHAIN | action=%s | detail=%s | sha256=%s', action, detail, current_hash)
    return current_hash




def setup_global_logging() -> None:
    """Initialize logging under the writable application data directory."""
    get_forensic_logger("ethicalarmor")


def get_logger(name: str = "ethicalarmor") -> logging.Logger:
    return get_forensic_logger(name)
