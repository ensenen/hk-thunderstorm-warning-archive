#!/usr/bin/env python3
"""Export the complete SQLite data as portable JSONL files."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/thunderstorm-warnings.sqlite3"
OUTPUT = ROOT / "data/processed/warning-series.jsonl"


def main() -> int:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with OUTPUT.open("w", encoding="utf-8") as output:
        for series_row in connection.execute("SELECT * FROM warning_series ORDER BY started_at"):
            series = dict(series_row)
            events = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM bulletin_events WHERE warning_series_id = ? ORDER BY event_at, id",
                    (series["id"],),
                )
            ]
            series["events"] = events
            series["source_references"] = [
                {
                    "bulletin_id": event["bulletin_id"],
                    "event_type": event["event_type"],
                    "source_url": event["source_url"],
                }
                for event in events
            ]
            output.write(json.dumps(series, ensure_ascii=False) + "\n")
            count += 1
    connection.close()
    print(f"Exported {count} warning series to {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

