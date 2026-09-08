"""Reading a reference-design generator's valve schedule."""

from __future__ import annotations

from pathlib import Path

from datacenter_equipment_finder import EquipmentCatalog, EquipmentService
from datacenter_equipment_finder.rd_studio import duties_from_valve_schedule

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rd_studio"
MANUAL = FIXTURES / "valve_schedule_manual.csv"
PRELIMINARY = FIXTURES / "valve_schedule_preliminary.csv"


def _service() -> EquipmentService:
    return EquipmentService(EquipmentCatalog.from_csv())


def test_rows_are_grouped_into_distinct_duties() -> None:
    # The real 126-row schedule of a 32-rack design holds eight distinct duties.
    # Selecting per row would repeat the same answer 64 times.
    duties = duties_from_valve_schedule(MANUAL)
    assert len(duties) == 8
    tags = {d["tag"] for d in duties}
    assert "TCS-isolation_valve-2in" in tags
    assert "FWS-balancing_valve-8in" in tags


def test_schedule_types_map_onto_the_catalogue_vocabulary() -> None:
    from datacenter_equipment_finder.catalog import KNOWN_CATEGORIES

    for duty in duties_from_valve_schedule(MANUAL):
        assert duty["category"] in KNOWN_CATEGORIES, duty["tag"]


def test_service_becomes_the_loop_and_material_a_requirement() -> None:
    by_tag = {d["tag"]: d for d in duties_from_valve_schedule(MANUAL)}
    assert by_tag["TCS-isolation_valve-2in"]["loop"] == "TCS"
    assert by_tag["TCS-isolation_valve-2in"]["required_material"] == "Copper"
    assert by_tag["FWS-isolation_valve-8in"]["loop"] == "FWS"
    assert by_tag["FWS-isolation_valve-8in"]["required_material"] == "Carbon Steel"


def test_nominal_inches_become_a_minimum_bore() -> None:
    by_tag = {d["tag"]: d for d in duties_from_valve_schedule(MANUAL)}
    assert by_tag["TCS-isolation_valve-2in"]["minimum_size_mm"] == 50.8


def test_a_manual_mode_schedule_carries_no_duty_to_select_against() -> None:
    # Every row of the real export reports "unassigned; manual geometry sizing" with an
    # empty valve_Cv. Selecting from nominal bore alone would look like an engineering
    # result and rest on nothing.
    duties = duties_from_valve_schedule(MANUAL)
    assert all("duty_unassigned" in d for d in duties)
    assert all("required_cv" not in d for d in duties)

    report = _service().select_for_duty(duties)
    assert len(report["unresolved"]) == len(duties)
    assert all(not item["candidates"] for item in report["items"])
    assert "manual geometry sizing" in report["items"][0]["unmet"][0]


def test_a_preliminary_schedule_carries_the_required_cv() -> None:
    by_tag = {d["tag"]: d for d in duties_from_valve_schedule(PRELIMINARY)}
    duty = by_tag["TCS-isolation_valve-2in"]
    assert duty["required_cv"] == 18.5
    assert duty["allocated_dp_pa"] == 20000
    assert "duty_unassigned" not in duty


def test_selection_keeps_the_loops_apart() -> None:
    duties = duties_from_valve_schedule(PRELIMINARY)
    report = _service().select_for_duty(duties)
    for loop, assembly in report["assemblies_by_loop"].items():
        assert loop in {"TCS", "FWS"}
        assert "governing_pressure_bar" in assembly["limits"]


def test_quantities_are_carried_through() -> None:
    duties = duties_from_valve_schedule(MANUAL)
    assert all(d["quantity"] >= 1 for d in duties)
    assert all(d["tags"] for d in duties)


SIZING = FIXTURES / "sizing_preliminary.json"


def _sizing() -> list:
    import json

    return json.loads(SIZING.read_text(encoding="utf-8"))["valve_capacities"]


def _schedule_rows() -> list:
    import csv

    with MANUAL.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_only_throttling_valves_carry_a_required_coefficient() -> None:
    # The generator computes Kv for balancing and control valves only. An isolation or
    # check valve is on/off, and its full-open Kv is not a design constraint, so it
    # must not be judged against a throttling figure it was never sized for.
    from datacenter_equipment_finder.rd_studio import duties_from_sizing

    by_tag = {d["tag"]: d for d in duties_from_sizing(_sizing(), _schedule_rows())}
    assert by_tag["TCS-R01K01-BV-001"]["required_cv"] == 18.5
    assert "required_cv" not in by_tag["TCS-C01-IV-001"]
    assert "on/off" in by_tag["TCS-C01-IV-001"]["sizing_note"]


def test_reconcile_pairs_calculated_with_suggested_and_leaves_the_choice_open() -> None:
    from datacenter_equipment_finder.rd_studio import duties_from_sizing, reconcile

    duties = duties_from_sizing(_sizing(), _schedule_rows())
    report = reconcile(duties, _service().select_for_duty(duties))

    row = next(r for r in report["rows"] if r["tag"] == "TCS-R01K01-BV-001")
    assert row["calculated"]["required_cv_us"] == 18.5
    assert row["suggested"]["part_number"]
    # The engineer decides; the tool does not.
    assert row["decision"] is None
    assert row["action_required"] == "choose"


