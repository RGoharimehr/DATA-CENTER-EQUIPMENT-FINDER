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


def test_published_site_does_not_hardcode_the_category_vocabulary() -> None:
    """The site's category list went stale the moment a category was added, hiding
    every quick disconnect from the published finder."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    index = (root / "docs" / "index.html").read_text(encoding="utf-8")
    app = (root / "docs" / "app.js").read_text(encoding="utf-8")

    select = index.split('<select id="category"')[1].split("</select>")[0]
    assert select.count("<option") == 1, "category options must be built from the catalog"
    assert "CATALOG.map((x) => x.category)" in app


def test_published_site_ranks_the_same_way_as_the_engine() -> None:
    from pathlib import Path

    from datacenter_equipment_finder.matching import (
        DISPUTED_PENALTY,
        FLOW_COEFFICIENT_CATEGORIES,
        UNKNOWN_PENALTY,
        UNVERIFIED_PENALTY,
    )

    app = (Path(__file__).resolve().parents[1] / "docs" / "app.js").read_text(encoding="utf-8")
    assert f"UNKNOWN_PENALTY = {UNKNOWN_PENALTY}" in app
    assert f"UNVERIFIED_PENALTY = {UNVERIFIED_PENALTY}" in app
    assert f"DISPUTED_PENALTY = {DISPUTED_PENALTY}" in app
    for category in FLOW_COEFFICIENT_CATEGORIES:
        assert f'"{category}"' in app, f"{category} missing from the site's flow categories"
