# Using this tool from a design agent

Instructions for an assistant embedded in a reference-design generator. This tool
selects catalogue components against duties the generator has already computed. It does
not size anything, and it does not decide anything the vendor has to decide.

## What it is

A catalogue of data-centre cooling components, each row transcribed from a published
vendor document, with a selector that answers one question: **which catalogue parts can
meet this duty?**

It is not a hydraulic solver, not a vendor selection, and not a compliance check.

## Call it with a schedule

```bash
dcef select --schedule <valve_schedule.csv> --top-n 3
```

Reads a generator valve schedule directly. Column mapping:

| Schedule column | Used as |
| --- | --- |
| `type` | catalogue category (`isolation_valve` -> valve/shutoff_valve, `check_valve` -> valve/check_valve, `quick_disconnect`, `strainer`, `cdu_*` -> cdu) |
| `service` | hydraulic loop; TCS and FWS are kept apart |
| `material` | wetted-material requirement (`stainless_sch10`, `copper_type_l`, `carbon_steel_sch40`) |
| `size_nominal_in` | minimum bore |
| `valve_Cv` | required **Cv (US)** at the allocated `dp_Pa` |

Rows are grouped into distinct duties. A 126-row schedule for a 32-rack design holds
eight; each result carries the `tags` and `quantity` it covers.

## Or call it with duties directly

```bash
dcef select --duty duty.json          # "-" reads stdin
```

```json
{"items": [
  {"tag": "CDU-1", "loop": "TCS", "category": "cdu",
   "required_capacity_kw": 2006.4, "required_temperature_c": 42},
  {"tag": "TCS-IV-2in", "loop": "TCS", "category": "valve",
   "component_subtype": "shutoff_valve", "required_cv": 18.5,
   "minimum_size_mm": 50.8, "required_material": "Copper",
   "required_pressure_bar": 10}
]}
```

`POST /api/v1/select` takes the same object.

## Reading the result

```json
{"items": [{"tag": ..., "loop": ..., "quantity": ...,
            "candidates": [{"score": 0.09, "component": {...}, "warnings": [...]}],
            "unmet": []}],
 "assemblies_by_loop": {"TCS": {"limits": {...}, "reasons": [...], "notes": [...]}},
 "unresolved": ["TCS-check_valve-8in"]}
```

- `score` is **mean fractional oversize**. `0.09` means 9% above the requirement. Lower
  is a closer fit. It is not a quality or confidence score.
- `unresolved` lists tags nothing could satisfy. The CLI exits non-zero when it is
  non-empty.
- `assemblies_by_loop` gives the governing pressure and temperature per circuit. The
  weakest component governs, and the report names it.

## What it refuses, and why you must not work around it

**A schedule with no assigned duty.** Rows reporting `unassigned; manual geometry
sizing` with an empty `valve_Cv` carry no flow and no allocated pressure drop. Every
duty returns unresolved. Do not fall back to selecting on nominal bore: that produces a
part number with no engineering basis behind it. Tell the user to run preliminary
sizing first.

**A part below the requirement.** A valve whose Kv is under the required figure cannot
pass the design flow at its allocated drop, so it is excluded rather than offered as a
near miss. Never present an excluded part as "close enough".

**An unknown value.** A part that publishes no coefficient, capacity, bore, pressure or
temperature is returned with a `cannot confirm` warning. Unknown is not adequate and
not inadequate. Repeat the warning to the user; do not resolve it yourself.

## Warnings you must pass on

| Warning | What it means |
| --- | --- |
| `...x the requirement; the catalogue may hold no closer size` | The nearest candidate is evidence of a missing size, not a selection. Above 2x, say so. |
| `specifications not verified against a source document` | The row has not been checked against its cited datasheet. |
| `vendor literature does not support this entry` | The row was checked and failed. Do not specify it. |
| `wetted material not published; X not confirmed` | The material requirement could not be checked. |
| `<material> on a <material> line: an accepted substitution` | Ordinary practice (bronze/brass on copper), still needs project confirmation. |
| `pressure rating not published; N bar duty unconfirmed` | Duty could not be checked against a published rating. |

## What you must not claim

A result from this tool is a **capacity shortlist**. It does not establish:

- trim characteristic, valve authority, opening position or minimum-flow control
- cavitation or flashing limits, viscosity effects
- pressure class, gasket, seat or seal material suitability
- a balanced network, a pump operating point, NPSH margin or transient behaviour
- compliance with any code or jurisdictional requirement

Say "candidate", "shortlist" or "meets the published capacity". Do not say "selected",
"specified", "verified" or "compliant".

## Discovering the vocabulary

```bash
dcef schema
```

Lists categories, their subtypes, what selects each one, the brands present and the duty
limits. An unknown category or brand is reported as a typo with the valid values, not as
an empty result. Use this rather than guessing a category name.

## Known catalogue limits

The catalogue is small and its gaps are real. It will legitimately fail to answer parts
of a real design, and reporting that failure is the correct behaviour. Current coverage:
Danfoss GBC ball valves to 3-1/8 in, Pratt HE butterfly valves 2-12 in, Danfoss FIA
strainers DN15-DN200, OCP UQD couplings UQD02-UQD08, and a set of CDUs and chillers.
There are no large check valves, no control valves with published characteristics, and
no pipe, fittings or supports at all.
