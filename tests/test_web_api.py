import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from datacenter_equipment_finder.service import EquipmentService
from datacenter_equipment_finder.web import create_handler


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service = EquipmentService.default()
        handler = create_handler(service)
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

    def test_schema_endpoint(self):
        payload = self._get_json("/api/schema")
        self.assertIn("fields", payload)
        self.assertIn("categories", payload)
        self.assertIn("brands", payload)

    def test_find_endpoint(self):
        payload = self._get_json("/api/find?category=valve&size_mm=20&cv=7&top_n=1")
        self.assertEqual(payload[0]["component"]["part_number"], "S4A-20")

    def test_compat_endpoint(self):
        body = json.dumps(
            {
                "part_numbers": ["LLD-20", "DML-20"],
                "max_connection_time": 33,
            }
        ).encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{self.port}/api/compat",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertFalse(payload["is_compatible"])
        self.assertGreaterEqual(payload["selected_count"], 2)


if __name__ == "__main__":
    unittest.main()
