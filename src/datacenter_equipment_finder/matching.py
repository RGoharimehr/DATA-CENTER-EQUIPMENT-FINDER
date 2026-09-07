from __future__ import annotations

from typing import Iterable, Optional

from .models import EquipmentComponent, MatchResult
from .units import cv_to_kv, inch_to_mm, kv_to_cv, tons_to_kw

FLOW_COEFFICIENT_CATEGORIES = {"valve", "strainer"}


def _normalized_delta(a: Optional[float], b: Optional[float], fallback: float = 1.0) -> float:
    if a is None or b is None:
        return fallback
    scale = max(abs(b), 1e-9)
    return abs(a - b) / scale


def _coefficient_for_target(
    component: EquipmentComponent,
    target_cv: Optional[float],
    target_kv: Optional[float],
) -> Optional[float]:
    if component.flow_coefficient_value is None or component.flow_coefficient_type is None:
        return None

    coeff_type = component.flow_coefficient_type.lower()
    coeff = component.flow_coefficient_value

    if target_cv is not None:
        return coeff if coeff_type == "cv" else kv_to_cv(coeff)
    if target_kv is not None:
        return coeff if coeff_type == "kv" else cv_to_kv(coeff)
    return None


def _connection_size_mm(component: EquipmentComponent) -> Optional[float]:
    if component.nominal_size_mm is not None:
        return component.nominal_size_mm
    if component.nominal_size_inch is not None:
        return inch_to_mm(component.nominal_size_inch)
    return None


def find_closest_components(
    components: Iterable[EquipmentComponent],
    *,
    category: Optional[str] = None,
    component_subtype: Optional[str] = None,
    brand: Optional[str] = None,
    target_size_mm: Optional[float] = None,
    target_cv: Optional[float] = None,
    target_kv: Optional[float] = None,
    target_capacity_kw: Optional[float] = None,
    target_capacity_tons: Optional[float] = None,
    target_connection_size_mm: Optional[float] = None,
    target_connection_size_inch: Optional[float] = None,
    top_n: int = 5,
) -> list[MatchResult]:
    filtered = []
    for c in components:
        if category and c.category.lower() != category.lower():
            continue
        if component_subtype and (c.component_subtype or "").lower() != component_subtype.lower():
            continue
        if brand and c.brand.lower() != brand.lower():
            continue
        filtered.append(c)

    if target_capacity_tons is not None and target_capacity_kw is None:
        target_capacity_kw = tons_to_kw(target_capacity_tons)
    if target_connection_size_inch is not None and target_connection_size_mm is None:
        target_connection_size_mm = inch_to_mm(target_connection_size_inch)

    scored: list[MatchResult] = []
    for c in filtered:
        score = 0.0
        score += _normalized_delta(c.nominal_size_mm, target_size_mm, fallback=0.2)
        if target_connection_size_mm is not None:
            score += 1.2 * _normalized_delta(_connection_size_mm(c), target_connection_size_mm, fallback=0.35)

        target_coeff = target_cv if target_cv is not None else target_kv
        if target_coeff is not None and c.category.lower() in FLOW_COEFFICIENT_CATEGORIES:
            coeff_for_target = _coefficient_for_target(c, target_cv, target_kv)
            score += _normalized_delta(coeff_for_target, target_coeff, fallback=0.6)

        score += _normalized_delta(c.capacity_kw, target_capacity_kw, fallback=0.3)

        if c.estimated_price_usd is None:
            score += 0.05
        scored.append(MatchResult(component=c, score=score))

    return sorted(scored, key=lambda m: m.score)[: max(1, top_n)]
