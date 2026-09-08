import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from datacenter_equipment_finder.service import EquipmentService
from datacenter_equipment_finder.web import API_PREFIX, ServerConfig, create_handler


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service = EquipmentService.default()
        handler = create_handler(service, config=ServerConfig(api_key=None, rate_limit_per_minute=200))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def _get_json(self, path: str):
        with urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get_text(self, path: str) -> str:
        with urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:
            return resp.read().decode("utf-8")

    def test_schema_endpoint(self):
        payload = self._get_json(f"{API_PREFIX}/schema")
        self.assertTrue(payload["ok"])
        self.assertIn("fields", payload["data"])
        self.assertIn("categories", payload["data"])
        self.assertIn("brands", payload["data"])

    def test_find_endpoint(self):
        payload = self._get_json(f"{API_PREFIX}/find?category=valve&component_subtype=shutoff_valve&size_mm=20&cv=7&top_n=1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"][0]["component"]["component_subtype"], "shutoff_valve")

    def test_find_endpoint_accepts_connection_size(self):
        payload = self._get_json(
            f"{API_PREFIX}/find?category=cdu&component_subtype=in_row_cdu&connection_size_inch=2.5&capacity_kw=1000&top_n=1"
        )
        self.assertTrue(payload["ok"])
        component = payload["data"][0]["component"]
        self.assertEqual(component["category"], "cdu")
        self.assertEqual(component["component_subtype"], "in_row_cdu")

    def test_compat_endpoint(self):
        body = json.dumps(
            {
                "part_numbers": ["LLD-20", "023Z5053"],
                "max_connection_time": 33,
            }
        ).encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{self.port}{API_PREFIX}/compat",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["is_compatible"])
        self.assertGreaterEqual(payload["data"]["selected_count"], 2)

    def test_assistant_endpoint(self):
        body = json.dumps({"query": "find check_valve 20 mm kv 6 from danfoss", "mode": "hybrid"}).encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{self.port}{API_PREFIX}/assistant",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["matches"])

    def test_assistant_endpoint_extracts_connection_size(self):
        body = json.dumps(
            {"query": "find in row cdu with 2.5 inch pipe connection around 1000 kw", "mode": "local"}
        ).encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{self.port}{API_PREFIX}/assistant",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertAlmostEqual(payload["data"]["filters"]["connection_size_inch"], 2.5)
        top = payload["data"]["matches"][0]["component"]
        self.assertEqual(top["category"], "cdu")
        self.assertEqual(top["component_subtype"], "in_row_cdu")

    def test_legacy_route_still_works(self):
        payload = self._get_json("/api/find?category=valve&component_subtype=shutoff_valve&size_mm=20&cv=7&top_n=1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"][0]["component"]["component_subtype"], "shutoff_valve")

    def test_invalid_find_request_fails(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get_json(f"{API_PREFIX}/find?cv=1&kv=1")
        self.assertEqual(ctx.exception.code, 400)

    def test_cdu_rejects_cv_kv_input(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get_json(f"{API_PREFIX}/find?category=cdu&cv=2")
        self.assertEqual(ctx.exception.code, 400)

    def test_assistant_endpoint_rejects_invalid_mode(self):
        body = json.dumps({"query": "find check valve", "mode": "bad"}).encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{self.port}{API_PREFIX}/assistant",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_find_endpoint_rejects_invalid_limit_values(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get_json(f"{API_PREFIX}/components?limit=0")
        self.assertEqual(ctx.exception.code, 400)

    def test_index_is_a_browse_page_with_no_selection_logic(self):
        # Selection semantics live in one place: the Python engine. The served page
        # browses the catalogue and adds to it; it does not rank anything.
        html = self._get_text("/")
        self.assertIn('id="api-key"', html)
        self.assertIn('id="rows"', html)
        self.assertIn("/api/v1/components", html)
        for absent in ("UNKNOWN_PENALTY", "oversize", "find?category"):
            self.assertNotIn(absent, html)


class WebApiAuthAndRateLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service = EquipmentService.default()
        handler = create_handler(service, config=ServerConfig(api_key="token123", rate_limit_per_minute=100))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def _get(self, path: str, headers: dict[str, str] | None = None):
        req = Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_requires_api_key(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get(f"{API_PREFIX}/schema")
        self.assertEqual(ctx.exception.code, 401)

    def test_allows_with_api_key(self):
        payload = self._get(f"{API_PREFIX}/schema", {"X-API-Key": "token123"})
        self.assertTrue(payload["ok"])

    def test_rate_limit(self):
        service = EquipmentService.default()
        handler = create_handler(service, config=ServerConfig(api_key=None, rate_limit_per_minute=2))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            with urlopen(f"http://127.0.0.1:{port}{API_PREFIX}/health"):
                pass
            with urlopen(f"http://127.0.0.1:{port}{API_PREFIX}/health"):
                pass
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}{API_PREFIX}/health")
            self.assertEqual(ctx.exception.code, 429)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()


class AddComponentTests(unittest.TestCase):
    """Adding a row through the browse page runs the catalogue's own validation."""

    def _add(self, **overrides):
        import tempfile
        from pathlib import Path

        from datacenter_equipment_finder.catalog import EquipmentCatalog
        from datacenter_equipment_finder.catalog_tools import append_component

        row = {
            "part_number": "TEST-VALVE-1", "brand": "Acme", "category": "valve",
            "component_name": "Test valve", "flow_coefficient_type": "Kv",
            "flow_coefficient_value": "12.5", "source_catalog": "Acme datasheet A-1",
            "datasheet_url": "https://example.com/a-1.pdf",
        }
        row.update(overrides)
        row = {k: v for k, v in row.items() if v is not None}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vendors = root / "vendors"
            vendors.mkdir()
            source = EquipmentCatalog.default_csv_path().read_text(encoding="utf-8")
            (vendors / "seed.csv").write_text(source, encoding="utf-8")
            catalog = root / "equipment_catalog.csv"
            catalog.write_text(source, encoding="utf-8")
            return append_component(row, vendors_dir=vendors, catalog_csv=catalog)

    def test_a_valid_component_is_added(self):
        outcome = self._add()
        self.assertTrue(outcome["added"], outcome)
        self.assertEqual(outcome["part_number"], "TEST-VALVE-1")

    def test_an_unknown_category_is_rejected(self):
        outcome = self._add(category="coolant_distribution_unit")
        self.assertFalse(outcome["added"])
        self.assertTrue(any("unknown category" in e for e in outcome["errors"]), outcome)

    def test_a_row_with_nothing_to_match_on_is_rejected(self):
        outcome = self._add(flow_coefficient_value=None)
        self.assertFalse(outcome["added"])
        self.assertTrue(any("nothing to match on" in e for e in outcome["errors"]), outcome)

    def test_a_row_without_a_source_is_rejected(self):
        outcome = self._add(source_catalog=None)
        self.assertFalse(outcome["added"])
        self.assertTrue(any("missing source_catalog" in e for e in outcome["errors"]), outcome)

    def test_a_duplicate_part_number_is_rejected(self):
        outcome = self._add(part_number="009L8620")
        self.assertFalse(outcome["added"])
        self.assertTrue(any("already in the catalogue" in e for e in outcome["errors"]), outcome)

    def test_an_unrecognised_verification_status_falls_back_to_unverified(self):
        outcome = self._add(verification_status="definitely-fine")
        self.assertTrue(outcome["added"], outcome)


class PostRouteTests(unittest.TestCase):
    """The POST routes are reachable over HTTP.

    A route added below do_POST's fall-through 404 is dead code that unit tests,
    ruff and mypy all pass over. /api/v1/select shipped that way and was never
    reachable, so these exercise the real server.
    """

    @classmethod
    def setUpClass(cls):
        service = EquipmentService.default()
        handler = create_handler(service, config=ServerConfig(api_key=None, rate_limit_per_minute=200))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _post(self, path, payload):
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_select_is_reachable(self):
        status, payload = self._post(
            f"{API_PREFIX}/select",
            {"items": [{"tag": "T1", "category": "valve", "required_cv": 20.0}]},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["items"][0]["candidates"])

    def test_add_component_is_reachable_and_validates(self):
        status, payload = self._post(
            f"{API_PREFIX}/components",
            {"part_number": "X", "brand": "Acme", "category": "cooling_unit",
             "component_name": "x", "source_catalog": "y", "flow_coefficient_value": "1"},
        )
        self.assertEqual(status, 422)
        self.assertFalse(payload["data"]["added"])
        self.assertTrue(any("unknown category" in e for e in payload["data"]["errors"]))

    def test_every_advertised_post_route_answers(self):
        # The openapi listing must not advertise a route the handler never reaches.
        with urlopen(f"http://127.0.0.1:{self.port}{API_PREFIX}/openapi.json") as response:
            spec = json.loads(response.read().decode("utf-8"))["data"]
        for route, methods in spec["paths"].items():
            if "post" not in methods:
                continue
            status, _ = self._post(route, {})
            self.assertNotEqual(status, 404, f"{route} is advertised but not routed")
