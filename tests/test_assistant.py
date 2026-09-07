import unittest

from datacenter_equipment_finder.assistant import local_parse_query, run_assistant_query
from datacenter_equipment_finder.service import EquipmentService


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.service = EquipmentService.default()

    def test_local_parse_extracts_filters(self):
        parsed = local_parse_query(
            "Find Danfoss check_valve 20 mm kv 6 top 3",
            self.service,
        )
        self.assertEqual(parsed["brand"], "Danfoss")
        self.assertEqual(parsed["component_subtype"], "check_valve")
        self.assertEqual(parsed["size_mm"], 20.0)
        self.assertEqual(parsed["kv"], 6.0)
        self.assertEqual(parsed["top_n"], 3)

    def test_hybrid_falls_back_to_local(self):
        result = run_assistant_query(
            "find cdu around 1000 kw from Johnson Controls",
            self.service,
            mode="hybrid",
        )
        self.assertIn(result["mode_used"], {"hybrid_local_only", "hybrid_remote+local"})
        self.assertTrue(result["matches"])


if __name__ == "__main__":
    unittest.main()
