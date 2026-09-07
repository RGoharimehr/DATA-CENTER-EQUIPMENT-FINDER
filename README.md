# DATA-CENTER-EQUIPMENT-FINDER

Find data-center cooling equipment by size, connection compatibility, flow coefficient, and capacity.

This project provides:
- a Python package
- a CLI (`dcef`)
- a local web UI
- a JSON API at `/api/v1`
- a hybrid assistant with local / remote / hybrid modes
- PDF-to-database ingestion with local AI-assisted extraction

## Requirements

- Python 3.10+
- `pip`
- optional: `uv` for faster environment setup
- optional: a local AI endpoint such as Ollama

## Quick start

### macOS / Linux

```bash
cd /path/to/DATA-CENTER-EQUIPMENT-FINDER
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
dcef serve --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

### Windows PowerShell

```powershell
cd C:\path\to\DATA-CENTER-EQUIPMENT-FINDER
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
dcef serve --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Easy development setup

### With `uv` (recommended)

#### macOS / Linux

```bash
cd /path/to/DATA-CENTER-EQUIPMENT-FINDER
uv venv
source .venv/bin/activate
uv sync --extra dev
python -m pytest
ruff check .
mypy
```

#### Windows PowerShell

```powershell
cd C:\path\to\DATA-CENTER-EQUIPMENT-FINDER
uv venv
.venv\Scripts\Activate.ps1
uv sync --extra dev
python -m pytest
ruff check .
mypy
```

### With `pip`

#### macOS / Linux

```bash
cd /path/to/DATA-CENTER-EQUIPMENT-FINDER
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m pytest
ruff check .
mypy
```

#### Windows PowerShell

```powershell
cd C:\path\to\DATA-CENTER-EQUIPMENT-FINDER
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m pytest
ruff check .
mypy
```

## Run locally

### CLI examples

```bash
dcef find --category valve --size-mm 20 --cv 7 --top-n 3
dcef find --category valve --component-subtype check_valve --size-mm 20 --kv 6 --top-n 3
dcef find --category valve --component-subtype check_valve --connection-size-inch 0.75 --kv 6 --top-n 3
dcef find --category cdu --capacity-kw 500 --size-mm 50
dcef find --category cdu --component-subtype in_row_cdu --connection-size-inch 2.5 --capacity-kw 1000 --top-n 3
dcef compat LLD-20 DML-20 --max-connection-time 40 --required-material Copper
dcef compat LXDU-450 JCI-CDU-1050 --required-connection-standard "ANSI B16.5" --required-coolant Water
dcef explain --property flow_coefficient_value
dcef explain --category cdu
dcef assist --mode local --query "find in row cdu with 2.5 inch pipe connection around 1000 kW"
```

## Use as a package from another tool

Example:

```python
from datacenter_equipment_finder import EquipmentCatalog, EquipmentService, build_database_from_pdf, extract_catalog_rows_from_pdf

catalog = EquipmentCatalog.from_csv()
service = EquipmentService(catalog)
matches = service.find_components(category="valve", connection_size_inch=0.75, kv=6, top_n=3)

rows = extract_catalog_rows_from_pdf(
    "vendor_catalog.pdf",
)

summary = build_database_from_pdf(
    "vendor_catalog.pdf",
    "vendor_catalog.sqlite",
    csv_path="vendor_catalog.csv",
)
```

Useful package APIs:
- `EquipmentCatalog`
- `EquipmentService`
- `run_assistant_query`
- `extract_pdf_text`
- `extract_catalog_rows_from_pdf`
- `write_catalog_csv`
- `build_database_from_pdf`

### Run the web UI + API

```bash
dcef serve --host 127.0.0.1 --port 8000
```

Optional secured run:

```bash
dcef serve --host 127.0.0.1 --port 8000 --api-key devkey --rate-limit-per-minute 120
```

If you enable API key auth:
- send `X-API-Key: <key>` on API calls
- in the built-in web UI, enter the key in the `API Key` field

## Windows / macOS deployment notes

For a simple local deployment on a laptop or workstation:

1. install Python 3.10+
2. create a virtual environment
3. install with `pip install -e .`
4. run `dcef serve --host 127.0.0.1 --port 8000`
5. keep the terminal open while the server is running

For LAN access inside your network:

```bash
dcef serve --host 0.0.0.0 --port 8000
```

Then open:

```text
http://<your-machine-ip>:8000
```

Notes:
- allow the Python process through the Windows or macOS firewall if prompted
- use `--api-key` if other people on the network can reach the service
- for production-style internet exposure, place it behind a reverse proxy and TLS terminator

## Local AI setup

The assistant supports:
- `mode=local`
- `mode=remote`
- `mode=hybrid`

