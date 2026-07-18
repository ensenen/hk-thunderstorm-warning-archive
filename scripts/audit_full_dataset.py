#!/usr/bin/env python3
"""Run completion checks over raw files, parsed events and SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from download_all_bulletins import candidate_dates


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/info-gov-hk"
DATABASE = ROOT / "data/thunderstorm-warnings.sqlite3"
REPORT = ROOT / "data/processed/full-dataset-audit.json"


def latest_download_rows() -> dict[str, dict]:
    latest = {}
    for line in (RAW / "full-download-log.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        latest[row["date"]] = row
    return latest


def verify_raw_files() -> tuple[int, int, list[str]]:
    files = sorted(RAW.glob("bulletins/**/*.*htm*"))
    checked = 0
    errors = []
    for path in files:
        relative = path.relative_to(RAW / "bulletins")
        metadata = RAW / "metadata/bulletins" / relative.with_suffix(".json")
        if not metadata.exists():
            errors.append(f"missing metadata: {relative}")
            continue
        expected = json.loads(metadata.read_text(encoding="utf-8"))["sha256"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"checksum mismatch: {relative}")
        checked += 1
    return len(files), checked, errors


def main() -> int:
    candidates = {day.isoformat() for day in candidate_dates()}
    downloads = latest_download_rows()
    download_errors = [row for row in downloads.values() if row.get("errors")]
    raw_files, checksum_files, raw_errors = verify_raw_files()
    parsed_events = sum(1 for _ in (ROOT / "data/processed/bulletin-events.jsonl").open(encoding="utf-8"))
    parse_errors = sum(1 for _ in (ROOT / "data/processed/parse-errors.jsonl").open(encoding="utf-8"))
    official_series = sum(
        1
        for line in (ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat").read_text(encoding="utf-8").splitlines()
        if line.split("\t", 1)[0].isdigit()
    )

    connection = sqlite3.connect(DATABASE)
    scalar = lambda sql: connection.execute(sql).fetchone()[0]
    report = {
        "candidate_dates": len(candidates),
        "candidate_dates_logged": len(candidates & downloads.keys()),
        "successful_daily_indexes": sum(downloads[day].get("index_status") == 200 for day in candidates),
        "not_found_daily_indexes": sum(downloads[day].get("index_status") == 404 for day in candidates),
        "download_error_days": len(download_errors),
        "raw_bulletin_files": raw_files,
        "raw_bulletin_checksums_verified": checksum_files,
        "raw_file_errors": raw_errors,
        "parsed_bulletin_events": parsed_events,
        "parse_errors": parse_errors,
        "sqlite_warning_series": scalar("SELECT count(*) FROM warning_series"),
        "sqlite_bulletin_events": scalar("SELECT count(*) FROM bulletin_events"),
        "sqlite_unique_source_urls": scalar("SELECT count(DISTINCT source_url) FROM bulletin_events"),
        "sqlite_matched_events": scalar("SELECT count(*) FROM bulletin_events WHERE assignment_status='matched'"),
        "sqlite_unmatched_events": scalar("SELECT count(*) FROM bulletin_events WHERE assignment_status='unmatched'"),
        "sqlite_corroborating_sources": scalar("SELECT count(*) FROM corroborating_sources"),
        "sqlite_not_downloaded_series": scalar("SELECT count(*) FROM warning_series WHERE weather_bulletin_status='not_downloaded'"),
        "series_status_counts": dict(connection.execute(
            "SELECT weather_bulletin_status, count(*) FROM warning_series GROUP BY weather_bulletin_status"
        ).fetchall()),
        "terminal_type_counts": dict(connection.execute(
            "SELECT terminal_type, count(*) FROM warning_series GROUP BY terminal_type"
        ).fetchall()),
        "terminal_inferred_counts": dict(connection.execute(
            "SELECT terminal_inferred, count(*) FROM warning_series GROUP BY terminal_inferred"
        ).fetchall()),
        "event_type_counts": dict(connection.execute(
            "SELECT event_type, count(*) FROM bulletin_events GROUP BY event_type"
        ).fetchall()),
        "correction_bulletins": scalar("SELECT count(*) FROM bulletin_events WHERE is_correction=1"),
        "reported_start_differs_from_official": scalar(
            "SELECT count(*) FROM bulletin_events WHERE official_start_delta_minutes != 0"
        ),
    }
    connection.close()
    invariants = {
        "all_candidate_dates_logged": report["candidate_dates"] == report["candidate_dates_logged"],
        "no_download_errors": report["download_error_days"] == 0,
        "all_raw_checksums_valid": not raw_errors and raw_files == checksum_files,
        "all_raw_files_parsed": raw_files == parsed_events and parse_errors == 0,
        "all_events_in_sqlite": parsed_events == report["sqlite_bulletin_events"] == report["sqlite_unique_source_urls"],
        "all_official_series_in_sqlite": report["sqlite_warning_series"] == official_series,
        "no_not_downloaded_series": report["sqlite_not_downloaded_series"] == 0,
    }
    report["invariants"] = invariants
    report["passed"] = all(invariants.values())
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
