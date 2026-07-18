#!/usr/bin/env python3
"""Audit HKO thunderstorm records in backwards decade batches."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"
OUTPUT = ROOT / "data/processed/warndb-audit.json"
BATCHES = [(2026, 2026)] + [(start, start + 9) for start in range(2016, 1965, -10)]
HONG_KONG = ZoneInfo("Asia/Hong_Kong")


def normalized_datetime(year: int, month: int, day: int, hour: int, minute: int):
    if hour == 24 and minute == 0:
        return datetime(year, month, day, tzinfo=HONG_KONG) + timedelta(days=1), "24:00"
    return datetime(year, month, day, hour, minute, tzinfo=HONG_KONG), None


def load_records() -> tuple[list[dict], list[dict]]:
    records, errors = [], []
    for number, line in enumerate(SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split("\t")
        if not fields or not fields[0].isdigit():
            continue
        try:
            values = list(map(int, fields[:12]))
            sy, sm, sd, sh, smin, ey, em, ed, eh, emin, duration_h, duration_m = values
            start, start_note = normalized_datetime(sy, sm, sd, sh, smin)
            end, end_note = normalized_datetime(ey, em, ed, eh, emin)
            # Convert to UTC before subtraction: historical Hong Kong Summer Time
            # changed the UTC offset during some records from 1967 to 1979.
            calculated = int(
                (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() // 60
            )
            stated = duration_h * 60 + duration_m
            records.append(
                {
                    "line": number,
                    "start": start,
                    "end": end,
                    "stated_minutes": stated,
                    "calculated_minutes": calculated,
                    "special_times": [note for note in (start_note, end_note) if note],
                }
            )
        except (ValueError, OverflowError) as error:
            errors.append({"line": number, "raw": line, "error": str(error)})
    return records, errors


def main() -> int:
    records, errors = load_records()
    report = {"source": str(SOURCE.relative_to(ROOT)), "total_records": len(records), "batches": []}
    for start_year, end_year in BATCHES:
        selected = [row for row in records if start_year <= row["start"].year <= end_year]
        mismatches = [row for row in selected if row["stated_minutes"] != row["calculated_minutes"]]
        special = [row for row in selected if row["special_times"]]
        report["batches"].append(
            {
                "start_year": start_year,
                "end_year": end_year,
                "records": len(selected),
                "first": selected[0]["start"].isoformat() if selected else None,
                "last": selected[-1]["start"].isoformat() if selected else None,
                "cross_day": sum(row["start"].date() != row["end"].date() for row in selected),
                "cross_month": sum(
                    (row["start"].year, row["start"].month)
                    != (row["end"].year, row["end"].month)
                    for row in selected
                ),
                "cross_year": sum(row["start"].year != row["end"].year for row in selected),
                "duration_mismatches": len(mismatches),
                "duration_mismatch_records": [
                    {
                        "line": row["line"],
                        "start": row["start"].isoformat(),
                        "end": row["end"].isoformat(),
                        "stated_minutes": row["stated_minutes"],
                        "calculated_minutes": row["calculated_minutes"],
                    }
                    for row in mismatches
                ],
                "special_time_formats": dict(
                    Counter(note for row in special for note in row["special_times"])
                ),
            }
        )
    report["unparsed_lines"] = errors
    report["record_start"] = records[0]["start"].isoformat()
    report["record_end"] = records[-1]["end"].isoformat()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for batch in report["batches"]:
        print(
            f"{batch['start_year']}-{batch['end_year']}: {batch['records']} records, "
            f"{batch['duration_mismatches']} duration mismatches, "
            f"special={batch['special_time_formats']}"
        )
    print(f"Unparsed lines: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
