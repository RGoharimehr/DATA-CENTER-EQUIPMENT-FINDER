"""Regression tests for the compatibility engine.

Each corresponds to a defect found by running real catalog selections through it.
"""

from datacenter_equipment_finder import EquipmentCatalog, EquipmentService


def _service() -> EquipmentService:
    return EquipmentService(EquipmentCatalog.from_csv())


def test_material_families_are_compared_not_raw_strings() -> None:
    # "316L Stainless Steel" and "SS303" are both austenitic stainless. Comparing the
    # strings reported a mismatch between two parts made of the same thing.
    report = _service().compatibility(
        ["7245-00203", "Hansen UQD06"], required_material="Stainless Steel"
    )
    assert not any("Material mismatch" in r for r in report["reasons"]), report["reasons"]


def test_material_mismatch_is_still_caught_across_families() -> None:
    report = _service().compatibility(["023Z5068"], required_material="Stainless Steel")
    assert any("Material mismatch" in r for r in report["reasons"])


def test_assembly_envelope_names_the_governing_component() -> None:
    report = _service().compatibility(["Hansen UQD06", "009L8622"])
    assert report["limits"]["governing_pressure_bar"] == 6.9
    assert report["limits"]["governing_temperature_c"] == 65.0
    assert any("limited to 6.9 bar by Hansen UQD06" in n for n in report["notes"])


def test_duty_above_the_weakest_part_is_an_incompatibility() -> None:
    report = _service().compatibility(
        ["Hansen UQD06", "009L8622"], required_pressure_bar=15.0
    )
    assert not report["is_compatible"]
    assert any("Pressure rating too low" in r and "Hansen UQD06" in r for r in report["reasons"])


def test_temperature_duty_is_checked() -> None:
    report = _service().compatibility(["Hansen UQD06"], required_temperature_c=90.0)
    assert not report["is_compatible"]
    assert any("Temperature rating too low" in r for r in report["reasons"])


def test_quick_disconnects_take_part_in_connection_checks() -> None:
    # quick_disconnect was in neither category set, so its end connection was never
    # compared against anything: an ORB coupling and an ODF solder valve passed.
    report = _service().compatibility(["7245-00203", "009L8622"])
    assert any("Connection mismatch" in r for r in report["reasons"]), report["reasons"]


def test_equivalent_connection_wording_is_not_a_mismatch() -> None:
    report = _service().compatibility(["023Z5068", "C-609-S"])
    assert not any("Connection mismatch" in r for r in report["reasons"]), report["reasons"]


def test_coolant_families_are_recognised() -> None:
    # "Water/EGW/PGW" is a water/glycol duty; a substring test called it a mismatch.
    report = _service().compatibility(["Boyd 10U CDU"], required_coolant="Water/Glycol")
    assert not any("Coolant mismatch" in r for r in report["reasons"]), report["reasons"]


def test_incompatible_coolant_is_still_caught() -> None:
    report = _service().compatibility(["Boyd 10U CDU"], required_coolant="Ammonia")
    assert any("Coolant mismatch" in r for r in report["reasons"])


def test_unverified_and_disputed_parts_are_surfaced() -> None:
    report = _service().compatibility(["CK2-32"])
    assert any("does not support" in n for n in report["notes"])


def test_notes_do_not_by_themselves_make_a_selection_incompatible() -> None:
    report = _service().compatibility(["Boyd 10U CDU"])
    assert report["is_compatible"]
    assert report["limits"]["governing_pressure_bar"] == 5.0
