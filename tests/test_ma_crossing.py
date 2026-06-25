import unittest


class MACrossingExperimentTests(unittest.TestCase):
    def test_catalog_btcusdt_instrument_matches_tick_precision(self):
        from experiments.ma_crossing import build_btcusdt_binance_spot

        instrument = build_btcusdt_binance_spot()

        self.assertEqual(str(instrument.id), "BTCUSDT.BINANCE")
        self.assertEqual(instrument.price_precision, 2)
        self.assertEqual(instrument.size_precision, 5)
        self.assertEqual(str(instrument.size_increment), "0.00001")

    def test_bar_type_is_internal_one_minute_last(self):
        from experiments.ma_crossing import build_bar_type

        bar_type = build_bar_type("BTCUSDT.BINANCE")

        self.assertEqual(str(bar_type), "BTCUSDT.BINANCE-1-MINUTE-LAST-INTERNAL")

    def test_strategy_config_requires_fast_period_less_than_slow_period(self):
        from experiments.ma_crossing import SMACrossConfig
        from experiments.ma_crossing import SMACrossLongOnly
        from experiments.ma_crossing import build_bar_type
        from nautilus_trader.model.identifiers import InstrumentId

        config = SMACrossConfig(
            instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
            bar_type=build_bar_type("BTCUSDT.BINANCE"),
            trade_size="0.00020",
            fast_period=8,
            slow_period=3,
        )

        with self.assertRaises(ValueError):
            SMACrossLongOnly(config)


if __name__ == "__main__":
    unittest.main()
