"""Path helpers compatible with development and PyInstaller builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def app_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", os.path.abspath(".")))

