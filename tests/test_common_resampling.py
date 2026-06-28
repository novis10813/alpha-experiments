import unittest
from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    ts_event: int
    value: float


class CommonResamplingTests(unittest.TestCase):
    def test_resample_last_by_bucket_uses_bucket_end_and_fills_empty_buckets(self):
        from common.resampling import resample_last_by_bucket

        rows = resample_last_by_bucket(
            [Row(1_100_000_000, 1), Row(1_900_000_000, 2), Row(3_100_000_000, 3)],
            1,
            lambda row: row.ts_event,
            lambda row, ts_event: Row(ts_event, row.value),
        )

        self.assertEqual([row.ts_event for row in rows], [2_000_000_000, 3_000_000_000, 4_000_000_000])
        self.assertEqual([row.value for row in rows], [2, 2, 3])


if __name__ == "__main__":
    unittest.main()

