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
        self.assertEqual(payload["data"][0]["component"]["part_number"], "S4A-20")

    def test_compat_endpoint(self):
        body = json.dumps(
            {
                "part_numbers": ["LLD-20", "DML-20"],
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

    def test_legacy_route_still_works(self):
        payload = self._get_json("/api/find?category=valve&component_subtype=shutoff_valve&size_mm=20&cv=7&top_n=1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"][0]["component"]["part_number"], "S4A-20")

    def test_invalid_find_request_fails(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get_json(f"{API_PREFIX}/find?cv=1&kv=1")
        self.assertEqual(ctx.exception.code, 400)

    def test_cdu_rejects_cv_kv_input(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get_json(f"{API_PREFIX}/find?category=cdu&cv=2")
        self.assertEqual(ctx.exception.code, 400)

    def test_index_includes_api_key_support_for_browser_requests(self):
        html = self._get_text("/")
        self.assertIn('id="api-key"', html)
        self.assertIn("'X-API-Key': apiKey", html)
        self.assertIn("localStorage.getItem('dcef-api-key')", html)


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
