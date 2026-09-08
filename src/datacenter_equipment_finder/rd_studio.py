"""Adapter for a reference-design generator's schedules.

The upstream studio emits a valve schedule with one row per physical item, already
carrying the loop, nominal size, wetted material and - once preliminary sizing has run
- a required valve Cv at an allocated pressure drop. This turns those rows into the
duty items the selector consumes.

Two things this deliberately does not do:

* It does not invent a duty. A schedule generated in manual geometry mode carries no
  flow, no allocated pressure drop and no Cv, and selecting a valve from nominal size
  alone would look like an engineering result while resting on nothing.
* It does not collapse the loops. A TCS item and an FWS item sit either side of the
  CDU's thermal coupling and are not part of one hydraulic assembly.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from .units import inch_to_mm

# Schedule component types mapped onto the catalogue's controlled vocabulary.
TYPE_TO_CATEGORY: dict[str, tuple[str, Optional[str]]] = {
    "isolation_valve": ("valve", "shutoff_valve"),
    "balancing_valve": ("valve", None),
    "check_valve": ("valve", "check_valve"),
    "control_valve": ("valve", None),
    "quick_disconnect": ("quick_disconnect", None),
    "strainer": ("strainer", None),
    "filter_dryer": ("filter_dryer", None),
    "cdu_primary": ("cdu", None),
    "cdu_secondary": ("cdu", None),
    "cdu_enclosure": ("cdu", None),
}

# Pipe-family codes mapped onto wetted-material families.
MATERIAL_TO_FAMILY = {
    "stainless_sch10": "Stainless Steel",
    "stainless_sch40": "Stainless Steel",
    "copper_type_l": "Copper",
    "copper_type_k": "Copper",
    "carbon_steel_sch40": "Carbon Steel",
    "carbon_steel_sch80": "Carbon Steel",
}

# A schedule says so itself when nothing hydraulic has been assigned.
_UNASSIGNED_MARKERS = ("unassigned", "manual geometry sizing")


def _number(value: str | None) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed


def _duty_is_assigned(row: dict[str, str]) -> bool:
    basis = (row.get("hydraulic_result_basis") or "").lower()
    if any(marker in basis for marker in _UNASSIGNED_MARKERS):
        return False
    cv = _number(row.get("valve_Cv"))
    return cv is not None and cv > 0


def duties_from_valve_schedule(path: str | Path) -> list[dict[str, Any]]:
    """Group a valve schedule into one duty item per distinct requirement.

    A 126-row schedule of a 32-rack design holds eight distinct duties. Selecting
    once per row would repeat the same answer 64 times; the tags are carried through
    so each duty still names the items it covers.
    """
    rows = list(csv.DictReader(Path(path).open("r", encoding="utf-8", newline="")))
    grouped: dict[tuple, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        signature = (
            (row.get("type") or "").strip(),
            (row.get("size_nominal_in") or "").strip(),
            (row.get("service") or "").strip(),
            (row.get("material") or "").strip(),
            (row.get("valve_Cv") or "").strip(),
            (row.get("dp_Pa") or "").strip(),
        )
        grouped[signature].append(row)

    duties: list[dict[str, Any]] = []
    for signature, members in grouped.items():
        kind, size_in, service, material, _, _ = signature
        category, subtype = TYPE_TO_CATEGORY.get(kind, (None, None))
        sample = members[0]
        tags = [m.get("tag") or m.get("component_id") or "" for m in members]

        duty: dict[str, Any] = {
            "tag": f"{service or 'UNSPECIFIED'}-{kind}-{size_in or 'NA'}in",
            "category": category,
            "component_subtype": subtype,
            "loop": service or None,
            "required_material": MATERIAL_TO_FAMILY.get(material),
            "schedule_type": kind,
            "quantity": sum(int(_number(m.get("quantity_each")) or 1) for m in members),
            "tags": tags,
        }

        nominal = _number(size_in)
        if nominal is not None:
            duty["minimum_size_mm"] = round(inch_to_mm(nominal), 2)

        if _duty_is_assigned(sample):
            duty["required_cv"] = _number(sample.get("valve_Cv"))
            duty["allocated_dp_pa"] = _number(sample.get("dp_Pa"))
            duty["design_flow_m3_s"] = _number(sample.get("design_flow_m3_s"))
        else:
            duty["duty_unassigned"] = (
                "the schedule reports "
                f"{(sample.get('hydraulic_result_basis') or 'no hydraulic basis').strip()}"
                " and no valve Cv, so there is no hydraulic duty to select against"
            )

        if category is None:
            duty["unmappable"] = f"schedule type {kind!r} has no catalogue category"

        duties.append(duty)

    duties.sort(key=lambda d: (d["loop"] or "", d.get("schedule_type", ""), d.get("minimum_size_mm") or 0))
    return duties


# The generator computes a required Kv only where one is meaningful. A balancing or
# control valve is sized on its throttling coefficient at an allocated pressure drop;
# an isolation or check valve is on/off, and its full-open Kv is not a design
# constraint. Those are selected on bore, rating and material instead.
THROTTLING_TYPES = {"balancing_valve", "control_valve"}


def duties_from_sizing(
    valve_capacities: list[dict[str, Any]],
    schedule_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build duties from the generator's own preliminary-sizing output.

    ``valve_capacities`` entries carry ``component_id``, ``Cv_US``, ``Kv_m3_h``,
    ``allocated_dp_Pa`` and ``flow_m3_s``. The schedule, when supplied, adds the loop,
    wetted material and nominal bore for the same tag.
    """
    context: dict[str, dict[str, str]] = {}
    for row in schedule_rows or []:
        tag = (row.get("tag") or row.get("component_id") or "").strip()
        if tag:
            context[tag] = row

    duties: list[dict[str, Any]] = []
    for entry in valve_capacities:
        tag = str(entry.get("component_id") or entry.get("edge_id") or "").strip()
        row = context.get(tag, {})
        kind = (row.get("type") or "").strip()
        category, subtype = TYPE_TO_CATEGORY.get(kind, ("valve", None))

        duty: dict[str, Any] = {
            "tag": tag,
            "edge_id": entry.get("edge_id"),
            "category": category,
            "component_subtype": subtype,
            "loop": (row.get("service") or "").strip() or None,
            "required_material": MATERIAL_TO_FAMILY.get((row.get("material") or "").strip()),
            "schedule_type": kind or None,
            "required_cv": _number(str(entry.get("Cv_US"))) if entry.get("Cv_US") is not None else None,
            "allocated_dp_pa": entry.get("allocated_dp_Pa"),
            "design_flow_m3_s": entry.get("flow_m3_s"),
        }

        nominal = _number(row.get("size_nominal_in"))
        if nominal is not None:
            duty["minimum_size_mm"] = round(inch_to_mm(nominal), 2)

        if kind and kind not in THROTTLING_TYPES:
            # Keep the coefficient out of the requirement so an on/off valve is not
            # judged against a throttling figure it was never sized for.
            duty["required_cv"] = None
            duty["sizing_note"] = (
                f"{kind} is on/off; selected on bore, pressure class and material "
                "rather than a required flow coefficient"
            )

        duties.append({k: v for k, v in duty.items() if v is not None})
    return duties


