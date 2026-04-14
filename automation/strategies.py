"""Strategy interfaces for reusable automation flows."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AutomationStrategy(ABC):
    """Pluggable automation behavior executed by an instance runner."""

    name = "base"

    @abstractmethod
    def run(self) -> None:
        """Run until completion, failure or cancellation."""


class SpinCoinStrategy(AutomationStrategy):
    """Default SpinBot strategy backed by the current SpinAutomator flow."""

    name = "spincoin"

    def __init__(self, automator):
        self.automator = automator

    def run(self) -> None:
        self.automator.run()

