from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from .assistant import run_assistant_query
from .api_models import (
    AssistantRequest,
    CompatibilityRequest,
    ComponentsQuery,
    FindQuery,
    first_query_value,
    query_payload,
    validation_message,
)
from .service import EquipmentService

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"
LEGACY_PREFIX = "/api"


HTML_INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Data Center Equipment Finder</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 2rem; max-width: 1080px; }
    .row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
    input, select, button { padding: 0.4rem; }
    pre { background: #f4f4f4; padding: 1rem; overflow: auto; border-radius: 6px; }
  </style>
</head>
<body>
  <h1>Data Center Equipment Finder</h1>
  <p>API version: <code>v1</code></p>
  <div class="row">
    <label>API Key <input id="api-key" type="password" placeholder="Optional X-API-Key"></label>
  </div>
  <div class="row">
    <label>Category
      <select id="category" onchange="onCategoryChange()">
        <option value="">(any)</option>
        <option value="valve">valve</option>
        <option value="strainer">strainer</option>
        <option value="filter_dryer">filter_dryer</option>
        <option value="cdu">cdu</option>
        <option value="chiller">chiller</option>
      </select>
    </label>
    <label>Subtype <input id="subtype" placeholder="isolation_valve/check_valve"></label>
    <label>Brand <input id="brand" placeholder="Parker/Vertiv"></label>
    <label>Size (mm) <input id="size" type="number" step="any"></label>
    <label>Connection (mm) <input id="conn-size-mm" type="number" step="any"></label>
    <label>Connection (inch) <input id="conn-size-inch" type="number" step="any"></label>
    <label id="cv-wrap">Cv <input id="cv" type="number" step="any"></label>
    <label id="kv-wrap">Kv <input id="kv" type="number" step="any"></label>
    <label id="cap-wrap">Capacity kW <input id="capkw" type="number" step="any"></label>
    <label>Top N <input id="topn" type="number" value="5"></label>
    <button onclick="findMatches()">Find</button>
  </div>
  <h3>Results</h3>
  <pre id="out">Run a search.</pre>
  <h3>Hybrid AI assistant</h3>
  <div class="row">
    <label>Mode
      <select id="ai-mode">
        <option value="hybrid">hybrid</option>
        <option value="local">local</option>
        <option value="remote">remote</option>
      </select>
    </label>
    <input id="ai-query" style="min-width: 420px;" placeholder="e.g. find check valve 20 mm kv 6 for ammonia from danfoss" />
    <button onclick="runAssistant()">Ask AI</button>
  </div>
  <pre id="ai-out">Run an AI request.</pre>
  <script>
    function apiHeaders(extra = {}) {
      const apiKey = document.getElementById('api-key').value.trim();
      if (apiKey) {
        localStorage.setItem('dcef-api-key', apiKey);
        return {...extra, 'X-API-Key': apiKey};
      }
      localStorage.removeItem('dcef-api-key');
      return extra;
    }
    function onCategoryChange() {
      const cat = document.getElementById('category').value;
      const showFlow = (cat === 'valve' || cat === 'strainer' || cat === '');
      const showCap = (cat === 'filter_dryer' || cat === 'cdu' || cat === 'chiller' || cat === '');
      document.getElementById('cv-wrap').style.display = showFlow ? '' : 'none';
      document.getElementById('kv-wrap').style.display = showFlow ? '' : 'none';
      document.getElementById('cap-wrap').style.display = showCap ? '' : 'none';
      if (!showFlow) {
        document.getElementById('cv').value = '';
        document.getElementById('kv').value = '';
      }
    }
    async function findMatches() {
      const params = new URLSearchParams({
        category: document.getElementById('category').value,
        component_subtype: document.getElementById('subtype').value,
        brand: document.getElementById('brand').value,
        size_mm: document.getElementById('size').value,
        connection_size_mm: document.getElementById('conn-size-mm').value,
        connection_size_inch: document.getElementById('conn-size-inch').value,
        cv: document.getElementById('cv').value,
        kv: document.getElementById('kv').value,
        capacity_kw: document.getElementById('capkw').value,
        top_n: document.getElementById('topn').value
      });
      const res = await fetch('/api/v1/find?' + params.toString(), {
        headers: apiHeaders()
      });
      const data = await res.json();
      document.getElementById('out').textContent = JSON.stringify(data, null, 2);
    }
    async function runAssistant() {
      const res = await fetch('/api/v1/assistant', {
        method: 'POST',
        headers: apiHeaders({'Content-Type': 'application/json'}),
        body: JSON.stringify({
          query: document.getElementById('ai-query').value,
          mode: document.getElementById('ai-mode').value
        })
      });
      const data = await res.json();
      document.getElementById('ai-out').textContent = JSON.stringify(data, null, 2);
    }
    document.getElementById('api-key').value = localStorage.getItem('dcef-api-key') || '';
    onCategoryChange();
  </script>
</body>
</html>
"""


@dataclass(frozen=True)
class ServerConfig:
    api_key: str | None = None
    rate_limit_per_minute: int = 120


def _default_config() -> ServerConfig:
    configured_key = os.environ.get("DCEF_API_KEY")
    configured_limit = int(os.environ.get("DCEF_RATE_LIMIT_PER_MIN", "120"))
    return ServerConfig(api_key=configured_key, rate_limit_per_minute=max(1, configured_limit))


def _envelope_ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"ok": True, "data": data, "error": None, "meta": {"api_version": API_VERSION}}
    if meta:
        payload["meta"].update(meta)
    return payload


def _envelope_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
        "meta": {"api_version": API_VERSION},
    }

def _normalized_api_path(path: str) -> str:
    if path.startswith(API_PREFIX):
        return path
    if path == LEGACY_PREFIX:
        return API_PREFIX
    if path.startswith(LEGACY_PREFIX + "/"):
        return API_PREFIX + path[len(LEGACY_PREFIX) :]
    return path


def _json_response(handler: BaseHTTPRequestHandler, payload: dict | list, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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

def create_handler(service: EquipmentService, config: ServerConfig | None = None):
    cfg = config or _default_config()
    request_buckets: dict[str, deque[float]] = defaultdict(deque)

    class EquipmentHandler(BaseHTTPRequestHandler):
        def _client_id(self) -> str:
            forwarded = self.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return self.client_address[0]

        def _check_rate_limit(self) -> bool:
            now = time.time()
            window_start = now - 60
            bucket = request_buckets[self._client_id()]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= cfg.rate_limit_per_minute:
                _json_response(
                    self,
                    _envelope_error("rate_limited", "Rate limit exceeded", {"limit_per_minute": cfg.rate_limit_per_minute}),
                    429,
                )
                return False
            bucket.append(now)
            return True

        def _check_auth(self, path: str) -> bool:
            if not path.startswith(API_PREFIX):
                return True
            if path.endswith("/health"):
                return True
            if not cfg.api_key:
                return True
            supplied = self.headers.get("X-API-Key")
            if supplied == cfg.api_key:
                return True
            _json_response(self, _envelope_error("unauthorized", "Missing or invalid API key"), 401)
            return False

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = _normalized_api_path(parsed.path)
            query = parse_qs(parsed.query)

            if path == "/":
                _text_response(self, HTML_INDEX, 200)
                return

            if not self._check_auth(path):
                return
            if path.startswith(API_PREFIX) and not self._check_rate_limit():
                return

            if path == f"{API_PREFIX}/health":
                _json_response(self, _envelope_ok({"status": "ok"}), 200)
                return

            if path == f"{API_PREFIX}/schema":
                _json_response(self, _envelope_ok(service.schema()), 200)
                return

            if path == f"{API_PREFIX}/components":
                try:
                    filters = ComponentsQuery.model_validate(
                        query_payload(query, "category", "component_subtype", "brand", "limit", "offset")
                    )
                    payload = service.list_components(
                        category=filters.category,
                        component_subtype=filters.component_subtype,
                        brand=filters.brand,
                        limit=filters.limit,
                        offset=filters.offset,
                    )
                    _json_response(self, _envelope_ok(payload, {"count": len(payload)}), 200)
                    return
                except ValidationError as exc:
                    _json_response(self, _envelope_error("invalid_request", validation_message(exc)), 400)
                    return

            if path == f"{API_PREFIX}/component":
                part = first_query_value(query, "part_number")
                if not part:
                    _json_response(self, _envelope_error("invalid_request", "part_number is required"), 400)
                    return
                item = service.get_component(part)
                if item is None:
                    _json_response(self, _envelope_error("not_found", "component not found"), 404)
                    return
                _json_response(self, _envelope_ok(item), 200)
                return

            if path == f"{API_PREFIX}/find":
                try:
                    filters = FindQuery.model_validate(
                        query_payload(
                            query,
                            "category",
                            "component_subtype",
                            "brand",
                            "size_mm",
                            "connection_size_mm",
                            "connection_size_inch",
                            "cv",
                            "kv",
                            "capacity_kw",
                            "capacity_tons",
                            "top_n",
                        )
                    )
                    payload = service.find_components(
                        category=filters.category,
                        component_subtype=filters.component_subtype,
                        brand=filters.brand,
                        size_mm=filters.size_mm,
                        connection_size_mm=filters.connection_size_mm,
                        connection_size_inch=filters.connection_size_inch,
                        cv=filters.cv,
                        kv=filters.kv,
                        capacity_kw=filters.capacity_kw,
                        capacity_tons=filters.capacity_tons,
                        top_n=filters.top_n,
                    )
                    _json_response(self, _envelope_ok(payload, {"count": len(payload)}), 200)
                    return
                except ValidationError as exc:
                    _json_response(self, _envelope_error("invalid_request", validation_message(exc)), 400)
                    return

            if path == f"{API_PREFIX}/explain":
                payload = service.explain(
                    property_name=first_query_value(query, "property"),
                    category=first_query_value(query, "category"),
                )
                _json_response(self, _envelope_ok(payload), 200)
                return

            if path == f"{API_PREFIX}/openapi.json":
                spec = {
                    "openapi": "3.0.0",
                    "info": {"title": "DCEF API", "version": API_VERSION},
                    "paths": {
                        f"{API_PREFIX}/health": {"get": {}},
                        f"{API_PREFIX}/schema": {"get": {}},
                        f"{API_PREFIX}/components": {"get": {}},
                        f"{API_PREFIX}/component": {"get": {}},
                        f"{API_PREFIX}/find": {"get": {}},
                        f"{API_PREFIX}/compat": {"post": {}},
                        f"{API_PREFIX}/assistant": {"post": {}},
                        f"{API_PREFIX}/explain": {"get": {}},
                    },
                }
                _json_response(self, _envelope_ok(spec), 200)
                return

            _json_response(self, _envelope_error("not_found", "not found"), 404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = _normalized_api_path(parsed.path)

            if not self._check_auth(path):
                return
            if path.startswith(API_PREFIX) and not self._check_rate_limit():
                return

            if path == f"{API_PREFIX}/assistant":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = AssistantRequest.model_validate(json.loads(self.rfile.read(length) or b"{}"))
                    result = run_assistant_query(payload.query, service, mode=payload.mode)
                    _json_response(self, _envelope_ok(result), 200)
                    return
                except json.JSONDecodeError as exc:
                    _json_response(self, _envelope_error("invalid_request", str(exc)), 400)
                    return
                except ValidationError as exc:
                    _json_response(self, _envelope_error("invalid_request", validation_message(exc)), 400)
                    return

            if path != f"{API_PREFIX}/compat":
                _json_response(self, _envelope_error("not_found", "not found"), 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = CompatibilityRequest.model_validate(json.loads(self.rfile.read(length) or b"{}"))
                report = service.compatibility(
                    payload.part_numbers,
                    max_connection_time=payload.max_connection_time,
                    required_material=payload.required_material,
                    required_connection_standard=payload.required_connection_standard,
                    required_coolant=payload.required_coolant,
                )
                _json_response(self, _envelope_ok(report), 200)
            except json.JSONDecodeError as exc:
                _json_response(self, _envelope_error("invalid_request", str(exc)), 400)
            except ValidationError as exc:
                _json_response(self, _envelope_error("invalid_request", validation_message(exc)), 400)

        def log_message(self, format: str, *args):  # noqa: A003
            return

    return EquipmentHandler


def run_server(host: str = "127.0.0.1", port: int = 8000, *, api_key: str | None = None, rate_limit_per_minute: int | None = None) -> None:
    base_cfg = _default_config()
    config = ServerConfig(
        api_key=api_key if api_key is not None else base_cfg.api_key,
        rate_limit_per_minute=rate_limit_per_minute if rate_limit_per_minute is not None else base_cfg.rate_limit_per_minute,
    )
    server = ThreadingHTTPServer((host, port), create_handler(EquipmentService.default(), config=config))
    print(f"DCEF web server running on http://{host}:{port}")
    print(f"API: {API_PREFIX} | OpenAPI: {API_PREFIX}/openapi.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
