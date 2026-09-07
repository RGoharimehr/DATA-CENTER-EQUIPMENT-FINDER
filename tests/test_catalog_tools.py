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


def test_export_web_catalog_matches_packaged_csv(tmp_path) -> None:
    import json

    from datacenter_equipment_finder.catalog import EquipmentCatalog
    from datacenter_equipment_finder.catalog_tools import export_web_catalog

    target = tmp_path / "equipment_catalog.json"
    count = export_web_catalog(EquipmentCatalog.default_csv_path(), target)

    rows = json.loads(target.read_text(encoding="utf-8"))
    assert count == len(rows) == len(EquipmentCatalog.from_csv().components)
    assert rows[0]["part_number"]


def test_docs_site_catalog_is_in_sync() -> None:
    import json
    from pathlib import Path

    from datacenter_equipment_finder.catalog import EquipmentCatalog

    docs_json = Path(__file__).resolve().parents[1] / "docs" / "equipment_catalog.json"
    if not docs_json.exists():  # pragma: no cover - docs site is optional
        return
    published = json.loads(docs_json.read_text(encoding="utf-8"))
    assert len(published) == len(EquipmentCatalog.from_csv().components), (
        "docs/equipment_catalog.json is stale; run 'dcef export-web-catalog'"
    )
