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


# DN and NPS are parallel nominal designations, not a unit conversion: DN15 is the
# nominal equivalent of NPS 1/2 even though 15 mm is not 12.7 mm. Rows that use pipe
# nominal sizes are checked against this table instead of against 25.4 mm/in.
DN_TO_NPS_INCH = {
    6: 0.125, 8: 0.25, 10: 0.375, 15: 0.5, 20: 0.75, 25: 1.0, 32: 1.25, 40: 1.5,
    50: 2.0, 65: 2.5, 80: 3.0, 100: 4.0, 125: 5.0, 150: 6.0, 200: 8.0, 250: 10.0, 300: 12.0,
}


def test_size_units_agree() -> None:
    for c in _components():
        if c.nominal_size_mm is None or c.nominal_size_inch is None:
            continue
        # Tube/ODF sizes convert exactly.
        implied = c.nominal_size_inch * 25.4
        if abs(implied - c.nominal_size_mm) / c.nominal_size_mm < 0.05:
            continue
        # Otherwise the row must be a recognised DN/NPS pair.
        dn = round(c.nominal_size_mm)
        assert DN_TO_NPS_INCH.get(dn) == c.nominal_size_inch, (
            f"{c.part_number}: {c.nominal_size_mm} mm vs {c.nominal_size_inch} in "
            "is neither an exact conversion nor a standard DN/NPS pair"
        )


def test_flow_coefficient_rows_declare_their_type() -> None:
    for c in _components():
        if c.flow_coefficient_value is None:
            continue
        assert c.flow_coefficient_type in {"Cv", "Kv"}, c.part_number


ALLOWED_VERIFICATION = {"verified", "unverified", "disputed"}


def test_verification_status_is_declared() -> None:
    for c in _components():
        assert c.verification_status in ALLOWED_VERIFICATION, f"{c.part_number}: {c.verification_status}"


def test_verified_rows_cite_a_specific_document_not_a_landing_page() -> None:
    # A row is only "verified" if its figures were read from the cited document, which
    # means the URL has to point at something more specific than a vendor home page.
    for c in _components():
        if c.verification_status != "verified":
            continue
        assert c.datasheet_url is not None
        path = c.datasheet_url.split("://", 1)[-1]
        assert "/" in path.rstrip("/"), f"{c.part_number} cites a bare domain: {c.datasheet_url}"


def test_disputed_rows_are_pushed_below_verified_ones() -> None:
    from datacenter_equipment_finder.matching import find_closest_components

    components = _components()
    disputed = [c for c in components if c.verification_status == "disputed"]
    assert disputed, "expected the audit to have flagged at least one row"
    for m in find_closest_components(components, category="valve", target_cv=7.0, top_n=20):
        if m.component.verification_status == "disputed":
            assert any("does not support" in w for w in m.warnings), m.component.part_number
