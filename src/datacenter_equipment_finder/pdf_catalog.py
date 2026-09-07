from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pypdf import PdfReader

from .assistant import AssistantConfig, default_assistant_config
from .catalog import FIELD_NAMES
from .catalog_tools import build_sqlite_database
from .dataset_pipeline import validate_rows


def extract_pdf_text(pdf_path: str | Path, *, max_pages: int | None = None) -> str:
    path = Path(pdf_path)
    reader = PdfReader(str(path))
    pages = reader.pages[: max_pages or len(reader.pages)]
    text = "\n\n".join((page.extract_text() or "").strip() for page in pages).strip()
    if not text:
        raise ValueError(f"No extractable text found in PDF: {path}")
    return text


def _chunk_text(text: str, *, max_chars: int = 12000) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_chars)
        if split_at <= 0:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks


def _extract_json_payload(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("Model response did not contain JSON")
    start = min(starts)
    end_object = text.rfind("}")
    end_array = text.rfind("]")
    end = max(end_object, end_array)
    if end <= start:
        raise ValueError("Model response did not contain complete JSON")
    return json.loads(text[start : end + 1])


def _pdf_prompt(text_chunk: str) -> str:
    return (
        "Convert the following PDF catalog text into structured JSON rows.\n"
        "Return JSON only. Use the exact schema keys below for every row.\n"
        "Only include rows that represent actual equipment items.\n"
        "Every field value must be a string; use an empty string when unknown.\n"
        f"Schema keys: {FIELD_NAMES}\n"
        'Return an object like {"rows": [...]}.\n'
        f"PDF text:\n{text_chunk}"
    )


def _request_local_model(prompt: str, config: AssistantConfig) -> Any:
    if not config.local_endpoint or not config.local_model:
        raise ValueError("DCEF_LOCAL_AI_ENDPOINT and DCEF_LOCAL_AI_MODEL are required for PDF extraction")

    endpoint = config.local_endpoint.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if config.local_api_key:
        headers["Authorization"] = "Bearer " + config.local_api_key
        headers["X-API-Key"] = config.local_api_key

    if endpoint.endswith("/api/generate"):
        payload: dict[str, Any] = {
            "model": config.local_model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        }
    else:
        payload = {
            "model": config.local_model,
            "messages": [
                {"role": "system", "content": "Return only JSON for the requested schema."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    req = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=config.timeout_seconds) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"Local model request failed: {exc}") from exc

    if isinstance(response_data, dict):
        if isinstance(response_data.get("response"), str):
            return _extract_json_payload(response_data["response"])
        if isinstance(response_data.get("message"), dict) and isinstance(response_data["message"].get("content"), str):
            return _extract_json_payload(response_data["message"]["content"])
        choices = response_data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return _extract_json_payload(message["content"])
        return response_data
    return response_data


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {field: _normalize_value(row.get(field)) for field in FIELD_NAMES}
    normalized["category"] = normalized["category"].lower().replace(" ", "_")
    normalized["component_subtype"] = normalized["component_subtype"].lower().replace(" ", "_")
    coeff = normalized["flow_coefficient_type"].lower()
    if coeff == "cv":
        normalized["flow_coefficient_type"] = "Cv"
    elif coeff == "kv":
        normalized["flow_coefficient_type"] = "Kv"
    return normalized


def _rows_from_payload(payload: Any) -> list[dict[str, str]]:
    rows_data = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows_data, list):
        raise ValueError("Model response must contain a rows list")
    rows: list[dict[str, str]] = []
    for item in rows_data:
        if isinstance(item, dict):
            rows.append(_normalize_row(item))
    return rows


def _merge_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    ordered: list[str] = []
    for row in rows:
        part_number = row.get("part_number", "").strip()
        key = part_number.lower() or json.dumps(row, sort_keys=True)
        if key not in merged:
            merged[key] = dict(row)
            ordered.append(key)
            continue
        current = merged[key]
        for field in FIELD_NAMES:
            if not current.get(field) and row.get(field):
                current[field] = row[field]
    return [merged[key] for key in ordered]


def extract_catalog_rows_from_pdf(
    pdf_path: str | Path,
    *,
    config: AssistantConfig | None = None,
    max_pages: int | None = None,
    max_chars_per_chunk: int = 12000,
) -> list[dict[str, str]]:
    cfg = config or default_assistant_config()
    text = extract_pdf_text(pdf_path, max_pages=max_pages)
    chunks = _chunk_text(text, max_chars=max_chars_per_chunk)
    rows: list[dict[str, str]] = []
    for chunk in chunks:
        payload = _request_local_model(_pdf_prompt(chunk), cfg)
        rows.extend(_rows_from_payload(payload))
    rows = _merge_rows(rows)
    errors = validate_rows(rows)
    if errors:
        message = "\n".join(f"- {error}" for error in errors[:20])
        raise ValueError(f"Extracted PDF rows failed validation:\n{message}")
    return rows


def write_catalog_csv(rows: list[dict[str, str]], csv_path: str | Path) -> Path:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_NAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_database_from_pdf(
    pdf_path: str | Path,
    sqlite_path: str | Path,
    *,
    csv_path: str | Path | None = None,
    config: AssistantConfig | None = None,
    max_pages: int | None = None,
    max_chars_per_chunk: int = 12000,
) -> dict[str, Any]:
    rows = extract_catalog_rows_from_pdf(
        pdf_path,
        config=config,
        max_pages=max_pages,
        max_chars_per_chunk=max_chars_per_chunk,
    )

    temp_csv: Path | None = None
    target_csv: Path
    if csv_path is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="dcef-pdf-", dir="/tmp"))
        temp_csv = temp_dir / "catalog_from_pdf.csv"
        target_csv = temp_csv
    else:
        target_csv = Path(csv_path)

    write_catalog_csv(rows, target_csv)
    row_count = build_sqlite_database(target_csv, sqlite_path)

    return {
        "pdf_path": str(Path(pdf_path)),
        "csv_path": str(target_csv),
        "sqlite_path": str(Path(sqlite_path)),
        "rows": row_count,
        "used_temporary_csv": temp_csv is not None,
    }
