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

- Python 3.11+
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
dcef find --category quick_disconnect --cv 2.4 --top-n 4
dcef find --category quick_disconnect --component-subtype blind_mate_uqd --cv 1.25
dcef explain --category quick_disconnect
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

1. install Python 3.11+
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
# Point it at a document you actually have. dcef sync-catalogs puts the catalog's
# cited datasheets in src/datacenter_equipment_finder/data/catalog_downloads/.
dcef build-db-from-pdf path/to/vendor-datasheet.pdf \
  --db-path vendor_catalog.sqlite --csv-path vendor_catalog.csv
```

Extraction keeps the rows it can use and sets the rest aside. Anything rejected is
written to `<csv-path>.rejected.json` with the reason, so a bad row can be corrected
rather than re-run blind. Pass `--strict` to fail the whole run instead. The command
fails only when no row survives.

Rows produced this way are always written with `verification_status = unverified`,
whatever the model claims. A model reading PDF text is making an extraction, not a
checked transcription, and this command does not confirm anything against the
document. Treat its output as a draft to review, not as catalog-ready data.

The command exits 2 with a plain message if the file is missing, is not a PDF (a
downloaded consent wall is the usual cause), or if no local model is configured.

Extraction on a local model is slow - minutes per chunk on an 8B model, and the
first call also pays the cost of loading the model into memory. The wait defaults to
600 seconds; raise it with `--timeout` or `DCEF_PDF_AI_TIMEOUT_SECONDS`. This is
separate from `DCEF_AI_TIMEOUT_SECONDS`, which governs the much shorter assistant
query parsing.

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

## Duty limits

State the pressure or coolant temperature the part has to survive and under-rated
components are removed from the results rather than ranked low:

```bash
dcef find --category quick_disconnect --cv 2.4 --required-pressure-bar 15
dcef find --category quick_disconnect --cv 2.4 --required-temperature-c 70
```

```text
GET /api/v1/find?category=quick_disconnect&cv=2.4&required_pressure_bar=15
```

The assistant reads them from plain language too - `"quick disconnect rated for 15 bar"`,
`"UQD for 70 C coolant temperature"`, `"a 150 psi system"`. A rating condition such as
`"1350 kW at 4 C approach"` is not treated as a duty limit.

Rules:

- A component is excluded only when its **published** rating is below the stated duty.
- A component with no published rating is kept and carries a warning, because an
  unknown rating cannot be proven inadequate.
- If nothing qualifies, the CLI says so and exits non-zero, and the assistant returns
  no matches plus an explicit check. It never quietly relaxes the limit.

## Compatibility

`dcef compat` and `POST /api/v1/compat` evaluate a set of part numbers as one assembly.

```bash
dcef compat "Hansen UQD06" 009L8622 --required-pressure-bar 15
dcef compat 023Z5068 C-609-S --required-coolant "Water/Glycol"
```

The response separates three things:

- `reasons` - genuine incompatibilities. Non-empty means `is_compatible` is false.
- `notes` - advisories and derived facts that do not invalidate the selection.
- `limits` - the assembly envelope. **The weakest component governs**, and the report
  names it: `Assembly is limited to 6.9 bar by Hansen UQD06`.

What it checks:

- **Duty**: `required_pressure_bar` and `required_temperature_c` are compared against
  every part, so the lowest-rated one cannot hide behind the others.
- **End connections**: compared by joint family across *all* categories, so ODF and
  ODS match, tri-clamp and hygienic flange match, and ORB against ODF solder does not.
- **Wetted materials**: compared by family. `316L Stainless Steel`, `SS303` and
  `Stainless Steel` are the same material family; a copper part in a carbon-steel loop
  raises a galvanic advisory rather than a false mismatch.
- **Coolant**: compared by family, so `Water/EGW/PGW` satisfies a `Water/Glycol`
  requirement while `Ammonia` does not.
- **Provenance**: unverified and disputed parts in the selection are called out.

The CLI exits non-zero when a selection is incompatible or a part number is not in the
catalog, so it can gate a build.

## Match scores

A score is the weighted mean relative error across the criteria you actually
constrained, so `0.02` means roughly 2% off and scores are comparable between queries.
Lower is better.

- Capacity dominates for `cdu` / `chiller` / `filter_dryer`; flow coefficient dominates
  for `valve` / `strainer` / `quick_disconnect`. Connection size is a secondary term,
  so a CDU three times off the requested duty cannot win on pipe size alone.
- A component with no value for a criterion you asked about is scored at 0.75 for it:
  worse than any match within 75%, better than a wilder one. Missing data no longer
  wins by default.
- Unverified rows take a 0.05 penalty and carry a warning, so they lose ties but can
  still win on merit.

## Matching behavior

- `valve` / `strainer` / `quick_disconnect`: use `cv` / `kv`, nominal size, and optional connection size
- `filter_dryer` / `cdu` / `chiller`: use capacity, subtype, nominal size, and optional connection size
- `cdu` / `chiller` / `filter_dryer` reject `cv` / `kv`
- `quick_disconnect` rows always carry a Cv or Kv value
- local assistant queries can infer phrases like:
  - `2 inch pipe`
  - `connection 50 mm`
  - `in row cdu`
  - `in rack cdu`

## Data files

- `valves_strainers_filter_dryers.csv`
- `src/datacenter_equipment_finder/data/equipment_catalog.csv`
- `src/datacenter_equipment_finder/data/equipment_catalog.sqlite`

### Verification status

Every row carries a `verification_status`:

- `verified` - each figure was read from the document in `datasheet_url`.
- `unverified` - not yet checked against a source. Confirm before relying on it.
- `disputed` - checked against the cited literature, which does not support it.
  Treat this as "contradicted so far", not "proven false": a wider document can
  clear a row, as Parker Catalog CC-11c did for `S4A-20` and `CK2-32`. Kept visible so a
  stale entry is obvious rather than quietly missing, but heavily penalised in ranking
  and flagged with a warning in every result.

Filter to trustworthy rows only:

```bash
dcef find --category cdu --capacity-kw 1000 | grep -v unverified
curl "http://127.0.0.1:8000/api/v1/components?category=cdu" | grep verification_status
```

Checking the inherited rows found three that could not be substantiated, which is why
this field exists:

| Row as it was | What the vendor document says |
| --- | --- |
| `SMC-CDU-250` | No such SKU. Supermicro publishes `LCS-SCDU-250L4001` (EIA) and `LCS-SCDU-250LP4002` (OCP). |
| `CHX2000`, 1000 kW, 65 mm Victaulic | CHx2000 is rated 2000 kW with 4 in tri-clamp connections. |
| `NC-CDU-300`, 300 kW | No such model. Accelsius ships NeuCool MR250 (250 kW) and IR150. |
| `DCS-1600` | Not an Airedale designation. TurboChill DCS models are TCF13R18K, TCF24R24G, TCC14R28K. |
| `LXDU-450`, 450 kW, NPT | Vertiv XDU450, 453 kW at 4 C approach, 2.5 in hygienic flange. |
| `HPCS-1200`, 1200 kW | The whole Liebert HPC-S range tops out near 408 kW - roughly a third of the claimed figure. |
| `DML-20`, 3/4 in, 120 C | Danfoss publishes no 3/4 in DML. The range is 1/4 to 5/8 in and the operating limit is 70 C, not 120 C. |
| `A4A-20`, angle valve, Cv 4.4, 40 bar, 121 C | A4A is a flanged-body pressure regulator series, 20-100 mm. At 20 mm: Cv 7.2, 27.6 bar, 105 C. |
| `S4A-20`, `CK2-32` | Both are real Parker types - S4A is a solenoid valve, CK2 a check valve - and appear in Catalog CC-11c. Their Cv values are still unconfirmed, so they are `unverified`. An earlier pass marked them `disputed` on the strength of two bulletins that simply do not cover these families; checking the catalog itself corrected that. |
| `CTV-DC-3500` | CenTraVac is real (CVHF/CVHE/CVHG/CDHF, 165-3950 tons) but this is not a Trane designation. Marked `disputed`. |

### Data provenance rules

Every catalog row must be traceable to a published vendor document. These rules
are enforced by `tests/test_catalog_data_quality.py`:

1. `source_catalog` and `datasheet_url` are required on every row, and the URL must be a real published document. A row marked `verified` must cite a specific document, not a vendor landing page.
2. Specifications are transcribed from that document. Values are never inferred, interpolated between models, or estimated.
3. `part_number` uses the manufacturer's own SKU where one is published. Where a vendor publishes a product designation but no public SKU (common for CDUs), the vendor's designation is used verbatim - for example `CoolChip CDU 1350` or `Boyd 10U CDU`.
4. Where different vendors publish different figures for the same nominal UQD size, each vendor's own published figure is recorded. The spread between them is real and is exactly what the finder is meant to surface.
5. `max_temperature_c` is the **product** operating limit, never the seal elastomer's material rating. Datasheets print both, and the elastomer figure is often far higher - Danfoss Hansen UQD couplings operate to 65 C while their EPDM-P seal material is rated to 150 C.
6. Capacity ratings are condition-dependent. Where a datasheet states an approach temperature or flow condition, record it in `component_name` so two rows are not compared at different conditions.
7. `estimated_price_usd` and `install_connection_time_min` are the only estimated fields. Leave them blank rather than guessing.
8. Unit pairs must agree: `capacity_kw` / `capacity_tons` within 2%, `nominal_size_mm` / `nominal_size_inch` within 5%.

The packaged CSV uses a unified schema for Parker/Danfoss valves, strainers, filter-dryers, CDUs, chillers, and OCP UQD quick disconnects.

Vendor source CSVs are in:

- `src/datacenter_equipment_finder/data/vendors/`

Useful commands:

```bash
dcef build-catalog
dcef sync-catalogs --limit 5
dcef build-db
dcef export-web-catalog
```

`sync-catalogs` reports each URL individually and exits non-zero if any failed:

```text
  ok           1244 KB  https://assets.danfoss.com/.../AI222586432958en-US1102.pdf
  FAILED   HTTP 403 Forbidden  https://www.vertiv.com/.../vertiv-xdu450-cdu-ds-en-na-sl-07622-web.pdf

12 downloaded, 1 already present, 14 failed, 27 total
```

It sends a browser user agent, because several vendor CDNs reject the default urllib
agent, and flags a PDF link that answers with HTML - usually a consent wall returned
as a 200, which silently corrupts the ingestion input.

Note that `.venv` in this directory is the only environment the tooling assumes. If you
share this folder between machines with different Python versions, keep separate
virtual environments outside the repository rather than one `.venv` inside it.

## GitHub Pages website

Static website source:

- `docs/index.html`

Deployment workflow:

- `.github/workflows/pages.yml`

After enabling **Pages (GitHub Actions)** in repository settings, the static site is published from the workflow artifact.

`docs/equipment_catalog.json` is a pre-rendered copy of the packaged catalog. After changing vendor data, regenerate it with:

```bash
dcef export-web-catalog
```

`tests/test_catalog_tools.py` fails if it drifts out of sync.
