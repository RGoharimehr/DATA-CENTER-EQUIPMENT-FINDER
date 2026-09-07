"""Regression tests for the matching and query-parsing engine.

Each test here corresponds to a defect found by probing the engine with realistic
queries, so they are written as behaviour assertions rather than fixed part numbers.
"""

from datacenter_equipment_finder import EquipmentCatalog, EquipmentService
from datacenter_equipment_finder.assistant import _best_brand, local_parse_query, run_assistant_query
from datacenter_equipment_finder.matching import find_closest_components


def _service() -> EquipmentService:
    return EquipmentService(EquipmentCatalog.from_csv())


# --- duty limits -----------------------------------------------------------------

def test_pressure_duty_excludes_under_rated_parts() -> None:
    catalog = _service().catalog
    matches = find_closest_components(
        catalog.components, category="quick_disconnect", target_cv=2.4,
        required_pressure_bar=15.0, top_n=10,
    )
    assert matches
    for m in matches:
        rating = m.component.pressure_rating_bar
        assert rating is None or rating >= 15.0, f"{m.component.part_number} is rated {rating} bar"


def test_temperature_duty_excludes_under_rated_parts() -> None:
    catalog = _service().catalog
    matches = find_closest_components(
        catalog.components, category="quick_disconnect", target_cv=2.4,
        required_temperature_c=70.0, top_n=10,
    )
    assert matches
    for m in matches:
        tmax = m.component.max_temperature_c
        assert tmax is None or tmax >= 70.0, f"{m.component.part_number} tops out at {tmax} C"


def test_unpublished_rating_is_kept_but_flagged() -> None:
    # An unknown rating cannot be proven inadequate, so the row survives with a warning
    # rather than being silently dropped or silently trusted.
    catalog = _service().catalog
    matches = find_closest_components(
        catalog.components, category="cdu", target_capacity_kw=1000,
        required_pressure_bar=8.0, top_n=10,
    )
    unpublished = [m for m in matches if m.component.pressure_rating_bar is None]
    assert unpublished, "expected at least one row without a published pressure rating"
    for m in unpublished:
        assert any("pressure rating not published" in w for w in m.warnings)


def test_impossible_duty_reports_rather_than_returning_junk() -> None:
    result = run_assistant_query("quick disconnect rated for 40 bar", _service(), mode="local")
    assert result["matches"] == []
    assert any("No catalog component is rated for" in c for c in result["checks"])


# --- ranking ---------------------------------------------------------------------

def test_missing_data_does_not_beat_a_reasonable_match() -> None:
    catalog = _service().catalog
    with_capacity = [c for c in catalog.components if c.capacity_kw is not None]
    best = find_closest_components(with_capacity, category="cdu", target_capacity_kw=1000, top_n=1)[0]
    # A row 10% from target must beat a row with no capacity figure at all.
    assert best.component.capacity_kw is not None
    assert best.score < 0.75


def test_primary_criterion_outweighs_connection_size() -> None:
    # A CDU three times off the requested duty must not win on connection size alone.
    catalog = _service().catalog
    top = find_closest_components(
        catalog.components, category="cdu", component_subtype="in_row_cdu",
        target_connection_size_inch=2.5, target_capacity_kw=1000, top_n=1,
    )[0]
    assert top.component.capacity_kw is not None
    assert abs(top.component.capacity_kw - 1000) / 1000 < 0.5


def test_unverified_rows_are_flagged_in_results() -> None:
    catalog = _service().catalog
    matches = find_closest_components(catalog.components, category="cdu", target_capacity_kw=1000, top_n=10)
    for m in matches:
        if m.component.verification_status != "verified":
            assert any("not verified" in w for w in m.warnings), m.component.part_number


def test_scores_are_relative_error_so_a_close_match_scores_near_zero() -> None:
    catalog = _service().catalog
    top = find_closest_components(
        catalog.components, category="quick_disconnect", target_cv=2.45,
        required_pressure_bar=15.0, top_n=1,
    )[0]
    assert top.score < 0.05


# --- query parsing ---------------------------------------------------------------

def test_brand_is_not_invented_from_unrelated_words() -> None:
    service = _service()
    brands = service.schema()["brands"]
    for query in (
        "show me a strainer",              # previously matched Trane
        "cooling unit 500 kw",             # previously matched CoolIT
        "give me a strainer with low pressure drop",
        "coolant distribution unit",
        "dry break connector",
    ):
        assert _best_brand(query, brands) is None, query


def test_brand_still_survives_a_typo() -> None:
    brands = _service().schema()["brands"]
    assert _best_brand("parkar chek valve", brands) == "Parker"
    assert _best_brand("danfos ball valve", brands) == "Danfoss"


def test_megawatt_queries_are_understood() -> None:
    service = _service()
    assert local_parse_query("cdu for a 1 MW rack row", service)["capacity_kw"] == 1000.0
    assert local_parse_query("something for 2 megawatt heat load", service)["capacity_kw"] == 2000.0


def test_duty_limits_are_parsed_from_natural_language() -> None:
    service = _service()
    assert local_parse_query("quick disconnect rated for 15 bar", service)["required_pressure_bar"] == 15.0
    assert local_parse_query("UQD for 70 C coolant temperature", service)["required_temperature_c"] == 70.0


def test_rating_conditions_are_not_mistaken_for_duty_limits() -> None:
    # "1350 kW at 4 C approach" states the condition a capacity is quoted at, not a
    # coolant temperature the part must withstand.
    filters = local_parse_query("cdu 1350 kw at 4 C approach", _service())
    assert filters["required_temperature_c"] is None
    assert filters["capacity_kw"] == 1350.0


def test_psi_is_converted_to_bar() -> None:
    filters = local_parse_query("quick disconnect for a 150 psi system", _service())
    assert filters["required_pressure_bar"] is not None
    assert abs(filters["required_pressure_bar"] - 10.34) < 0.05