def test_a_tag_with_no_candidate_is_marked_for_external_sourcing() -> None:
    from datacenter_equipment_finder.rd_studio import reconcile

    duties = [{"tag": "GIANT-BV", "category": "valve", "required_cv": 99999.0}]
    report = reconcile(duties, _service().select_for_duty(duties))
    row = report["rows"][0]
    assert row["suggested"] is None
    assert row["action_required"] == "source_externally"
    assert report["needs_external_sourcing"] == ["GIANT-BV"]


def test_nothing_is_publishable_until_every_row_is_decided() -> None:
    from datacenter_equipment_finder.rd_studio import duties_from_sizing, reconcile

    duties = duties_from_sizing(_sizing(), _schedule_rows())
    report = reconcile(duties, _service().select_for_duty(duties))
    assert report["ready_to_publish"] is False
    assert set(report["undecided"]) == {d["tag"] for d in duties}


def test_the_selection_core_needs_no_optional_dependencies() -> None:
    # It has to run inside a Pyodide worker beside the design engine, where rapidfuzz
    # and pypdf are not available.
    import subprocess
    import sys

    code = (
        "import sys\n"
        "for blocked in ('rapidfuzz', 'pypdf', 'pydantic'):\n"
        "    sys.modules[blocked] = None\n"
        "from datacenter_equipment_finder.service import EquipmentService\n"
        "from datacenter_equipment_finder.rd_studio import duties_from_sizing, reconcile\n"
        "assert EquipmentService.default().catalog.components\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


# --- decisions persist across Apply, keyed on the duty ----------------------------

def _reconciled(duties, previous=None):
    from datacenter_equipment_finder.rd_studio import reconcile

    return reconcile(duties, _service().select_for_duty(duties), previous)


def _decided(duty, choice="catalogue"):
    from datacenter_equipment_finder.rd_studio import decisions_from_rows, record_decision

    report = _reconciled([duty])
    row = report["rows"][0]
    row["decision"] = record_decision(row, choice)
    return decisions_from_rows(report["rows"])


BASE_DUTY = {
    "tag": "TCS-R01-BV-001", "loop": "TCS", "category": "valve",
    "schedule_type": "balancing_valve", "required_cv": 92.0, "minimum_size_mm": 127.0,
}


def test_a_decision_survives_an_apply_that_did_not_change_the_duty() -> None:
    # A 0.25 m pod move changes the applied hash and changes nothing about what part
    # fits. Wiping 126 valve decisions on every Apply would make the review unusable.
    previous = _decided(BASE_DUTY)
    again = _reconciled([dict(BASE_DUTY)], previous)
    row = again["rows"][0]
    assert row["decision"] is not None
    assert row["action_required"] == "decided"
    assert again["carried_forward"] == ["TCS-R01-BV-001"]
    assert again["ready_to_publish"] is True


def test_a_decision_is_dropped_when_the_duty_changes() -> None:
    previous = _decided(BASE_DUTY)
    changed = _reconciled([dict(BASE_DUTY, required_cv=420.0)], previous)
    row = changed["rows"][0]
    assert row["decision"] is None
    assert "the duty changed" in row["decision_invalidated"]
    assert changed["ready_to_publish"] is False


def test_a_decision_is_dropped_when_the_chosen_part_no_longer_meets_the_duty() -> None:
    # The catalogue can move under a decision: a row gets corrected, or superseded.
    from datacenter_equipment_finder.rd_studio import duty_fingerprint

    stale = {
        "TCS-R01-BV-001": {
            "choice": "catalogue",
            "part_number": "NO-SUCH-PART",
            "duty_fingerprint": duty_fingerprint(BASE_DUTY),
        }
    }
    report = _reconciled([dict(BASE_DUTY)], stale)
    row = report["rows"][0]
    assert row["decision"] is None
    assert "no longer meets this duty" in row["decision_invalidated"]


def test_geometry_and_hashes_do_not_enter_the_fingerprint() -> None:
    from datacenter_equipment_finder.rd_studio import duty_fingerprint

    moved = dict(BASE_DUTY, edge_id="E999", allocated_dp_pa=31000, design_flow_m3_s=0.02)
    assert duty_fingerprint(moved) == duty_fingerprint(BASE_DUTY)


def test_rounding_noise_does_not_invalidate_a_decision() -> None:
    from datacenter_equipment_finder.rd_studio import duty_fingerprint

    recomputed = dict(BASE_DUTY, required_cv=92.0000000001)
    assert duty_fingerprint(recomputed) == duty_fingerprint(BASE_DUTY)


def test_keeping_the_calculated_requirement_is_a_valid_decision() -> None:
    previous = _decided(BASE_DUTY, choice="calculated")
    report = _reconciled([dict(BASE_DUTY)], previous)
    assert report["rows"][0]["decision"]["choice"] == "calculated"
    assert report["ready_to_publish"] is True


def test_a_catalogue_choice_needs_a_part_number() -> None:
    import pytest

    from datacenter_equipment_finder.rd_studio import record_decision

    with pytest.raises(ValueError, match="part number"):
        record_decision({"duty_fingerprint": "abc", "suggested": None}, "catalogue")
