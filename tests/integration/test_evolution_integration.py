import os
import unittest


@unittest.skipUnless(os.environ.get("RUN_EVOLUTION_INTEGRATION") == "1", "opt-in evolution integration")
class EvolutionIntegrationTests(unittest.TestCase):
    def test_sandbox_image_and_catalog_are_available(self):
        from pathlib import Path

        from evolution.sandbox import DEFAULT_IMAGE

        self.assertTrue(Path(".local/evolution-data").exists())
        self.assertTrue(DEFAULT_IMAGE)


if __name__ == "__main__":
    unittest.main()
