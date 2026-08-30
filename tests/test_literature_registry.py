import copy
import json
import unittest
from pathlib import Path

from research.literature_registry import REGISTRY_PATH
from research.literature_registry import canonical_source_id
from research.literature_registry import find_source
from research.literature_registry import load_registry
from research.literature_registry import normalize_doi
from research.literature_registry import normalize_persistent_id
from research.literature_registry import validate_registry


class LiteratureRegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def test_normalization_variants(self):
        self.assertEqual(normalize_doi(" DOI:10.1093/JJFINec/nbt003. "), "10.1093/jjfinec/nbt003")
        self.assertEqual(normalize_doi("https://doi.org/10.1080/14697688.2018.1489139"), "10.1080/14697688.2018.1489139")
        self.assertEqual(normalize_persistent_id("https://arxiv.org/abs/2602.00776v1"), "arxiv:2602.00776")
        self.assertEqual(canonical_source_id("10.48550/arXiv.2602.00776"), "arxiv:2602.00776")

    def test_duplicate_doi_detection(self):
        registry = copy.deepcopy(self.registry)
        duplicate = copy.deepcopy(registry["sources"][0])
        duplicate["paper_id"] = "duplicate-paper"
        duplicate["canonical_source_id"] = "doi:10.1016/b978-012374258-2.50006-3"
        duplicate["note_path"] = registry["sources"][1]["note_path"]
        registry["sources"].append(duplicate)
        errors = validate_registry(registry)
        self.assertTrue(any("duplicate DOI or persistent ID" in error for error in errors))

    def test_bad_feature_rejection(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["hypotheses"][0]["primary_features"] = ["not_a_market_state_feature"]
        errors = validate_registry(registry)
        self.assertTrue(any("invalid EvolutionMarketState feature" in error for error in errors))

    def test_missing_note_rejection(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["note_path"] = "docs/research/literature/papers/missing.md"
        errors = validate_registry(registry)
        self.assertIn("missing note: docs/research/literature/papers/missing.md", errors)

    def test_actual_registry_validity(self):
        self.assertEqual(validate_registry(self.registry), [])
        self.assertTrue(REGISTRY_PATH.is_file())
        self.assertEqual(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")), self.registry)

    def test_source_lookup(self):
        source = find_source("https://doi.org/10.1093/jjfinec/nbt003", self.registry)
        self.assertIsNotNone(source)
        self.assertEqual(source["paper_id"], "cont-kukanov-stoikov-2014")
        source = find_source("10.48550/arXiv.2602.00776", self.registry)
        self.assertIsNotNone(source)
        self.assertEqual(source["paper_id"], "bieganowski-slepaczuk-2026")
        self.assertIsNone(find_source("10.1080/14697688.2018.1432883", self.registry))


if __name__ == "__main__":
    unittest.main()
