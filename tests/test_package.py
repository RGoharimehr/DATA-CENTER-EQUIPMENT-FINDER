import unittest

from datacenter_equipment_finder.catalog import EquipmentCatalog
from datacenter_equipment_finder.compatibility import check_compatibility
from datacenter_equipment_finder.matching import find_closest_components
from datacenter_equipment_finder.units import cv_to_kv, kv_to_cv, inch_to_mm, mm_to_inch, tons_to_kw, kw_to_tons


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.catalog = EquipmentCatalog.from_csv()

    def test_catalog_has_cdu_and_chiller_from_multiple_vendors(self):
        cdu_vendors = {c.brand for c in self.catalog.components if c.category == "cdu"}
        chiller_vendors = {c.brand for c in self.catalog.components if c.category == "chiller"}
        self.assertGreaterEqual(len(cdu_vendors), 2)
        self.assertGreaterEqual(len(chiller_vendors), 2)

    def test_unit_conversion_roundtrips(self):
        self.assertAlmostEqual(mm_to_inch(inch_to_mm(2.0)), 2.0, places=6)
        self.assertAlmostEqual(kv_to_cv(cv_to_kv(7.5)), 7.5, places=6)
        self.assertAlmostEqual(kw_to_tons(tons_to_kw(5.0)), 5.0, places=6)

    def test_find_closest_valve_by_size_and_cv(self):
        result = find_closest_components(
            self.catalog.components,
            category="valve",
            target_size_mm=20,
            target_cv=7.0,
            top_n=1,
        )[0]
        self.assertEqual(result.component.part_number, "S4A-20")

    def test_compatibility_detects_connection_time_limit(self):
        parts = [
            c for c in self.catalog.components if c.part_number in {"LLD-20", "DML-20"}
        ]
        report = check_compatibility(parts, max_install_connection_time_min=33)
        self.assertFalse(report.is_compatible)
        self.assertTrue(any("Connection time too high" in r for r in report.reasons))


if __name__ == "__main__":
    unittest.main()
