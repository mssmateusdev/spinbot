"""Compatibility module for the legacy CLI entry point.

The canonical automation runner now lives in automation.spin_automator.
"""

from __future__ import annotations

from automation.spin_automator import SpinAutomator


if __name__ == "__main__":
    bot = SpinAutomator(device_label="CLI")
    bot.run()

