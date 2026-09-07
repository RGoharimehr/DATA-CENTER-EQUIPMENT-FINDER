from __future__ import annotations

import argparse

from .catalog import EquipmentCatalog
from .compatibility import check_compatibility
from .dataset_pipeline import build_catalog_from_vendor_sources
from .explanations import explain_category, explain_property
from .matching import find_closest_components
from .web import run_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dcef", description="Data Center Equipment Finder")
    sub = parser.add_subparsers(dest="command", required=True)

    f = sub.add_parser("find", help="Find closest components")
    f.add_argument("--category", required=False)
    f.add_argument("--brand", required=False)
    f.add_argument("--size-mm", type=float, required=False)
    f.add_argument("--cv", type=float, required=False)
    f.add_argument("--kv", type=float, required=False)
    f.add_argument("--capacity-kw", type=float, required=False)
    f.add_argument("--capacity-tons", type=float, required=False)
    f.add_argument("--top-n", type=int, default=5)

    c = sub.add_parser("compat", help="Check compatibility for part numbers")
    c.add_argument("part_numbers", nargs="+", help="Part numbers to evaluate")
    c.add_argument("--max-connection-time", type=float)
    c.add_argument("--required-material")

    e = sub.add_parser("explain", help="Explain a property or category")
    e.add_argument("--property", dest="property_name")
    e.add_argument("--category")

    s = sub.add_parser("serve", help="Run web interface and JSON API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--api-key", default=None, help="Optional API key required on X-API-Key header")
    s.add_argument("--rate-limit-per-minute", type=int, default=None, help="Per-client requests/minute for API")

    b = sub.add_parser("build-catalog", help="Build packaged catalog from vendor CSV sources")
    b.add_argument("--source-dir", default="src/datacenter_equipment_finder/data/vendors")
    b.add_argument("--output-file", default="src/datacenter_equipment_finder/data/equipment_catalog.csv")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    catalog = EquipmentCatalog.from_csv()

    if args.command == "find":
        matches = find_closest_components(
            catalog.components,
            category=args.category,
            brand=args.brand,
            target_size_mm=args.size_mm,
            target_cv=args.cv,
            target_kv=args.kv,
            target_capacity_kw=args.capacity_kw,
            target_capacity_tons=args.capacity_tons,
            top_n=args.top_n,
        )
        for i, m in enumerate(matches, start=1):
            c = m.component
            print(
                f"{i}. {c.part_number} | {c.brand} {c.category} | size_mm={c.nominal_size_mm} "
                f"| coeff={c.flow_coefficient_type}:{c.flow_coefficient_value} | cap_kw={c.capacity_kw} "
                f"| conn={c.connection_type} | material={c.material} | score={m.score:.4f}"
            )
        return 0

    if args.command == "compat":
        selected = [
            c for c in catalog.components if c.part_number.lower() in {p.lower() for p in args.part_numbers}
        ]
        report = check_compatibility(
            selected,
            max_install_connection_time_min=args.max_connection_time,
            required_material=args.required_material,
        )
        print(f"compatible={report.is_compatible}")
        for reason in report.reasons:
            print(f"- {reason}")
        return 0

    if args.command == "explain":
        if args.property_name:
            print(explain_property(args.property_name))
        elif args.category:
            print(explain_category(args.category))
        else:
            parser.error("Provide --property or --category")
        return 0

    if args.command == "serve":
        run_server(
            host=args.host,
            port=args.port,
            api_key=args.api_key,
            rate_limit_per_minute=args.rate_limit_per_minute,
        )
        return 0

    if args.command == "build-catalog":
        errors = build_catalog_from_vendor_sources(args.source_dir, args.output_file)
        if errors:
            print("Catalog validation failed:")
            for err in errors:
                print(f"- {err}")
            return 2
        print(f"Catalog built: {args.output_file}")
        return 0

    return 1
