# DATA-CENTER-EQUIPMENT-FINDER

An installable Python package is included to find data-center cooling components by closest required size, Cv/Kv, and capacity, then check list compatibility.

## Install

```bash
pip install -e /home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER
```

## CLI examples

```bash
dcef find --category valve --size-mm 20 --cv 7 --top-n 3
dcef find --category valve --component-subtype check_valve --size-mm 20 --kv 6 --top-n 3
dcef find --category cdu --capacity-kw 500 --size-mm 50
dcef compat LLD-20 DML-20 --max-connection-time 40 --required-material Copper
dcef compat LXDU-450 JCI-CDU-1050 --required-connection-standard "ANSI B16.5" --required-coolant Water
dcef explain --property flow_coefficient_value
dcef explain --category cdu
dcef serve --host 127.0.0.1 --port 8000 --api-key devkey --rate-limit-per-minute 120
dcef build-catalog
```

Then open `http://127.0.0.1:8000`.

## JSON data interface (for other code/libraries)

API is versioned under `/api/v1` and returns a consistent envelope:

- success: `{\"ok\": true, \"data\": ..., \"error\": null, \"meta\": {\"api_version\": \"v1\"}}`
- error: `{\"ok\": false, \"data\": null, \"error\": {\"code\": \"...\", \"message\": \"...\"}, \"meta\": {\"api_version\": \"v1\"}}`

The web server provides machine-friendly endpoints:

- `GET /api/v1/schema` → available fields, categories, brands
- `GET /api/v1/components?category=...&brand=...&limit=...&offset=...`
- `GET /api/v1/components?category=...&component_subtype=...&brand=...&limit=...&offset=...`
- `GET /api/v1/component?part_number=...`
- `GET /api/v1/find?category=...&component_subtype=...&size_mm=...&cv=...&kv=...&capacity_kw=...&top_n=...`
- `POST /api/v1/compat` with JSON body:
  - `{"part_numbers":["LLD-20","DML-20"],"max_connection_time":40,"required_material":"Copper","required_connection_standard":"ANSI B16.5","required_coolant":"Water"}`
- `GET /api/v1/explain?property=flow_coefficient_value` or `GET /api/v1/explain?category=cdu`
- `GET /api/v1/health`
- `GET /api/v1/openapi.json`

Component-aware input behavior:

- `valve`/`strainer`: use `cv`/`kv` and size
- `filter_dryer`/`cdu`/`chiller`: use capacity and size; Cv/Kv is rejected
- compatibility checks now include thermal fields (`required_connection_standard`, `required_coolant`) and hydraulic connection-time checks

Optional API key auth:

- set `DCEF_API_KEY` env var or pass `--api-key` in `dcef serve`
- send `X-API-Key: <key>` header on API calls

Rate limiting:

- set `DCEF_RATE_LIMIT_PER_MIN` env var or pass `--rate-limit-per-minute`

Python integration interface:

- `datacenter_equipment_finder.EquipmentService`

## Data files

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/valves_strainers_filter_dryers.csv`
- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/src/datacenter_equipment_finder/data/equipment_catalog.csv`

The packaged CSV uses a unified schema for Parker/Danfoss valves, strainers, filter-dryers and CDU/chiller vendors (Vertiv, CoolIT, Accelsius, Trane, Airedale, Supermicro, Motivair).

`brand,category,component_subtype,series_name,component_name,nominal_size_mm,nominal_size_inch,flow_coefficient_type,flow_coefficient_value,capacity_kw,capacity_tons,connection_type,connection_standard,material,pressure_rating_bar,max_temperature_c,coolant_compatibility,estimated_price_usd,install_connection_time_min,part_number,source_catalog,source_page,datasheet_url,baseline_references`

Vendor-split source files for data maintenance are in:

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/src/datacenter_equipment_finder/data/vendors/`

Use `dcef build-catalog` to validate and rebuild the consolidated catalog.

## GitHub Pages website

Static website source:

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/docs/index.html`

Deployment workflow:

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/.github/workflows/pages.yml`

After enabling **Pages (GitHub Actions)** in repo settings, the website is published from the workflow artifact.