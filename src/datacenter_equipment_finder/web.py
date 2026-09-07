from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import EquipmentService


HTML_INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Data Center Equipment Finder</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 2rem; }
    input, select, button { margin: 0.25rem; padding: 0.35rem; }
    pre { background: #f4f4f4; padding: 1rem; overflow: auto; }
  </style>
</head>
<body>
  <h1>Data Center Equipment Finder</h1>
  <div>
    <label>Category <input id="category" placeholder="valve/cdu/chiller"></label>
    <label>Brand <input id="brand" placeholder="Parker/Vertiv"></label>
    <label>Size (mm) <input id="size" type="number" step="any"></label>
    <label>Cv <input id="cv" type="number" step="any"></label>
    <label>Kv <input id="kv" type="number" step="any"></label>
    <label>Capacity kW <input id="capkw" type="number" step="any"></label>
    <label>Top N <input id="topn" type="number" value="5"></label>
    <button onclick="findMatches()">Find</button>
  </div>
  <h3>Results</h3>
  <pre id="out">Run a search.</pre>
  <script>
    async function findMatches() {
      const params = new URLSearchParams({
        category: document.getElementById('category').value,
        brand: document.getElementById('brand').value,
        size_mm: document.getElementById('size').value,
        cv: document.getElementById('cv').value,
        kv: document.getElementById('kv').value,
        capacity_kw: document.getElementById('capkw').value,
        top_n: document.getElementById('topn').value
      });
      const res = await fetch('/api/find?' + params.toString());
      const data = await res.json();
      document.getElementById('out').textContent = JSON.stringify(data, null, 2);
    }
  </script>
</body>
</html>
"""


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _to_float(query: dict[str, list[str]], key: str) -> float | None:
    value = _first(query, key)
    if value is None:
        return None
    return float(value)


def _json_response(handler: BaseHTTPRequestHandler, payload: dict | list, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def create_handler(service: EquipmentService):
    class EquipmentHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)

            if parsed.path == "/":
                _text_response(self, HTML_INDEX, 200)
                return

            if parsed.path == "/api/health":
                _json_response(self, {"status": "ok"}, 200)
                return

            if parsed.path == "/api/schema":
                _json_response(self, service.schema(), 200)
                return

            if parsed.path == "/api/components":
                try:
                    payload = service.list_components(
                        category=_first(query, "category"),
                        brand=_first(query, "brand"),
                        limit=int(_first(query, "limit") or "100"),
                        offset=int(_first(query, "offset") or "0"),
                    )
                    _json_response(self, payload, 200)
                    return
                except ValueError as exc:
                    _json_response(self, {"error": str(exc)}, 400)
                    return

            if parsed.path == "/api/component":
                part = _first(query, "part_number")
                if not part:
                    _json_response(self, {"error": "part_number is required"}, 400)
                    return
                item = service.get_component(part)
                if item is None:
                    _json_response(self, {"error": "component not found"}, 404)
                    return
                _json_response(self, item, 200)
                return

            if parsed.path == "/api/find":
                try:
                    payload = service.find_components(
                        category=_first(query, "category"),
                        brand=_first(query, "brand"),
                        size_mm=_to_float(query, "size_mm"),
                        cv=_to_float(query, "cv"),
                        kv=_to_float(query, "kv"),
                        capacity_kw=_to_float(query, "capacity_kw"),
                        capacity_tons=_to_float(query, "capacity_tons"),
                        top_n=int(_first(query, "top_n") or "5"),
                    )
                    _json_response(self, payload, 200)
                    return
                except ValueError as exc:
                    _json_response(self, {"error": str(exc)}, 400)
                    return

            if parsed.path == "/api/explain":
                payload = service.explain(
                    property_name=_first(query, "property"),
                    category=_first(query, "category"),
                )
                _json_response(self, payload, 200)
                return

            _json_response(self, {"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/compat":
                _json_response(self, {"error": "not found"}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                report = service.compatibility(
                    payload.get("part_numbers", []),
                    max_connection_time=payload.get("max_connection_time"),
                    required_material=payload.get("required_material"),
                )
                _json_response(self, report, 200)
            except (json.JSONDecodeError, ValueError) as exc:
                _json_response(self, {"error": str(exc)}, 400)

        def log_message(self, format: str, *args):  # noqa: A003
            return

    return EquipmentHandler


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    service = EquipmentService.default()
    server = ThreadingHTTPServer((host, port), create_handler(service))
    print(f"DCEF web server running on http://{host}:{port}")
    print("Endpoints: /api/schema, /api/components, /api/find, /api/compat, /api/explain")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
