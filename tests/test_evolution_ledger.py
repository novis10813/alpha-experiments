import tempfile
import unittest
from pathlib import Path


class EvolutionLedgerTests(unittest.TestCase):
    def test_family_holdout_lock_survives_run_id_change(self):
        from evolution.ledger import acquire_holdout_lock
        from evolution.ledger import complete_holdout
        from evolution.ledger import register_family

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register_family(root, "trend-flow-v1", "trend and flow agree", "BTCUSDT.BINANCE", "run-1")
            acquire_holdout_lock(root, "trend-flow-v1", "BTCUSDT.BINANCE", "run-1", "c1")
            complete_holdout(root, "trend-flow-v1", "BTCUSDT.BINANCE", "run-1", "c1")
            register_family(root, "trend-flow-v1", "trend and flow agree", "BTCUSDT.BINANCE", "run-2")
            with self.assertRaisesRegex(RuntimeError, "research family"):
                acquire_holdout_lock(root, "trend-flow-v1", "BTCUSDT.BINANCE", "run-2", "c2")

    def test_family_hypothesis_is_immutable(self):
        from evolution.ledger import register_family

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register_family(root, "trend-v1", "first", "BTCUSDT.BINANCE", "run-1")
            with self.assertRaisesRegex(ValueError, "cannot change"):
                register_family(root, "trend-v1", "second", "BTCUSDT.BINANCE", "run-2")


if __name__ == "__main__":
    unittest.main()
