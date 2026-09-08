import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdf_fixture import write_text_pdf

from datacenter_equipment_finder.assistant import AssistantConfig
from datacenter_equipment_finder.pdf_catalog import build_database_from_pdf, extract_catalog_rows_from_pdf, extract_pdf_text


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


_SAMPLE_DIR = tempfile.mkdtemp(prefix="dcef-pdf-tests-")


def _sample_pdf() -> str:
    """A real PDF on disk, so the parsing path is genuinely exercised."""
    return str(
        write_text_pdf(
            Path(_SAMPLE_DIR) / "sample.pdf",
            ["Parker valve catalog", "S4A 20 mm", "C-609-S 1-1/8 in ODF"],
        )
    )


class PdfCatalogTests(unittest.TestCase):
    def test_extract_pdf_text_reads_pages(self):
        fake_reader = type("Reader", (), {"pages": [_FakePage("Page 1"), _FakePage("Page 2")]})()
        with patch("datacenter_equipment_finder.pdf_catalog.PdfReader", return_value=fake_reader):
            text = extract_pdf_text(_sample_pdf())
        self.assertIn("Page 1", text)
        self.assertIn("Page 2", text)

    def test_extract_catalog_rows_from_pdf_uses_local_model(self):
        fake_reader = type("Reader", (), {"pages": [_FakePage("Parker valve catalog text")]})()
        payload = {
            "response": json.dumps(
                {
                    "rows": [
                        {
                            "brand": "Parker",
                            "category": "valve",
                            "component_subtype": "check valve",
                            "series_name": "CK2",
                            "component_name": "Check Valve CK2 1-1/4",
                            "nominal_size_mm": "32",
                            "nominal_size_inch": "1.25",
                            "flow_coefficient_type": "cv",
                            "flow_coefficient_value": "19.0",
                            "capacity_kw": "",
                            "capacity_tons": "",
                            "connection_type": "SW",
                            "connection_standard": "ASME B16.11",
                            "material": "Steel",
                            "pressure_rating_bar": "40",
                            "max_temperature_c": "121",
                            "coolant_compatibility": "R134a/R404A",
                            "estimated_price_usd": "",
                            "install_connection_time_min": "",
                            "part_number": "CK2-32",
                            "source_catalog": "PDF",
                            "source_page": "1",
                            "datasheet_url": "https://example.com/catalog.pdf",
                            "baseline_references": "Test",
                        }
                    ]
                }
            )
        }
        with patch("datacenter_equipment_finder.pdf_catalog.PdfReader", return_value=fake_reader), patch(
            "datacenter_equipment_finder.pdf_catalog.urlopen",
            return_value=_FakeResponse(payload),
        ):
            rows = extract_catalog_rows_from_pdf(
                _sample_pdf(),
                config=AssistantConfig(local_endpoint="http://127.0.0.1:11434/api/generate", local_model="llama3.1"),
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["part_number"], "CK2-32")
        self.assertEqual(rows[0]["component_subtype"], "check_valve")
        self.assertEqual(rows[0]["flow_coefficient_type"], "Cv")

    def test_build_database_from_pdf_writes_sqlite(self):
        fake_reader = type("Reader", (), {"pages": [_FakePage("Supermicro CDU catalog text")]})()
        payload = {
            "response": json.dumps(
                {
                    "rows": [
                        {
                            "brand": "Supermicro",
                            "category": "cdu",
                            "component_subtype": "in_rack_cdu",
                            "series_name": "In-Rack CDU",
                            "component_name": "Rack-integrated CDU",
                            "nominal_size_mm": "32",
                            "nominal_size_inch": "1.25",
                            "flow_coefficient_type": "",
                            "flow_coefficient_value": "",
                            "capacity_kw": "250",
                            "capacity_tons": "71",
                            "connection_type": "ODF",
                            "connection_standard": "ASME B16.22",
                            "material": "Copper",
                            "pressure_rating_bar": "10",
                            "max_temperature_c": "60",
                            "coolant_compatibility": "Water/Glycol",
                            "estimated_price_usd": "",
                            "install_connection_time_min": "75",
                            "part_number": "SMC-CDU-250",
                            "source_catalog": "PDF",
                            "source_page": "1",
                            "datasheet_url": "https://example.com/in-rack-cdu.pdf",
                            "baseline_references": "Test",
                        }
                    ]
                }
            )
        }
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "catalog.sqlite"
            csv_path = Path(td) / "catalog.csv"
            with patch("datacenter_equipment_finder.pdf_catalog.PdfReader", return_value=fake_reader), patch(
                "datacenter_equipment_finder.pdf_catalog.urlopen",
                return_value=_FakeResponse(payload),
            ):
                summary = build_database_from_pdf(
                    _sample_pdf(),
                    db_path,
                    csv_path=csv_path,
                    config=AssistantConfig(local_endpoint="http://127.0.0.1:11434/api/generate", local_model="llama3.1"),
                )
            self.assertEqual(summary["rows"], 1)
            self.assertEqual(summary["csv_path"], str(csv_path))
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute("SELECT COUNT(*) FROM equipment_catalog").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(rows, 1)


if __name__ == "__main__":
    unittest.main()
