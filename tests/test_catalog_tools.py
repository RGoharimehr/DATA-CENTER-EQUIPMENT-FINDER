import sqlite3
import tempfile
import unittest
from pathlib import Path

from datacenter_equipment_finder.catalog_tools import build_sqlite_database, list_catalog_urls


class CatalogToolsTests(unittest.TestCase):
    def test_list_catalog_urls(self):
        urls = list_catalog_urls("src/datacenter_equipment_finder/data/equipment_catalog.csv")
        self.assertTrue(urls)
        self.assertTrue(all(u.startswith("http") for u in urls))

    def test_build_sqlite_database(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "catalog.sqlite"
            count = build_sqlite_database(
                "src/datacenter_equipment_finder/data/equipment_catalog.csv",
                db,
            )
            self.assertGreater(count, 0)
            conn = sqlite3.connect(db)
            try:
                rows = conn.execute("SELECT COUNT(*) FROM equipment_catalog").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(rows, count)


if __name__ == "__main__":
    unittest.main()
