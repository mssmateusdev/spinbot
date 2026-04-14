import unittest
from pathlib import Path

from services.stats_store import StatsStore


class StatsStoreTests(unittest.TestCase):
    def test_update_and_read_profit(self):
        stats_file = Path("tests/.tmp_stats_store_runtime.json")
        store = StatsStore(
            stats_file=str(stats_file),
            reports_dir="tests",
            save_interval=0,
        )
        store.update_profit("user@example.com", 123)

        self.assertEqual(store.get_profit("user@example.com"), 123)
        self.assertEqual(store.get_all_stats(), {"user@example.com": 123})


if __name__ == "__main__":
    unittest.main()
