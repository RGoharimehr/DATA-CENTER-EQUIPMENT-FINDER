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
) -> CompatibilityReport:
    parts = list(components)
    reasons: list[str] = []

    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = parts[i], parts[j]
            if not _connections_compatible(a.connection_type, b.connection_type):
                reasons.append(
                    f"Connection mismatch: {a.part_number} ({a.connection_type}) vs {b.part_number} ({b.connection_type})"
                )

    if required_material:
        wanted = required_material.strip().lower()
        for p in parts:
            if p.material and p.material.strip().lower() != wanted:
                reasons.append(f"Material mismatch: {p.part_number} material={p.material}, required={required_material}")

    if max_install_connection_time_min is not None:
        for p in parts:
            if p.install_connection_time_min is not None and p.install_connection_time_min > max_install_connection_time_min:
                reasons.append(
                    f"Connection time too high: {p.part_number} requires {p.install_connection_time_min} min"
                )

    pressure_values = [p.pressure_rating_bar for p in parts if p.pressure_rating_bar is not None]
    if pressure_values and max(pressure_values) / max(min(pressure_values), 1e-9) > 2.0:
        reasons.append("Large pressure-class spread across selected components; verify rating alignment.")

    return CompatibilityReport(is_compatible=not reasons, reasons=reasons)
