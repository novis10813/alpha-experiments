import tempfile
import unittest
from pathlib import Path


class DownStreakPressureReportTests(unittest.TestCase):
    def test_build_context_screens_costs_and_regimes_for_down_streak_events(self):
        from reports.down_streak_pressure_report import build_down_streak_context

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100",
                        "59000000000,BTCUSDT.BINANCE,99",
                        "61000000000,BTCUSDT.BINANCE,99",
                        "119000000000,BTCUSDT.BINANCE,98",
                        "121000000000,BTCUSDT.BINANCE,98",
                        "179000000000,BTCUSDT.BINANCE,97",
                        "181000000000,BTCUSDT.BINANCE,97",
                        "239000000000,BTCUSDT.BINANCE,96",
                        "241000000000,BTCUSDT.BINANCE,96",
                        "299000000000,BTCUSDT.BINANCE,95",
                        "301000000000,BTCUSDT.BINANCE,95",
                        "359000000000,BTCUSDT.BINANCE,94",
                        "361000000000,BTCUSDT.BINANCE,94",
                        "419000000000,BTCUSDT.BINANCE,96",
                        "421000000000,BTCUSDT.BINANCE,96",
                        "479000000000,BTCUSDT.BINANCE,95",
                        "481000000000,BTCUSDT.BINANCE,95",
                        "539000000000,BTCUSDT.BINANCE,94",
                        "541000000000,BTCUSDT.BINANCE,94",
                        "599000000000,BTCUSDT.BINANCE,93",
                        "601000000000,BTCUSDT.BINANCE,93",
                        "659000000000,BTCUSDT.BINANCE,92",
                    ],
                ),
                encoding="utf-8",
            )
            pressure_path = Path(directory) / "pressure.csv"
            pressure_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "60000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "120000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "180000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "240000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "300000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "360000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "420000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,0.0",
                        "480000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.5",
                        "540000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.5",
                        "600000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.5",
                        "660000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.5",
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
                        "60000000000,BTCUSDT.BINANCE,99,1,10,0,10,0,1,-10,-1,-1,-1",
                        "120000000000,BTCUSDT.BINANCE,98,1,20,0,20,0,1,-20,-1,-1,-1",
                        "180000000000,BTCUSDT.BINANCE,97,1,30,0,30,0,1,-30,-1,-1,-1",
                        "240000000000,BTCUSDT.BINANCE,96,1,40,0,40,0,1,-40,-1,-1,-1",
                        "300000000000,BTCUSDT.BINANCE,95,1,50,0,50,0,1,-50,-1,-1,-1",
                        "360000000000,BTCUSDT.BINANCE,94,1,60,0,60,0,1,-60,-1,-1,-1",
                        "420000000000,BTCUSDT.BINANCE,96,1,70,70,0,1,0,70,1,1,1",
                        "480000000000,BTCUSDT.BINANCE,95,1,80,0,80,0,1,-80,-1,-1,-1",
                        "540000000000,BTCUSDT.BINANCE,94,1,90,0,90,0,1,-90,-1,-1,-1",
                        "600000000000,BTCUSDT.BINANCE,93,1,100,0,100,0,1,-100,-1,-1,-1",
                        "660000000000,BTCUSDT.BINANCE,92,1,110,0,110,0,1,-110,-1,-1,-1",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_down_streak_context(
                price_path,
                pressure_path,
                feature_path,
                horizons_minutes=[1, 3],
                pressure_threshold=0.2,
                cooldown_minutes=[0, 10],
                cost_bps=[0, 10],
                volatility_lookback_minutes=3,
                trend_lookback_minutes=3,
            )

        self.assertEqual(context.instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(context.bar_count, 11)
        self.assertEqual(context.raw_event_count, 2)
        self.assertEqual(context.confirmed_event_count, 2)
        self.assertEqual(context.cooldown_event_counts[0], 2)
        self.assertEqual(context.cooldown_event_counts[10], 1)

        base = next(
            summary
            for summary in context.summaries
            if summary.group == "all_confirmed"
            and summary.horizon_minutes == 1
            and summary.cooldown_minutes == 0
            and summary.cost_bps == 0
        )
        self.assertEqual(base.count, 2)
        self.assertGreater(base.mean_gross_return, 0)
        self.assertEqual(base.mean_net_return, base.mean_gross_return)

        costly = next(
            summary
            for summary in context.summaries
            if summary.group == "all_confirmed"
            and summary.horizon_minutes == 1
            and summary.cooldown_minutes == 0
            and summary.cost_bps == 10
        )
        self.assertAlmostEqual(costly.mean_net_return, costly.mean_gross_return - 0.001)

        density_groups = {
            summary.group
            for summary in context.summaries
            if summary.horizon_minutes == 1 and summary.cost_bps == 0
        }
        self.assertIn("density_high", density_groups)
        self.assertIn("volatility_high", density_groups)
        self.assertIn("trend_down", density_groups)

    def test_render_report_html_contains_screen_data(self):
        from reports.down_streak_pressure_report import build_down_streak_context
        from reports.down_streak_pressure_report import render_down_streak_report_html

        with tempfile.TemporaryDirectory() as directory:
            price_path = Path(directory) / "prices.csv"
            price_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,price",
                        "1000000000,BTCUSDT.BINANCE,100",
                        "59000000000,BTCUSDT.BINANCE,99",
                        "61000000000,BTCUSDT.BINANCE,99",
                        "119000000000,BTCUSDT.BINANCE,98",
                        "121000000000,BTCUSDT.BINANCE,98",
                        "179000000000,BTCUSDT.BINANCE,97",
                        "181000000000,BTCUSDT.BINANCE,97",
                        "239000000000,BTCUSDT.BINANCE,96",
                    ],
                ),
                encoding="utf-8",
            )
            pressure_path = Path(directory) / "pressure.csv"
            pressure_path.write_text(
                "\n".join(
                    [
                        "ts_event,instrument_id,alpha_name,value",
                        "60000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "120000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "180000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
                        "240000000000,BTCUSDT.BINANCE,confirmed_pressure_persistence_1m,-0.4",
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
                        "60000000000,BTCUSDT.BINANCE,99,1,10,0,10,0,1,-10,-1,-1,-1",
                        "120000000000,BTCUSDT.BINANCE,98,1,20,0,20,0,1,-20,-1,-1,-1",
                        "180000000000,BTCUSDT.BINANCE,97,1,30,0,30,0,1,-30,-1,-1,-1",
                        "240000000000,BTCUSDT.BINANCE,96,1,40,0,40,0,1,-40,-1,-1,-1",
                    ],
                ),
                encoding="utf-8",
            )

            context = build_down_streak_context(
                price_path,
                pressure_path,
                feature_path,
                horizons_minutes=[1],
                pressure_threshold=0.2,
                cooldown_minutes=[0],
                cost_bps=[0],
            )
            html = render_down_streak_report_html(context)

        self.assertIn("Down Streak Pressure Screen", html)
        self.assertIn("all_confirmed", html)
        self.assertIn("Plotly.newPlot", html)


if __name__ == "__main__":
    unittest.main()
