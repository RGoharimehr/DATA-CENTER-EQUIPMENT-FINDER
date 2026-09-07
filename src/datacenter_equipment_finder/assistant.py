from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .service import EquipmentService


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


def _extract_number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _contains_term(text: str, term: str) -> bool:
    variants = {
        term.lower(),
        term.lower().replace("_", " "),
        term.lower().replace("_", "-"),
    }
    return any(v in text for v in variants)


def local_parse_query(text: str, service: EquipmentService) -> dict[str, Any]:
    t = text.strip().lower()
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

    brand = None
    for b in schema["brands"]:
        if _contains_term(t, b):
            brand = b
            break

    size_mm = _extract_number(r"(\d+(?:\.\d+)?)\s*mm", t)
    cv = _extract_number(r"(?:^|\s)cv\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    kv = _extract_number(r"(?:^|\s)kv\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    capacity_kw = _extract_number(r"(\d+(?:\.\d+)?)\s*k\s*w", t)
    capacity_tons = _extract_number(r"(\d+(?:\.\d+)?)\s*(?:tr|ton|tons)", t)
    top_n_match = re.search(r"top\s*(\d+)", t)
    top_n = int(top_n_match.group(1)) if top_n_match else 5

    return {
        "category": category,
        "component_subtype": component_subtype,
        "brand": brand,
        "size_mm": size_mm,
        "cv": cv,
        "kv": kv,
        "capacity_kw": capacity_kw,
        "capacity_tons": capacity_tons,
        "top_n": max(1, min(top_n, 20)),
    }


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
        top_n=int(filters.get("top_n") or 5),
    )

    return {
        "mode_requested": normalized_mode,
        "mode_used": mode_used,
        "filters": filters,
        "matches": matches,
    }
