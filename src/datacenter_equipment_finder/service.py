from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .catalog import EquipmentCatalog, FIELD_NAMES
from .compatibility import check_compatibility
from .explanations import explain_category, explain_property
from .matching import find_closest_components


class EquipmentService:
    def __init__(self, catalog: EquipmentCatalog):
        self.catalog = catalog

    @classmethod
    def default(cls) -> "EquipmentService":
        return cls(EquipmentCatalog.from_csv())

    def schema(self) -> dict[str, Any]:
        categories = sorted({c.category for c in self.catalog.components})
        brands = sorted({c.brand for c in self.catalog.components})
        return {
            "fields": FIELD_NAMES,
            "categories": categories,
            "brands": brands,
        }

    def list_components(
        self,
        *,
        category: str | None = None,
        brand: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = self.catalog.components
        if category:
            rows = [c for c in rows if c.category.lower() == category.lower()]
        if brand:
            rows = [c for c in rows if c.brand.lower() == brand.lower()]
        sliced = rows[max(0, offset) : max(0, offset) + max(1, limit)]
        return [asdict(c) for c in sliced]

    def get_component(self, part_number: str) -> dict[str, Any] | None:
        for c in self.catalog.components:
            if c.part_number.lower() == part_number.lower():
                return asdict(c)
        return None

    def find_components(
        self,
        *,
        category: str | None = None,
        brand: str | None = None,
        size_mm: float | None = None,
        cv: float | None = None,
        kv: float | None = None,
        capacity_kw: float | None = None,
        capacity_tons: float | None = None,
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        matches = find_closest_components(
            self.catalog.components,
            category=category,
            brand=brand,
            target_size_mm=size_mm,
            target_cv=cv,
            target_kv=kv,
            target_capacity_kw=capacity_kw,
            target_capacity_tons=capacity_tons,
            top_n=top_n,
        )
        return [{"score": m.score, "component": asdict(m.component)} for m in matches]

    def compatibility(
        self,
        part_numbers: list[str],
        *,
        max_connection_time: float | None = None,
        required_material: str | None = None,
    ) -> dict[str, Any]:
        selected = [
            c for c in self.catalog.components if c.part_number.lower() in {p.lower() for p in part_numbers}
        ]
        report = check_compatibility(
            selected,
            max_install_connection_time_min=max_connection_time,
            required_material=required_material,
        )
        return {
            "is_compatible": report.is_compatible,
            "reasons": report.reasons,
            "selected_count": len(selected),
            "requested_count": len(part_numbers),
        }

    def explain(self, *, property_name: str | None = None, category: str | None = None) -> dict[str, str]:
        if property_name:
            return {"type": "property", "name": property_name, "explanation": explain_property(property_name)}
        if category:
            return {"type": "category", "name": category, "explanation": explain_category(category)}
        return {"type": "error", "name": "", "explanation": "Provide property_name or category."}
