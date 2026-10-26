"""UI Provider Abstraction - Fixes CLI/GUI mixing"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

class UIProvider(ABC):
    @abstractmethod
    def ask_choice(self, prompt: str, choices: list[str]) -> str: pass
    @abstractmethod
    def ask_input(self, prompt: str, default: str = "") -> str: pass
    @abstractmethod
    def show_message(self, message: str, level: str = "info") -> None: pass
    @abstractmethod
    def confirm(self, message: str) -> bool: pass

class ConsoleUIProvider(UIProvider):
    def ask_choice(self, prompt: str, choices: list[str]) -> str:
        print(f"\n{prompt}")
        return input("\nChoose Action: ").strip()
    def ask_input(self, prompt: str, default: str = "") -> str:
        return input(f"{prompt}: ").strip() or default
    def show_message(self, message: str, level: str = "info") -> None:
        print(f"[{level}] {message}")
    def confirm(self, message: str) -> bool:
        return input(f"{message} (y/n): ").lower() in ("y","yes")

class GUIUIProvider(UIProvider):
    def ask_choice(self, prompt: str, choices: list[str]) -> str:
        return "1"
    def ask_input(self, prompt: str, default: str = "") -> str:
        return default
    def show_message(self, message: str, level: str = "info") -> None:
        try:
            from modules.core.logger import get_logger
            get_logger("gui").info(message)
        except: pass
    def confirm(self, message: str) -> bool:
        return False

def get_ui_provider() -> UIProvider:
    if os.getenv("TELECOM_GUI_MODE") == "1":
        return GUIUIProvider()
    return ConsoleUIProvider()

_ui_provider = None
def get_active_ui_provider() -> UIProvider:
    global _ui_provider
    if _ui_provider is None:
        _ui_provider = get_ui_provider()
    return _ui_provider
