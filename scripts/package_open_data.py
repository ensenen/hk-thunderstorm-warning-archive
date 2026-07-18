#!/usr/bin/env python3
"""Create portable CSV and Frictionless Data exports from SQLite."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/thunderstorm-warnings.sqlite3"
OUT = ROOT / "dist/open-data"
HKT = ZoneInfo("Asia/Hong_Kong")


def export_query(connection, filename: str, query: str) -> dict:
    path = OUT / filename
    cursor = connection.execute(query)
    columns = [item[0] for item in cursor.description]
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in cursor:
            writer.writerow(row)
            count += 1
    return {
        "path": filename,
        "format": "csv",
        "rows": count,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema": {"fields": [{"name": name, "type": "string"} for name in columns]},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB)
    resources = [
        export_query(connection, "warning-series.csv", "SELECT * FROM warning_series ORDER BY started_at"),
        export_query(connection, "bulletin-events.csv", "SELECT * FROM bulletin_events ORDER BY bulletin_at, id"),
        export_query(connection, "source-references.csv", """
            SELECT warning_series_id, bulletin_id, event_type, event_at, valid_until, source_url
            FROM bulletin_events ORDER BY bulletin_at, id
        """),
    ]
    connection.close()
    package = {
        "profile": "data-package",
        "name": "hong-kong-thunderstorm-warnings",
        "title": "Hong Kong Thunderstorm Warning Archive",
        "created": datetime.now(HKT).isoformat(),
        "licenses": [{"name": "HKSARG-Open-Data-Terms", "path": "https://data.gov.hk/en/terms-and-conditions"}],
        "sources": [
            {"title": "Hong Kong Observatory Warnings and Signals Database", "path": "https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb5.shtml"},
            {"title": "HKSAR Government press releases", "path": "https://www.info.gov.hk/gia/general/"},
        ],
        "resources": resources,
    }
    (OUT / "datapackage.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Hong Kong Thunderstorm Warning Open Data\n\n"
        "Source: Hong Kong Observatory and HKSAR Government press releases. "
        "See `LICENSE-DATA.md` in the project repository. This is a historical "
        "research dataset, not an official real-time warning service.\n",
        encoding="utf-8",
    )
    analysis = ROOT / "data/processed/analysis.json"
    if analysis.exists():
        shutil.copy2(analysis, OUT / "analysis.json")
    print(f"Packaged {sum(r['rows'] for r in resources)} rows in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
