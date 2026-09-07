from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from .catalog import FIELD_NAMES


def list_catalog_urls(csv_path: str | Path) -> list[str]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        urls = {(row.get("datasheet_url") or "").strip() for row in reader}
    return sorted(u for u in urls if u.startswith(("http://", "https://")))


def _safe_file_name(url: str) -> str:
    parsed = urlparse(url)
    base = Path(parsed.path).name or "catalog"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{base}"


def download_catalogs(csv_path: str | Path, output_dir: str | Path, *, limit: int | None = None, timeout: int = 20) -> dict[str, int]:
    urls = list_catalog_urls(csv_path)
    if limit is not None:
        urls = urls[: max(0, limit)]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    for url in urls:
        target = out / _safe_file_name(url)
        if target.exists():
            skipped += 1
            continue
        try:
            with urlopen(url, timeout=timeout) as resp:
                target.write_bytes(resp.read())
                downloaded += 1
        except (URLError, TimeoutError, ValueError):
            failed += 1

    return {
        "total": len(urls),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
    }


def build_sqlite_database(csv_path: str | Path, sqlite_path: str | Path) -> int:
    csv_file = Path(csv_path)
    db_file = Path(sqlite_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with csv_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    conn = sqlite3.connect(db_file)
    try:
        cols = ", ".join(f'"{c}" TEXT' for c in FIELD_NAMES)
        conn.execute("DROP TABLE IF EXISTS equipment_catalog")
        conn.execute(f"CREATE TABLE equipment_catalog ({cols})")
        placeholders = ", ".join("?" for _ in FIELD_NAMES)
        insert_sql = f"INSERT INTO equipment_catalog ({', '.join(FIELD_NAMES)}) VALUES ({placeholders})"
        for row in rows:
            conn.execute(insert_sql, [row.get(c, "") for c in FIELD_NAMES])
        conn.commit()
    finally:
        conn.close()

    return len(rows)
