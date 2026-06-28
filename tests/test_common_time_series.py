import unittest
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    ts_event: int


class CommonTimeSeriesTests(unittest.TestCase):
    def test_ts_event_to_iso_formats_utc(self):
        from common.time_series import ts_event_to_iso

        self.assertEqual(ts_event_to_iso(1_000_000_000), "1970-01-01T00:00:01Z")

    def test_sign_percentile_downsample_and_indices(self):
        from common.time_series import downsample
        from common.time_series import index_at_or_after
        from common.time_series import index_at_or_before
        from common.time_series import percentile
        from common.time_series import sign

        self.assertEqual([sign(-1), sign(0), sign(1)], [-1, 0, 1])
        self.assertEqual(percentile([10, 20, 30, 40], 0.75), 32.5)
        self.assertEqual(downsample([1, 2, 3, 4], 2), [1, 4])
        self.assertEqual(index_at_or_before([10, 20, 30], 25), 1)
        self.assertEqual(index_at_or_after([10, 20, 30], 25), 2)

    def test_require_dense_series_rejects_large_gaps(self):
        from common.time_series import require_dense_series

        with self.assertRaises(RuntimeError):
            require_dense_series([Point(0), Point(3_000_000_000)], 1, "features")


if __name__ == "__main__":
    unittest.main()

