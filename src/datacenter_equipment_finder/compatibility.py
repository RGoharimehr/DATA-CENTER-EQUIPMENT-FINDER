from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import EquipmentComponent


_CONNECTION_EQUIVALENTS = {
    "NPT": {"NPT", "FPT"},
    "FPT": {"NPT", "FPT"},
    "ODF": {"ODF", "ODS"},
    "ODS": {"ODF", "ODS"},
    "SW": {"SW", "SOCKET WELD"},
    "SOCKET WELD": {"SW", "SOCKET WELD"},
}


@dataclass(frozen=True)
class CompatibilityReport:
    is_compatible: bool
    reasons: list[str]


def _normalize_connection(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().upper()


def _connections_compatible(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    an = _normalize_connection(a)
    bn = _normalize_connection(b)
    if an == bn:
        return True
    return bn in _CONNECTION_EQUIVALENTS.get(an, {an})


def check_compatibility(
    components: Iterable[EquipmentComponent],
    *,
    max_install_connection_time_min: float | None = None,
    required_material: str | None = None,
    required_connection_standard: str | None = None,
    required_coolant: str | None = None,
) -> CompatibilityReport:
    parts = list(components)
    reasons: list[str] = []
    hydraulic_categories = {"valve", "strainer", "filter_dryer"}
    thermal_categories = {"cdu", "chiller"}

    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = parts[i], parts[j]
            if a.category.lower() in hydraulic_categories and b.category.lower() in hydraulic_categories and not _connections_compatible(a.connection_type, b.connection_type):
                reasons.append(
                    f"Connection mismatch: {a.part_number} ({a.connection_type}) vs {b.part_number} ({b.connection_type})"
                )
            if a.category.lower() in thermal_categories and b.category.lower() in thermal_categories:
                a_std = (a.connection_standard or "").strip().lower()
                b_std = (b.connection_standard or "").strip().lower()
                if a_std and b_std and a_std != b_std:
                    reasons.append(
                        f"Connection standard mismatch: {a.part_number} ({a.connection_standard}) vs {b.part_number} ({b.connection_standard})"
                    )

    if required_material:
        wanted = required_material.strip().lower()
        for p in parts:
            if p.material and p.material.strip().lower() != wanted:
                reasons.append(f"Material mismatch: {p.part_number} material={p.material}, required={required_material}")

    if required_connection_standard:
        expected = required_connection_standard.strip().lower()
        for p in parts:
            if p.connection_standard and p.connection_standard.strip().lower() != expected:
                reasons.append(
                    f"Connection standard mismatch: {p.part_number} standard={p.connection_standard}, required={required_connection_standard}"
                )

    if required_coolant:
        expected = required_coolant.strip().lower()
        for p in parts:
            if p.coolant_compatibility and expected not in p.coolant_compatibility.strip().lower():
                reasons.append(
                    f"Coolant mismatch: {p.part_number} coolant={p.coolant_compatibility}, required contains={required_coolant}"
                )

    if max_install_connection_time_min is not None:
        for p in parts:
            if (
                p.category.lower() in hydraulic_categories
                and p.install_connection_time_min is not None
                and p.install_connection_time_min > max_install_connection_time_min
            ):
                reasons.append(
                    f"Connection time too high: {p.part_number} requires {p.install_connection_time_min} min"
                )

    pressure_values = [p.pressure_rating_bar for p in parts if p.pressure_rating_bar is not None]
    if pressure_values and max(pressure_values) / max(min(pressure_values), 1e-9) > 2.0:
        reasons.append("Large pressure-class spread across selected components; verify rating alignment.")

    return CompatibilityReport(is_compatible=not reasons, reasons=reasons)
