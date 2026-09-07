from datacenter_equipment_finder import EquipmentCatalog, EquipmentService
from datacenter_equipment_finder.assistant import local_parse_query
from datacenter_equipment_finder.explanations import explain_category


def _service() -> EquipmentService:
    return EquipmentService(EquipmentCatalog.from_csv())


def test_quick_disconnect_is_a_first_class_category() -> None:
    schema = _service().schema()
    assert "quick_disconnect" in schema["categories"]
    assert "cv_or_kv" in schema["input_hints"]["quick_disconnect"]
    assert set(schema["subtypes_by_category"]["quick_disconnect"]) == {"hand_mate_uqd", "blind_mate_uqd"}


def test_quick_disconnect_matches_on_flow_coefficient() -> None:
    matches = _service().find_components(category="quick_disconnect", cv=2.4, top_n=3)
    assert matches
    coefficients = [m["component"]["flow_coefficient_value"] for m in matches]
    # Cv must actually drive ranking, so the closest catalog value has to come back first.
    assert min(abs(c - 2.4) for c in coefficients) == abs(coefficients[0] - 2.4)


def test_every_quick_disconnect_row_carries_a_flow_coefficient() -> None:
    rows = _service().list_components(category="quick_disconnect", limit=100)
    assert rows
    for row in rows:
        assert row["flow_coefficient_type"] in {"Cv", "Kv"}, row["part_number"]
        assert row["flow_coefficient_value"] is not None, row["part_number"]


def test_assistant_understands_uqd_vocabulary() -> None:
    service = _service()
    for query in ("find a UQD08 coupling", "quick disconnect with cv 1.2", "dry break connector for the rack loop"):
        filters = local_parse_query(query, service)
        assert filters["category"] == "quick_disconnect", query


def test_assistant_recognises_blind_mate_subtype() -> None:
    filters = local_parse_query("blind mate quick disconnect cv 1.25", _service())
    assert filters["category"] == "quick_disconnect"
    assert filters["component_subtype"] == "blind_mate_uqd"


def test_assistant_parses_fractional_inch_connection_sizes() -> None:
    filters = local_parse_query("quick disconnect for 3/8 inch line", _service())
    assert filters["connection_size_inch"] == 0.375
    assert filters["connection_size_mm"] is not None
    assert abs(filters["connection_size_mm"] - 9.525) < 1e-6


def test_quick_disconnect_has_an_explanation() -> None:
    text = explain_category("quick_disconnect")
    assert "UQD" in text
    assert text != "No explanation available for this category."
