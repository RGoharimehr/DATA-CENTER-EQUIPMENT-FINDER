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
