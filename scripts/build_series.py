#!/usr/bin/env python3
"""Group parsed bulletins into warning series and derive terminal events."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "bulletin-events.jsonl"
OUTPUT = ROOT / "data" / "processed" / "warning-series.jsonl"


def dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def build(records: list[dict]) -> list[dict]:
    records = sorted(records, key=lambda row: dt(row["event_at"]))
    groups: dict[str, list[dict]] = {}
    cancellations: list[dict] = []
    for record in records:
        start = record["warning_started_at"]
        if start:
            groups.setdefault(start, []).append(record)
        elif record["event_type"] == "cancelled":
            cancellations.append(record)

    series = []
    for start_value, events in sorted(groups.items()):
        events.sort(key=lambda row: dt(row["event_at"]))
        start = dt(start_value)
        last_valid = max(dt(row["valid_until"]) for row in events if row["valid_until"])
        matching_cancel = next(
            (
                row
                for row in cancellations
                if start <= dt(row["event_at"]) <= last_valid
            ),
            None,
        )
        output_events = list(events)
        if matching_cancel:
            ended_at = dt(matching_cancel["event_at"])
            terminal_type = "cancelled_early" if ended_at < last_valid else "expired"
            terminal_inferred = False
            terminal_source = matching_cancel["bulletin_id"]
            output_events.append(matching_cancel)
        else:
            ended_at = last_valid
            terminal_type = "expired"
            terminal_inferred = True
            terminal_source = None

        series.append(
            {
                "series_id": f"WTS-{start:%Y%m%d-%H%M}",
                "warning_started_at": start.isoformat(),
                "ended_at": ended_at.isoformat(),
                "last_valid_until": last_valid.isoformat(),
                "terminal_type": terminal_type,
                "terminal_inferred": terminal_inferred,
                "terminal_source_bulletin_id": terminal_source,
                "duration_minutes": int((ended_at - start).total_seconds() // 60),
                "source_references": [
                    {
                        "bulletin_id": row["bulletin_id"],
                        "event_type": row["event_type"],
                        "source_url": row["source_url"],
                    }
                    for row in output_events
                ],
                "events": output_events,
            }
        )
    return series


def main() -> int:
    records = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines()]
    series = build(records)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as output:
        for item in series:
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Built {len(series)} warning series.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
