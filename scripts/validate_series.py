#!/usr/bin/env python3
"""Validate derived warning series boundaries against the official HKO database."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"
SERIES = ROOT / "data/processed/warning-series.jsonl"
OUTPUT = ROOT / "data/processed/series-validation.json"
HKT = ZoneInfo("Asia/Hong_Kong")


def official_records() -> dict[str, dict]:
    output = {}
    for line in DATABASE.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if not fields or not fields[0].isdigit():
            continue
        sy, sm, sd, sh, smin, ey, em, ed, eh, emin, duration_h, duration_m = map(int, fields[:12])
        start = datetime(sy, sm, sd, sh, smin, tzinfo=HKT)
        if eh == 24:
            end = datetime(ey, em, ed, tzinfo=HKT) + timedelta(days=1, minutes=emin)
        else:
            end = datetime(ey, em, ed, eh, emin, tzinfo=HKT)
        output[start.isoformat()] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_minutes": duration_h * 60 + duration_m,
        }
    return output


def main() -> int:
    official = official_records()
    derived = [json.loads(line) for line in SERIES.read_text(encoding="utf-8").splitlines()]
    comparisons = []
    for row in derived:
        expected = official.get(row["warning_started_at"])
        comparison = {
            "series_id": row["series_id"],
            "warning_started_at": row["warning_started_at"],
            "official_record_found": expected is not None,
            "derived_end": row["ended_at"],
            "official_end": expected["end"] if expected else None,
            "end_matches": expected is not None and row["ended_at"] == expected["end"],
            "derived_duration_minutes": row["duration_minutes"],
            "official_duration_minutes": expected["duration_minutes"] if expected else None,
            "duration_matches": expected is not None and row["duration_minutes"] == expected["duration_minutes"],
            "source_references": row["source_references"],
        }
        comparisons.append(comparison)
    report = {
        "derived_series": len(derived),
        "official_records_found": sum(row["official_record_found"] for row in comparisons),
        "end_matches": sum(row["end_matches"] for row in comparisons),
        "duration_matches": sum(row["duration_matches"] for row in comparisons),
        "comparisons": comparisons,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Validated {report['derived_series']} series: "
        f"official={report['official_records_found']}, ends={report['end_matches']}, "
        f"durations={report['duration_matches']}"
    )
    for row in comparisons:
        if not row["end_matches"] or not row["duration_matches"]:
            print(
                row["series_id"], "derived", row["derived_end"], row["derived_duration_minutes"],
                "official", row["official_end"], row["official_duration_minutes"]
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