### Rule-based local mode

Works with no extra AI software:

```bash
dcef assist --mode local --query "find a valve with 0.75 inch pipe diameter kv 6"
```

### Optional local model endpoint

You can connect a local model server to improve parsing.

Example with an Ollama-compatible endpoint:

#### macOS / Linux

```bash
export DCEF_LOCAL_AI_ENDPOINT=http://127.0.0.1:11434/api/generate
export DCEF_LOCAL_AI_MODEL=llama3.1
dcef assist --mode local --query "find in row cdu with 2.5 inch pipe connection around 1000 kw"
```

#### Windows PowerShell

```powershell
$env:DCEF_LOCAL_AI_ENDPOINT="http://127.0.0.1:11434/api/generate"
$env:DCEF_LOCAL_AI_MODEL="llama3.1"
dcef assist --mode local --query "find in row cdu with 2.5 inch pipe connection around 1000 kw"
```

Optional auth:
- `DCEF_LOCAL_AI_API_KEY`

Optional remote AI settings:
- `DCEF_AI_ENDPOINT`
- `DCEF_AI_API_KEY`

## Build a database from a PDF

The package can read a PDF, ask a local AI model to map extracted content into the existing equipment schema, write a CSV, and build a SQLite database.

### CLI

```bash
dcef build-db-from-pdf vendor_catalog.pdf --db-path vendor_catalog.sqlite --csv-path vendor_catalog.csv
```

Optional page limit:

```bash
dcef build-db-from-pdf vendor_catalog.pdf --db-path vendor_catalog.sqlite --max-pages 10
```

### Required local AI environment

#### macOS / Linux

```bash
export DCEF_LOCAL_AI_ENDPOINT=http://127.0.0.1:11434/api/generate
export DCEF_LOCAL_AI_MODEL=llama3.1
```

#### Windows PowerShell

```powershell
$env:DCEF_LOCAL_AI_ENDPOINT="http://127.0.0.1:11434/api/generate"
$env:DCEF_LOCAL_AI_MODEL="llama3.1"
```

Optional:
- `DCEF_LOCAL_AI_API_KEY`

The PDF workflow is intended for vendor datasheets and catalog-like PDFs that contain structured equipment information. The local AI model is used to decide what rows should become database records in the existing schema.

## JSON API

API version: `/api/v1`

Envelope format:
- success: `{"ok": true, "data": ..., "error": null, "meta": {"api_version": "v1"}}`
- error: `{"ok": false, "data": null, "error": {"code": "...", "message": "..."}, "meta": {"api_version": "v1"}}`

Endpoints:
- `GET /api/v1/schema`
- `GET /api/v1/components?category=...&brand=...&limit=...&offset=...`
- `GET /api/v1/components?category=...&component_subtype=...&brand=...&limit=...&offset=...`
- `GET /api/v1/component?part_number=...`
- `GET /api/v1/find?category=...&component_subtype=...&size_mm=...&connection_size_mm=...&connection_size_inch=...&cv=...&kv=...&capacity_kw=...&top_n=...`
- `POST /api/v1/compat`
- `GET /api/v1/explain?property=flow_coefficient_value`
- `GET /api/v1/explain?category=cdu`
- `POST /api/v1/assistant`
- `GET /api/v1/health`
- `GET /api/v1/openapi.json`

Example assistant request body:

```json
{"query":"find check_valve 20 mm kv 6 from danfoss","mode":"hybrid"}
```

## Matching behavior

- `valve` / `strainer`: use `cv` / `kv`, nominal size, and optional connection size
- `filter_dryer` / `cdu` / `chiller`: use capacity, subtype, nominal size, and optional connection size
- `cdu` / `chiller` / `filter_dryer` reject `cv` / `kv`
- local assistant queries can infer phrases like:
  - `2 inch pipe`
  - `connection 50 mm`
  - `in row cdu`
  - `in rack cdu`

## Data files

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/valves_strainers_filter_dryers.csv`
- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/src/datacenter_equipment_finder/data/equipment_catalog.csv`
- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/src/datacenter_equipment_finder/data/equipment_catalog.sqlite`

The packaged CSV uses a unified schema for Parker/Danfoss valves, strainers, filter-dryers, CDUs, and chillers.

Vendor source CSVs are in:

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/src/datacenter_equipment_finder/data/vendors/`

Useful commands:

```bash
dcef build-catalog
dcef sync-catalogs --limit 5
dcef build-db
```

## GitHub Pages website

Static website source:

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/docs/index.html`

Deployment workflow:

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/.github/workflows/pages.yml`

After enabling **Pages (GitHub Actions)** in repository settings, the static site is published from the workflow artifact.
