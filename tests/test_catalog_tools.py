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


def test_sync_reports_every_url_individually(tmp_path) -> None:
    """A bare 'failed: 14' gives no way to tell a dead link from a blocked agent."""
    import csv as _csv

    from datacenter_equipment_finder.catalog import FIELD_NAMES
    from datacenter_equipment_finder.catalog_tools import _safe_file_name, download_catalogs

    url = "https://example.invalid/datasheets/widget.pdf"
    csv_path = tmp_path / "catalog.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=FIELD_NAMES)
        writer.writeheader()
        writer.writerow({name: "" for name in FIELD_NAMES} | {"part_number": "X", "datasheet_url": url})

    out = tmp_path / "downloads"
    out.mkdir()
    # Pre-place the target so the call resolves without touching the network.
    (out / _safe_file_name(url)).write_bytes(b"%PDF-1.4 stub")

    summary = download_catalogs(csv_path, out)
    assert summary["total"] == 1
    assert summary["skipped"] == 1
    assert [r["url"] for r in summary["results"]] == [url]
    assert summary["results"][0]["status"] == "skipped"
