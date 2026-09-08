"""End-to-end run of the PDF ingestion pipeline.

Nothing previously exercised this path against a real PDF or a real HTTP endpoint:
the tests mocked PdfReader and urlopen, so 'dcef build-db-from-pdf' had never been
shown to work. This drives the whole command through a real one-page PDF and a stub
HTTP server that answers like an Ollama /api/generate endpoint.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from datacenter_equipment_finder.assistant import AssistantConfig
from datacenter_equipment_finder.pdf_catalog import build_database_from_pdf, extract_pdf_text
from pdf_fixture import write_text_pdf

ROW = {
    "brand": "Trane", "category": "chiller", "component_subtype": "air_cooled_chiller",
    "series_name": "Series R RTAC", "component_name": "RTAC 140 air-cooled screw chiller",
    "nominal_size_mm": "101.6", "nominal_size_inch": "4.0", "capacity_kw": "492.36",
    "capacity_tons": "140", "connection_type": "Grooved", "material": "Steel",
    "part_number": "RTAC 140-TEST", "source_catalog": "Trane RTAC catalog",
    "datasheet_url": "https://www.tranehk.com/files/Products/RLC-PRC006N-EN.pdf",
    # A model claiming its own extraction is verified must not be believed.
    "verification_status": "verified",
}


class _StubModel(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({"response": json.dumps({"rows": [ROW]})}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture()
def stub_model():
    server = HTTPServer(("127.0.0.1", 0), _StubModel)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/api/generate"
    server.shutdown()
    server.server_close()


def test_build_db_from_pdf_end_to_end(tmp_path: Path, stub_model: str) -> None:
    pdf = write_text_pdf(tmp_path / "vendor.pdf", ["Trane RTAC catalog", "RTAC 140  4 in  140 tons"])
    summary = build_database_from_pdf(
        pdf,
        tmp_path / "vendor.sqlite",
        csv_path=tmp_path / "vendor.csv",
        config=AssistantConfig(local_endpoint=stub_model, local_model="stub"),
    )

    assert summary["rows"] == 1
    assert Path(summary["csv_path"]).exists()

    with sqlite3.connect(summary["sqlite_path"]) as conn:
        rows = conn.execute(
            "SELECT part_number, capacity_kw, verification_status FROM equipment_catalog"
        ).fetchall()
    assert rows == [("RTAC 140-TEST", "492.36", "unverified")]


def test_model_cannot_mark_its_own_extraction_verified(tmp_path: Path, stub_model: str) -> None:
    pdf = write_text_pdf(tmp_path / "vendor.pdf", ["Trane RTAC catalog"])
    build_database_from_pdf(
        pdf, tmp_path / "v.sqlite", csv_path=tmp_path / "v.csv",
        config=AssistantConfig(local_endpoint=stub_model, local_model="stub"),
    )
    text = (tmp_path / "v.csv").read_text()
    assert "verified" in text  # the column is populated
    assert ",verified" not in text.replace(",unverified", "")  # but never as "verified"


def test_missing_pdf_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        extract_pdf_text(tmp_path / "absent.pdf")


def test_html_masquerading_as_a_pdf_is_rejected(tmp_path: Path) -> None:
    # sync-catalogs can save a consent wall under a .pdf name; feeding that to the
    # extractor should say so rather than fail deep inside the parser.
    fake = tmp_path / "consent.pdf"
    fake.write_bytes(b"<!doctype html><html><body>Accept cookies</body></html>")
    with pytest.raises(ValueError, match="is not a PDF"):
        extract_pdf_text(fake)


def test_missing_model_configuration_explains_what_to_set(tmp_path: Path) -> None:
    from datacenter_equipment_finder.pdf_catalog import extract_catalog_rows_from_pdf

    pdf = write_text_pdf(tmp_path / "vendor.pdf", ["text"])
    with pytest.raises(ValueError, match="DCEF_LOCAL_AI_ENDPOINT"):
        extract_catalog_rows_from_pdf(pdf, config=AssistantConfig())


GOOD = dict(ROW, part_number="RTAC 155-TEST")
NAMELESS = dict(ROW, part_number="", component_name="10U Coolant Distribution Unit")


class _MixedModel(_StubModel):
    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({"response": json.dumps({"rows": [GOOD, NAMELESS]})}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def mixed_model():
    server = HTTPServer(("127.0.0.1", 0), _MixedModel)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/api/generate"
    server.shutdown()
    server.server_close()


def test_one_unusable_row_does_not_discard_the_extraction(tmp_path: Path, mixed_model: str) -> None:
    # The Boyd 10U datasheet publishes no SKU at all, so a row without a part_number is
    # a normal outcome. Losing the whole document over it wastes the run.
    summary = build_database_from_pdf(
        write_text_pdf(tmp_path / "v.pdf", ["catalog"]),
        tmp_path / "v.sqlite", csv_path=tmp_path / "v.csv",
        config=AssistantConfig(local_endpoint=mixed_model, local_model="stub"),
    )
    assert summary["rows"] == 1
    assert summary["rejected"] == 1


def test_rejected_rows_are_written_out_for_inspection(tmp_path: Path, mixed_model: str) -> None:
    summary = build_database_from_pdf(
        write_text_pdf(tmp_path / "v.pdf", ["catalog"]),
        tmp_path / "v.sqlite", csv_path=tmp_path / "v.csv",
        config=AssistantConfig(local_endpoint=mixed_model, local_model="stub"),
    )
    rejected = json.loads(Path(summary["rejected_path"]).read_text())
    assert rejected[0]["reasons"] == ["missing part_number"]
    assert rejected[0]["row"]["component_name"] == "10U Coolant Distribution Unit"


def test_strict_mode_still_fails_the_whole_run(tmp_path: Path, mixed_model: str) -> None:
    with pytest.raises(ValueError, match="failed validation"):
        build_database_from_pdf(
            write_text_pdf(tmp_path / "v.pdf", ["catalog"]),
            tmp_path / "v.sqlite", csv_path=tmp_path / "v.csv",
            config=AssistantConfig(local_endpoint=mixed_model, local_model="stub"),
            strict=True,
        )


def test_prompt_tells_the_model_what_to_do_without_a_sku() -> None:
    from datacenter_equipment_finder.pdf_catalog import _pdf_prompt

    prompt = _pdf_prompt("some catalog text")
    assert "product designation" in prompt
    assert "Never invent a code" in prompt
