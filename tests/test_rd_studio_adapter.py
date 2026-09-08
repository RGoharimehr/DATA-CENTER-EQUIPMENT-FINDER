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
