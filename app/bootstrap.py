"""Application entry points and dependency wiring."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from services.logging_service import configure_logging
from ui.main_window import SpinGUI


def run_gui() -> int:
    """Start the desktop application."""
    configure_logging()
    app = QApplication(sys.argv)
    window = SpinGUI()
    window.show()
    return app.exec()

