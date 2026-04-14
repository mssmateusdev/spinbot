import time
import unittest
from unittest.mock import patch

from automation import spin_automator


class FakeSpinButton:
    def __init__(self):
        self.clicked = False

    def click(self):
        self.clicked = True


class PreAdGuardTests(unittest.TestCase):
    def make_bot(self):
        bot = spin_automator.SpinAutomator.__new__(spin_automator.SpinAutomator)
        bot.device = object()
        bot.device_profile = None
        bot.dry_run = False
        bot.last_action_time = 0
        bot.log = lambda *args, **kwargs: None
        bot.wait = lambda seconds: False
        return bot

    def test_blocks_ad_when_spins_are_available(self):
        bot = self.make_bot()
        with patch.object(spin_automator, "check_spins_status", return_value="HAS_SPINS"):
            self.assertFalse(bot._confirm_ready_for_ad())

    def test_clicks_spin_before_releasing_ad(self):
        bot = self.make_bot()
        spin_button = FakeSpinButton()

        with patch.object(spin_automator, "check_spins_status", side_effect=["NO_SPINS", "NO_SPINS", "NO_SPINS"]):
            with patch.object(spin_automator, "find_spin_button", return_value=spin_button):
                with patch.object(spin_automator, "check_and_dismiss_warning_popup", return_value=False):
                    self.assertTrue(bot._confirm_ready_for_ad())

        self.assertTrue(spin_button.clicked)
        self.assertGreater(bot.last_action_time, 0)


if __name__ == "__main__":
    unittest.main()

