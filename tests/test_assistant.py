import json
import unittest
from unittest.mock import patch

from datacenter_equipment_finder.assistant import AssistantConfig, local_parse_query, run_assistant_query
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

    def test_local_parse_extracts_connection_size_and_cdu_subtype(self):
        parsed = local_parse_query(
            "find in row cdu with 2.5 inch pipe connection around 1000 kw top 2",
            self.service,
        )
        self.assertEqual(parsed["category"], "cdu")
        self.assertEqual(parsed["component_subtype"], "in_row_cdu")
        self.assertAlmostEqual(parsed["connection_size_inch"], 2.5)
        self.assertAlmostEqual(parsed["connection_size_mm"], 63.5)
        self.assertAlmostEqual(parsed["size_mm"], 63.5)
        self.assertEqual(parsed["top_n"], 2)

    def test_local_assistant_checks_drop_invalid_cdu_kv(self):
        result = run_assistant_query(
            "find in rack cdu with 1.25 inch pipe kv 6 around 250 kw",
            self.service,
            mode="local",
        )
        self.assertEqual(result["filters"]["component_subtype"], "in_rack_cdu")
        self.assertIsNone(result["filters"]["kv"])
        self.assertTrue(any("Cv/Kv inputs were ignored" in check for check in result["checks"]))
        top = result["matches"][0]["component"]
        self.assertEqual(top["category"], "cdu")
        self.assertEqual(top["component_subtype"], "in_rack_cdu")

    def test_local_parse_fuzzy_matches_typo_terms(self):
        parsed = local_parse_query(
            "find parkar chek valve 20 mm kv 6",
            self.service,
        )
        self.assertEqual(parsed["brand"], "Parker")
        self.assertEqual(parsed["component_subtype"], "check_valve")

    def test_local_model_overlay_enriches_local_mode(self):
        payload = {"response": json.dumps({"brand": "Danfoss", "component_subtype": "check_valve", "top_n": 1})}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch("datacenter_equipment_finder.assistant.urlopen", return_value=FakeResponse()):
            result = run_assistant_query(
                "find danfos chek valve kv 6",
                self.service,
                mode="local",
                config=AssistantConfig(
                    local_endpoint="http://127.0.0.1:11434/api/generate",
                    local_model="llama3.1",
                ),
            )
        self.assertEqual(result["mode_used"], "local_model+rules")
        self.assertEqual(result["filters"]["brand"], "Danfoss")
        self.assertEqual(result["filters"]["component_subtype"], "check_valve")
        self.assertEqual(result["filters"]["top_n"], 1)


if __name__ == "__main__":
    unittest.main()
