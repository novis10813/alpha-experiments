import tempfile
import unittest
from pathlib import Path


class PressurePersistenceTests(unittest.TestCase):
    def test_build_confirmed_pressure_signals_aggregates_signed_confirmation_by_bucket(self):
        from alphas.pressure_persistence import build_confirmed_pressure_signals

        with tempfile.TemporaryDirectory() as directory:
            alpha_path = Path(directory) / "alpha.csv"
            alpha_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "10000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.8",
                        "20000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,0.4",
                        "30000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.5",
                        "70000000000,BTCUSDT.BINANCE,orderbook_imbalance_depth10,-0.7",
                    ],
                ),
                encoding="utf-8",
            )
            feature_path = Path(directory) / "features.csv"
            feature_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price,volume,trade_count,buy_trade_count,sell_trade_count,"
                        "buy_volume,sell_volume,signed_trade_count,signed_volume,trade_imbalance,volume_imbalance",
                        "10000000000,BTCUSDT.BINANCE,100,1,1,1,0,1,0,1,1,1,1",
                        "20000000000,BTCUSDT.BINANCE,101,1,1,1,0,1,0,1,1,1,1",
                        "30000000000,BTCUSDT.BINANCE,102,1,1,1,0,1,0,1,1,1,1",
                        "70000000000,BTCUSDT.BINANCE,103,1,1,0,1,0,1,-1,-1,-1,-1",
                    ],
                ),
                encoding="utf-8",
            )

            signals = build_confirmed_pressure_signals(
                alpha_path,
                feature_path,
                bucket_seconds=60,
            )

        self.assertEqual([signal.ts_event for signal in signals], [60_000_000_000, 120_000_000_000])
        self.assertEqual([signal.instrument_id for signal in signals], ["BTCUSDT.BINANCE", "BTCUSDT.BINANCE"])
        self.assertEqual(
            [signal.alpha_name for signal in signals],
            ["confirmed_pressure_persistence_1m", "confirmed_pressure_persistence_1m"],
        )
        self.assertAlmostEqual(signals[0].value, 2 / 3)
        self.assertAlmostEqual(signals[1].value, -1.0)

    def test_write_signals_csv_uses_canonical_alpha_shape(self):
        from alphas.pressure_persistence import AlphaSignal
        from alphas.pressure_persistence import write_signals_csv

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pressure.csv"
            rows_written = write_signals_csv(
                [
                    AlphaSignal(
                        ts_event=60_000_000_000,
                        instrument_id="BTCUSDT.BINANCE",
                        alpha_name="confirmed_pressure_persistence_1m",
                        value=0.25,
                    ),
                ],
                output,
            )
            contents = output.read_text(encoding="utf-8")

        self.assertEqual(rows_written, 1)
        self.assertIn("ts_event,instrument_id,alpha_name,value", contents)
        self.assertIn("60000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,0.25", contents)


if __name__ == "__main__":
    unittest.main()
