import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Row:
    ts_event: int
    value: float


class CommonCsvIoTests(unittest.TestCase):
    def test_readers_sort_points_and_first_column_value(self):
        from common.csv_io import first_column_value
        from common.csv_io import read_alpha_points
        from common.csv_io import read_price_points
        from common.csv_io import read_quote_points
        from common.csv_io import read_trade_feature_points

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            alpha = base / "alpha.csv"
            alpha.write_text(
                "ts_event,instrument_id,alpha_name,value\n2,BTCUSDT.BINANCE,a,-1\n1,BTCUSDT.BINANCE,a,1\n",
                encoding="utf-8",
            )
            price = base / "price.csv"
            price.write_text("ts_event,instrument_id,price\n2,BTC,101\n1,BTC,100\n", encoding="utf-8")
            quote = base / "quote.csv"
            quote.write_text(
                "ts_event,instrument_id,bid,ask,mid,spread,spread_bps\n1,BTC,99,101,100,2,200\n",
                encoding="utf-8",
            )
            features = base / "features.csv"
            features.write_text(
                "ts_event,instrument_id,price,volume,trade_count,buy_trade_count,sell_trade_count,"
                "buy_volume,sell_volume,signed_trade_count,signed_volume,trade_imbalance,volume_imbalance\n"
                "1,BTC,100,2,3,2,1,1.5,0.5,1,1,0.333,0.5\n",
                encoding="utf-8",
            )

            self.assertEqual([point.ts_event for point in read_alpha_points(alpha)], [1, 2])
            self.assertEqual(read_price_points(price)[0].price, 100)
            self.assertEqual(read_quote_points(quote)[0].spread_bps, 200)
            self.assertEqual(read_trade_feature_points(features, "trade_imbalance")[0].flow_value, 0.333)
            self.assertEqual(first_column_value(alpha, "instrument_id"), "BTCUSDT.BINANCE")

    def test_write_dataclass_csv(self):
        from common.csv_io import write_dataclass_csv

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.csv"
            count = write_dataclass_csv([Row(1, 2.5)], output, ["ts_event", "value"])

            self.assertEqual(count, 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "ts_event,value\n1,2.5\n")


if __name__ == "__main__":
    unittest.main()

