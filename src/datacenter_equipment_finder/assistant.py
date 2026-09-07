from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .service import EquipmentService
from .units import inch_to_mm


@dataclass(frozen=True)
class AssistantConfig:
    endpoint: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 12


def default_assistant_config() -> AssistantConfig:
    return AssistantConfig(
        endpoint=os.environ.get("DCEF_AI_ENDPOINT"),
        api_key=os.environ.get("DCEF_AI_API_KEY"),
        timeout_seconds=int(os.environ.get("DCEF_AI_TIMEOUT_SECONDS", "12")),
    )


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _contains_term(text: str, term: str) -> bool:
    variants = {
        term.lower(),
        term.lower().replace("_", " "),
        term.lower().replace("_", "-"),
    }
    return any(v in text for v in variants)


def _tokenize(text: str) -> list[str]:
    cleaned = []
    for ch in text.lower():
        if ch.isalnum() or ch in {"_", ".", "-"}:
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return [token for token in "".join(cleaned).split() if token]


def _extract_before_unit(tokens: list[str], units: set[str]) -> float | None:
    for i, tok in enumerate(tokens):
        if tok in units and i > 0:
            val = _as_float(tokens[i - 1])
            if val is not None:
                return val
    return None


def _extract_prefixed_value(tokens: list[str], key: str) -> float | None:
    for i, tok in enumerate(tokens):
        if tok == key and i + 1 < len(tokens):
            val = _as_float(tokens[i + 1])
            if val is not None:
                return val
        if tok.startswith(f"{key}=") or tok.startswith(f"{key}:"):
            _, _, rhs = tok.partition("=" if "=" in tok else ":")
            val = _as_float(rhs)
            if val is not None:
                return val
    return None


def _extract_top_n(tokens: list[str], default: int = 5) -> int:
    for i, tok in enumerate(tokens):
        if tok == "top" and i + 1 < len(tokens):
            val = _as_float(tokens[i + 1])
            if val is not None:
                return int(val)
    return default


def _extract_connection_size(text: str) -> tuple[float | None, float | None]:
    patterns = (
        r"(?:pipe|piping|connection|port|line|diameter|dn)\s*(?:size)?\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|in|inch|inches|\")",
        r"(\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|in|inch|inches|\")\s*(?:pipe|piping|connection|port|line|diameter|id|od|dn)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = _as_float(match.group(1))
        if value is None:
            continue
        unit = match.group(2)
        if unit.startswith("mm"):
            return value, None
        return inch_to_mm(value), value
    return None, None


def _infer_category_from_subtype(service: EquipmentService, component_subtype: str | None) -> str | None:
    if not component_subtype:
        return None
    for category, subtypes in service.schema()["subtypes_by_category"].items():
        if component_subtype in subtypes:
            return category
    return None


def _validate_local_filters(filters: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    if filters.get("cv") is not None and filters.get("kv") is not None:
        filters["kv"] = None
        checks.append("Both cv and kv were provided; the local model kept cv and dropped kv.")
    if filters.get("category") in {"cdu", "chiller", "filter_dryer"} and (
        filters.get("cv") is not None or filters.get("kv") is not None
    ):
        filters["cv"] = None
        filters["kv"] = None
        checks.append("Cv/Kv inputs were ignored because they do not apply to CDU, chiller, or filter_dryer searches.")
    if filters.get("connection_size_inch") is not None and filters.get("connection_size_mm") is None:
        filters["connection_size_mm"] = inch_to_mm(filters["connection_size_inch"])
        checks.append("Converted connection size from inches to millimeters for local matching.")
    if filters.get("size_mm") is None and filters.get("connection_size_mm") is not None:
        filters["size_mm"] = filters["connection_size_mm"]
        checks.append("Used the connection size as the nominal size target because no explicit size_mm was provided.")
    return checks


def local_parse_query(text: str, service: EquipmentService) -> dict[str, Any]:
    t = text.strip().lower()
    tokens = _tokenize(t)
    schema = service.schema()

    category = None
    for c in schema["categories"]:
        if _contains_term(t, c):
            category = c
            break

    component_subtype = None
    if category:
        for s in schema["subtypes_by_category"].get(category, []):
            if _contains_term(t, s):
                component_subtype = s
                break
    if component_subtype is None:
        for subtypes in schema["subtypes_by_category"].values():
            for s in subtypes:
                if _contains_term(t, s):
                    component_subtype = s
                    break
            if component_subtype is not None:
                break
    if category is None:
        category = _infer_category_from_subtype(service, component_subtype)

    brand = None
    for b in schema["brands"]:
        if _contains_term(t, b):
            brand = b
            break

    size_mm = _extract_before_unit(tokens, {"mm"})
    cv = _extract_prefixed_value(tokens, "cv")
    kv = _extract_prefixed_value(tokens, "kv")
    capacity_kw = _extract_before_unit(tokens, {"kw", "kilowatt", "kilowatts"})
    capacity_tons = _extract_before_unit(tokens, {"tr", "ton", "tons"})
    connection_size_mm, connection_size_inch = _extract_connection_size(t)
    top_n = _extract_top_n(tokens, default=5)

    filters = {
        "category": category,
        "component_subtype": component_subtype,
        "brand": brand,
        "size_mm": size_mm,
        "cv": cv,
        "kv": kv,
        "capacity_kw": capacity_kw,
        "capacity_tons": capacity_tons,
        "connection_size_mm": connection_size_mm,
        "connection_size_inch": connection_size_inch,
        "top_n": max(1, min(top_n, 20)),
    }
    filters["checks"] = _validate_local_filters(filters)
    return filters


def remote_parse_query(text: str, config: AssistantConfig) -> dict[str, Any] | None:
    if not config.endpoint:
        return None

    payload = json.dumps({"query": text}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    req = Request(config.endpoint, data=payload, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=config.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def _merge_filters(local: dict[str, Any], remote: dict[str, Any] | None) -> dict[str, Any]:
    if not remote:
        return local
    merged = dict(local)
    for k in merged:
        if k in remote and remote[k] not in (None, ""):
            merged[k] = remote[k]
    return merged


def run_assistant_query(
    text: str,
    service: EquipmentService,
    *,
    mode: str = "hybrid",
    config: AssistantConfig | None = None,
) -> dict[str, Any]:
    cfg = config or default_assistant_config()
    local_filters = local_parse_query(text, service)
    remote_filters = None

    normalized_mode = (mode or "hybrid").lower()
    if normalized_mode in {"remote", "hybrid"}:
        remote_filters = remote_parse_query(text, cfg)

    if normalized_mode == "local":
        filters = local_filters
        mode_used = "local"
    elif normalized_mode == "remote":
        filters = remote_filters or local_filters
        mode_used = "remote" if remote_filters else "local_fallback"
    else:
        filters = _merge_filters(local_filters, remote_filters)
        mode_used = "hybrid_remote+local" if remote_filters else "hybrid_local_only"

    matches = service.find_components(
        category=filters.get("category"),
        component_subtype=filters.get("component_subtype"),
        brand=filters.get("brand"),
        size_mm=filters.get("size_mm"),
        cv=filters.get("cv"),
        kv=filters.get("kv"),
        capacity_kw=filters.get("capacity_kw"),
        capacity_tons=filters.get("capacity_tons"),
        connection_size_mm=filters.get("connection_size_mm"),
        connection_size_inch=filters.get("connection_size_inch"),
        top_n=int(filters.get("top_n") or 5),
    )

    return {
        "mode_requested": normalized_mode,
        "mode_used": mode_used,
        "filters": filters,
        "checks": filters.get("checks", []),
        "matches": matches,
    }
