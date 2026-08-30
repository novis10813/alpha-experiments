import json
import tempfile
import unittest
from pathlib import Path


class EvolutionDiagnosticTests(unittest.TestCase):
    def test_flat_baseline_has_no_trades_or_costs(self):
        from evolution.backtest import run_candidate

        result = run_candidate(
            "evolution/baselines/flat.py",
            "BTCUSDT.BINANCE",
            _states((100, 101, 99)),
        )
        self.assertEqual(result.metrics.closed_positions, 0)
        self.assertEqual(result.metrics.orders, 0)
        self.assertEqual(result.diagnostics.gross_return, 0)
        self.assertEqual(result.diagnostics.fee_drag, 0)
        self.assertEqual(result.diagnostics.net_return, 0)
        self.assertEqual(result.diagnostics.turnover, 0)
        self.assertIsNone(result.diagnostics.average_holding_seconds)

    def test_buy_and_hold_reconciles_gross_fees_and_net(self):
        from evolution.backtest import run_candidate

        profitable = run_candidate(
            "evolution/baselines/buy_and_hold.py",
            "BTCUSDT.BINANCE",
            _states((100, 101, 102, 103, 104, 105)),
        )
        losing = run_candidate(
            "evolution/baselines/buy_and_hold.py",
            "BTCUSDT.BINANCE",
            _states((105, 104, 103, 102, 101, 100)),
        )
        for result in (profitable, losing):
            diagnostics = result.diagnostics
            self.assertAlmostEqual(
                diagnostics.gross_return - diagnostics.fee_drag,
                diagnostics.net_return,
            )
            self.assertGreater(diagnostics.fee_drag, 0)
            self.assertGreater(diagnostics.turnover, 0)
            self.assertEqual(len(diagnostics.holding_durations_seconds), 1)
            self.assertAlmostEqual(
                diagnostics.average_holding_seconds,
                diagnostics.median_holding_seconds,
            )
            self.assertAlmostEqual(
                diagnostics.average_gross_pnl_per_position
                - diagnostics.average_fee_per_position,
                diagnostics.net_return * 100_000,
            )
        self.assertGreater(profitable.diagnostics.gross_return, 0)
        self.assertLess(losing.diagnostics.gross_return, 0)

    def test_aggregate_payload_combines_folds_and_is_json_deterministic(self):
        from evolution.backtest import run_candidate
        from evolution.diagnostic import _candidate_payload

        folds = [
            run_candidate("evolution/baselines/flat.py", "BTCUSDT.BINANCE", _states((100, 101))),
            run_candidate("evolution/baselines/flat.py", "BTCUSDT.BINANCE", _states((101, 100))),
            run_candidate("evolution/baselines/flat.py", "BTCUSDT.BINANCE", _states((100, 100))),
            run_candidate("evolution/baselines/flat.py", "BTCUSDT.BINANCE", _states((99, 100))),
            run_candidate("evolution/baselines/flat.py", "BTCUSDT.BINANCE", _states((100, 99))),
        ]
        payload = _candidate_payload(folds)
        aggregate = payload["aggregate"]
        self.assertEqual(aggregate["closed_positions"], 0)
        self.assertEqual(aggregate["gross_return"], 0)
        self.assertEqual(aggregate["turnover"], 0)
        first = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        second = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self.assertEqual(first, second)

    def test_discovery_split_guard_rejects_validation_and_holdout_before_io(self):
        from evolution.diagnostic import discovery_split_path

        for split in ("validation", "holdout", "discovery_6"):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "discovery folds only"):
                discovery_split_path(Path("missing"), split, "BTCUSDT.BINANCE")

    def test_cli_parses_diagnose_output_arguments(self):
        from unittest.mock import patch
        from evolution.__main__ import parse_args

        with tempfile.TemporaryDirectory() as directory:
            with patch("sys.argv", [
                "evolution", "diagnose", "--instrument-id", "BTCUSDT.BINANCE",
                "--output-root", directory, "--run-id", "baseline-v1",
            ]):
                args = parse_args()
        self.assertEqual(args.command, "diagnose")
        self.assertEqual(args.run_id, "baseline-v1")


def _states(prices):
    from evolution.market_state import EvolutionMarketState

    values = []
    for index, price in enumerate(prices):
        ts_event = (index + 1) * 60_000_000_000
        values.append(EvolutionMarketState(
            "BTCUSDT.BINANCE", price, price, price, price, 1, 2, 1, 1,
            0.5, 0.5, 0, 0, 0, 0, 0, 0, price - 0.1, price + 0.1, 20,
            ts_event, ts_event + 2,
        ))
    return values


if __name__ == "__main__":
    unittest.main()
