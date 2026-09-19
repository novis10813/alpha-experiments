import unittest
from unittest.mock import patch

from experiments.open_evolve.policy import Policy, InvalidPolicy
from experiments.open_evolve.runtime import PolicyProcess
from experiments.open_evolve.contracts import PositionState, TargetPosition
from experiments.open_evolve.features import FeatureEngine
from test_open_evolve_pipeline import fixture, FLAT, LIMITS


class WorkerTests(unittest.TestCase):
    def test_worker_only_receives_values_and_has_clean_environment(self):
        _, _, depths, config, *_ = fixture()
        state = FeatureEngine(config).update(depths[0], available_at=depths[0].ts_init, event_ordinal=0).market
        with patch.dict("os.environ", {"CATALOG_S3_SECRET_KEY": "test-secret"}):
            worker = PolicyProcess(Policy(FLAT, LIMITS))
        try:
            self.assertNotEqual(worker.process.pid, __import__("os").getpid())
            self.assertEqual(worker(state, PositionState(0, None, 0, None, False), allow_short=False), TargetPosition.FLAT)
            with open(f"/proc/{worker.process.pid}/environ", "rb") as file:
                self.assertNotIn(b"CATALOG_S3_SECRET_KEY", file.read())
        finally:
            worker.close()
        self.assertIsNotNone(worker.process.poll())

    def test_killed_worker_is_invalid_candidate(self):
        _, _, depths, config, *_ = fixture()
        state = FeatureEngine(config).update(depths[0], available_at=depths[0].ts_init, event_ordinal=0).market
        worker = PolicyProcess(Policy(FLAT, LIMITS))
        try:
            worker.process.kill()
            worker.process.wait()
            with self.assertRaises(InvalidPolicy):
                worker(state, PositionState(0, None, 0, None, False), allow_short=False)
        finally:
            worker.close()


if __name__ == "__main__":
    unittest.main()
