from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from rapidfuzz import fuzz

from .service import EquipmentService
from .units import inch_to_mm


@dataclass(frozen=True)
class AssistantConfig:
    endpoint: str | None = None
    api_key: str | None = None
    local_endpoint: str | None = None
    local_model: str | None = None
    local_api_key: str | None = None
    timeout_seconds: int = 12


def default_assistant_config() -> AssistantConfig:
    return AssistantConfig(
        endpoint=os.environ.get("DCEF_AI_ENDPOINT"),
        api_key=os.environ.get("DCEF_AI_API_KEY"),
        local_endpoint=os.environ.get("DCEF_LOCAL_AI_ENDPOINT"),
        local_model=os.environ.get("DCEF_LOCAL_AI_MODEL"),
        local_api_key=os.environ.get("DCEF_LOCAL_AI_API_KEY"),
        timeout_seconds=int(os.environ.get("DCEF_AI_TIMEOUT_SECONDS", "12")),
    )


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _contains_term(text: str, term: str) -> bool:
    variants = _term_variants(term)
    return any(v in text for v in variants)


def _normalize_text(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ")


def _term_variants(term: str) -> set[str]:
    lowered = term.lower()
    return {
        lowered,
        lowered.replace("_", " "),
        lowered.replace("_", "-"),
        lowered.replace("-", " "),
    }


def _best_schema_term(text: str, candidates: list[str], *, minimum_score: float = 85.0) -> str | None:
    for candidate in candidates:
        if _contains_term(text, candidate):
            return candidate
    normalized_text = _normalize_text(text)
    best_candidate = None
    best_score = 0.0
    for candidate in candidates:
        score = max(fuzz.partial_ratio(variant, normalized_text) for variant in _term_variants(candidate))
        if score > best_score:
            best_candidate = candidate
            best_score = score
    if best_candidate is not None and best_score >= minimum_score:
        return best_candidate
    return None


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


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


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


def _local_model_prompt(text: str, service: EquipmentService) -> str:
    schema = service.schema()
    return (
        "Extract structured filters for the Data Center Equipment Finder.\n"
        "Return JSON only with keys: category, component_subtype, brand, size_mm, cv, kv, capacity_kw, "
        "capacity_tons, connection_size_mm, connection_size_inch, top_n.\n"
        "Use null for unknown values. Prefer catalog-supported categories and subtypes.\n"
        f"Categories: {schema['categories']}\n"
        f"Subtypes by category: {schema['subtypes_by_category']}\n"
        f"Brands: {schema['brands']}\n"
        f"Query: {text}"
    )


def local_model_parse_query(text: str, service: EquipmentService, config: AssistantConfig) -> dict[str, Any] | None:
    if not config.local_endpoint or not config.local_model:
        return None

    endpoint = config.local_endpoint.rstrip("/")
    prompt = _local_model_prompt(text, service)
    headers = {"Content-Type": "application/json"}
    if config.local_api_key:
        headers["Authorization"] = "Bearer " + config.local_api_key
        headers["X-API-Key"] = config.local_api_key

    if endpoint.endswith("/api/generate"):
        payload: dict[str, Any] = {
            "model": config.local_model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        }
    else:
        payload = {
            "model": config.local_model,
            "messages": [
                {"role": "system", "content": "Return only a JSON object with the requested filter keys."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    req = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=config.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    if isinstance(data.get("response"), str):
        return _extract_json_object(data["response"])
    if isinstance(data.get("message"), dict) and isinstance(data["message"].get("content"), str):
        return _extract_json_object(data["message"]["content"])
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return _extract_json_object(content)
    return data


def local_parse_query(text: str, service: EquipmentService) -> dict[str, Any]:
    t = text.strip().lower()
    tokens = _tokenize(t)
    schema = service.schema()

    category = _best_schema_term(t, schema["categories"], minimum_score=90.0)

    component_subtype = None
    if category:
        component_subtype = _best_schema_term(t, schema["subtypes_by_category"].get(category, []), minimum_score=88.0)
    if component_subtype is None:
        for subtypes in schema["subtypes_by_category"].values():
            component_subtype = _best_schema_term(t, subtypes, minimum_score=88.0)
            if component_subtype:
                break
    if category is None:
        category = _infer_category_from_subtype(service, component_subtype)

    brand = _best_schema_term(t, schema["brands"], minimum_score=88.0)

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
    local_rule_filters = local_parse_query(text, service)
    local_model_filters = None
    remote_filters = None

    normalized_mode = (mode or "hybrid").lower()
    if normalized_mode in {"local", "hybrid"}:
        local_model_filters = local_model_parse_query(text, service, cfg)
    if normalized_mode in {"remote", "hybrid"}:
        remote_filters = remote_parse_query(text, cfg)
    local_filters = _merge_filters(local_rule_filters, local_model_filters)

    if normalized_mode == "local":
        filters = local_filters
        mode_used = "local_model+rules" if local_model_filters else "local_rules_only"
    elif normalized_mode == "remote":
        filters = remote_filters or local_filters
        mode_used = "remote" if remote_filters else ("local_model_fallback" if local_model_filters else "local_rules_fallback")
    else:
        filters = _merge_filters(local_filters, remote_filters)
        if remote_filters and local_model_filters:
            mode_used = "hybrid_remote+local_model+rules"
        elif remote_filters:
            mode_used = "hybrid_remote+local_rules"
        elif local_model_filters:
            mode_used = "hybrid_local_model+rules"
        else:
            mode_used = "hybrid_local_only"
    filters = dict(filters)
    existing_checks = list(filters.get("checks", []))
    filters["checks"] = existing_checks + [
        check for check in _validate_local_filters(filters) if check not in existing_checks
    ]

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
