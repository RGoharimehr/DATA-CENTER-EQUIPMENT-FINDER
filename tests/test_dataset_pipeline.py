import tempfile
import unittest
from pathlib import Path

from datacenter_equipment_finder.dataset_pipeline import build_catalog_from_vendor_sources


class DatasetPipelineTests(unittest.TestCase):
    def test_build_catalog_from_vendor_sources(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "equipment_catalog.csv"
            errors = build_catalog_from_vendor_sources(
                "src/datacenter_equipment_finder/data/vendors",
                out,
            )
            self.assertEqual(errors, [])
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