def reconcile(
    duties: list[dict[str, Any]],
    selection: dict[str, Any],
) -> dict[str, Any]:
    """Pair what the generator calculated with what the catalogue offers.

    Produces one row per tag with the calculated duty beside the suggested part and an
    unset decision. The design is not published until every row has one: the choice
    between the calculated requirement and a catalogue part belongs to the engineer,
    and a tag the catalogue cannot answer needs a component sourced elsewhere.
    """
    by_tag = {item.get("tag"): item for item in selection.get("items", [])}
    rows: list[dict[str, Any]] = []

    for duty in duties:
        tag = duty.get("tag")
        result = by_tag.get(tag, {})
        candidates = result.get("candidates", [])
        best = candidates[0] if candidates else None

        calculated = {
            "required_cv_us": duty.get("required_cv"),
            "allocated_dp_pa": duty.get("allocated_dp_pa"),
            "design_flow_m3_s": duty.get("design_flow_m3_s"),
            "minimum_size_mm": duty.get("minimum_size_mm"),
            "required_material": duty.get("required_material"),
            "note": duty.get("sizing_note"),
        }

        suggested: dict[str, Any] | None = None
        if best is not None:
            component = best["component"]
            suggested = {
                "part_number": component["part_number"],
                "brand": component["brand"],
                "description": component["component_name"],
                "flow_coefficient": component["flow_coefficient_value"],
                "flow_coefficient_type": component["flow_coefficient_type"],
                "nominal_size_mm": component["nominal_size_mm"],
                "material": component["material"],
                "pressure_rating_bar": component["pressure_rating_bar"],
                "max_temperature_c": component["max_temperature_c"],
                "datasheet_url": component["datasheet_url"],
                "verification_status": component["verification_status"],
                "oversize": best["score"],
                "warnings": best.get("warnings", []),
                "alternatives": [c["component"]["part_number"] for c in candidates[1:]],
            }

        rows.append(
            {
                "tag": tag,
                "loop": duty.get("loop"),
                "schedule_type": duty.get("schedule_type"),
                "calculated": {k: v for k, v in calculated.items() if v is not None},
                "suggested": suggested,
                # Unset on purpose. The engineer picks per component.
                "decision": None,
                "action_required": (
                    "choose" if suggested is not None else "source_externally"
                ),
                "unmet": result.get("unmet", []),
            }
        )

    needs_sourcing = [r["tag"] for r in rows if r["action_required"] == "source_externally"]
    return {
        "rows": rows,
        "needs_external_sourcing": needs_sourcing,
        "undecided": [r["tag"] for r in rows if r["decision"] is None],
        "ready_to_publish": False,
        "note": (
            "Every row needs a decision before the design is published. A suggested "
            "part is a capacity shortlist, not a specification; a tag listed under "
            "needs_external_sourcing has no catalogue answer and requires a component "
            "sourced from vendor literature."
        ),
    }
