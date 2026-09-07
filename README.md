# DATA-CENTER-EQUIPMENT-FINDER

An installable Python package is included to find data-center cooling components by closest required size, Cv/Kv, and capacity, then check list compatibility.

## Install

```bash
pip install -e /home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER
```

## CLI examples

```bash
dcef find --category valve --size-mm 20 --cv 7 --top-n 3
dcef find --category cdu --capacity-kw 500 --size-mm 50
dcef compat LLD-20 DML-20 --max-connection-time 40 --required-material Copper
dcef explain --property flow_coefficient_value
dcef explain --category cdu
dcef serve --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`.

## JSON data interface (for other code/libraries)

The web server provides machine-friendly endpoints:

- `GET /api/schema` → available fields, categories, brands
- `GET /api/components?category=...&brand=...&limit=...&offset=...`
- `GET /api/component?part_number=...`
- `GET /api/find?category=...&size_mm=...&cv=...&kv=...&capacity_kw=...&top_n=...`
- `POST /api/compat` with JSON body:
  - `{"part_numbers":["LLD-20","DML-20"],"max_connection_time":40,"required_material":"Copper"}`
- `GET /api/explain?property=flow_coefficient_value` or `GET /api/explain?category=cdu`
- `GET /api/health`

Python integration interface:

- `datacenter_equipment_finder.EquipmentService`

## Data files

- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/valves_strainers_filter_dryers.csv`
- `/home/runner/work/DATA-CENTER-EQUIPMENT-FINDER/DATA-CENTER-EQUIPMENT-FINDER/src/datacenter_equipment_finder/data/equipment_catalog.csv`

The packaged CSV uses a unified schema for Parker/Danfoss valves, strainers, filter-dryers and CDU/chiller vendors (Vertiv, CoolIT, Accelsius, Trane, Airedale, Supermicro, Motivair).

`brand,category,series_name,component_name,nominal_size_mm,nominal_size_inch,flow_coefficient_type,flow_coefficient_value,capacity_kw,capacity_tons,connection_type,connection_standard,material,pressure_rating_bar,max_temperature_c,coolant_compatibility,estimated_price_usd,install_connection_time_min,part_number,source_catalog,source_page,datasheet_url,baseline_references`