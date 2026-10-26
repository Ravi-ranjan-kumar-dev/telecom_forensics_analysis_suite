# Centralized Configuration Management for EthicalArmor
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from pydantic_settings import BaseSettings  # type: ignore
    _HAS_PYDANTIC_SETTINGS = True
except ImportError:
    _HAS_PYDANTIC_SETTINGS = False


@dataclass
class Settings:
    app_name: str = 'EthicalArmor - Telecom & Digital Forensics Suite'
    secret_key: str = field(default_factory=lambda: os.getenv('SECRET_KEY', ''))
    api_url: str = field(default_factory=lambda: os.getenv('TELECOM_API_URL', 'http://localhost:8000'))
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
    )
    gui_fast_mode: bool = field(
        default_factory=lambda: os.getenv('TELECOM_GUI_FAST_MODE', '1') == '1'
    )
    csv_chunk_size: int = field(
        default_factory=lambda: int(os.getenv('EA_CSV_CHUNK_SIZE', '100000'))
    )


settings = Settings()
