"""Provenance rules for catalog data.

Every row in this catalog is meant to be traceable to a published vendor
document. These tests exist so that fabricated specifications cannot be added
without the suite going red.
"""

from collections import Counter

from datacenter_equipment_finder import EquipmentCatalog


def _components() -> list:
    return EquipmentCatalog.from_csv().components


def test_every_row_cites_a_source_document() -> None:
    for c in _components():
        assert c.source_catalog, f"{c.part_number} has no source_catalog"
        assert c.datasheet_url, f"{c.part_number} has no datasheet_url"
        assert c.datasheet_url.startswith(("http://", "https://")), c.part_number


def test_part_numbers_are_unique() -> None:
    counts = Counter(c.part_number.lower() for c in _components())
    assert [p for p, n in counts.items() if n > 1] == []


def test_capacity_units_agree() -> None:
    # 1 ton of refrigeration = 3.5168525 kW; catalogs that disagree are transcription errors.
    for c in _components():
        if c.capacity_kw is None or c.capacity_tons is None:
            continue
        implied = c.capacity_tons * 3.5168525
        assert abs(implied - c.capacity_kw) / c.capacity_kw < 0.02, f"{c.part_number}: {c.capacity_kw} kW vs {c.capacity_tons} TR"


def test_size_units_agree() -> None:
    for c in _components():
        if c.nominal_size_mm is None or c.nominal_size_inch is None:
            continue
        implied = c.nominal_size_inch * 25.4
        assert abs(implied - c.nominal_size_mm) / c.nominal_size_mm < 0.05, f"{c.part_number}: {c.nominal_size_mm} mm vs {c.nominal_size_inch} in"


def test_flow_coefficient_rows_declare_their_type() -> None:
    for c in _components():
        if c.flow_coefficient_value is None:
            continue
        assert c.flow_coefficient_type in {"Cv", "Kv"}, c.part_number
