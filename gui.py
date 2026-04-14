"""Compatibility entry point for the SpinBot desktop app."""

from __future__ import annotations

import sys

from app.bootstrap import run_gui


if __name__ == "__main__":
    sys.exit(run_gui())

