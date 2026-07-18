#!/usr/bin/env python3
"""Refresh current official data, recent bulletin pages, and derived outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from download_all_bulletins import LOG, append_log, candidate_dates, download_day


ROOT = Path(__file__).resolve().parents[1]
HKT = ZoneInfo("Asia/Hong_Kong")
STATE = ROOT / "data/processed/daily-update-state.json"
ARCHIVE_STATE = ROOT / "data/processed/archive-date-status.json"


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)


def archive_statuses() -> dict[str, int | None]:
    statuses = {}
    if ARCHIVE_STATE.exists():
        try:
            statuses.update(json.loads(ARCHIVE_STATE.read_text(encoding="utf-8")).get("dates", {}))
        except json.JSONDecodeError:
            pass
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                statuses[row["date"]] = row.get("index_status")
            except (json.JSONDecodeError, KeyError):
                pass
    return statuses


def save_archive_statuses(statuses: dict[str, int | None]) -> None:
    ARCHIVE_STATE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_STATE.write_text(json.dumps({
        "generated_at": datetime.now(HKT).isoformat(),
        "dates": dict(sorted(statuses.items())),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=2)
    parser.add_argument("--skip-download", action="store_true", help="test rebuild without network")
    args = parser.parse_args()
    if args.lookback_days < 1 or args.lookback_days > 14:
        parser.error("--lookback-days must be between 1 and 14")

    started = datetime.now(HKT)
    download_rows = []
    statuses = archive_statuses()
    if not args.skip_download:
        run("download_warning_database.py")
        try:
            run("download_analysis_sources.py")
        except subprocess.CalledProcessError:
            required = [ROOT / "data/raw/weather-gov-hk/analysis" / name for name in ("rstorm.dat", "tc.dat", "thunderstorm-days.json")]
            if not all(path.exists() for path in required):
                raise
            print("Warning: external analysis refresh failed; retaining the previous archived copies", file=sys.stderr)
        today = datetime.now(HKT).date()
        missing = [day for day in candidate_dates() if day.isoformat() not in statuses]
        recent = [today - timedelta(days=offset) for offset in range(args.lookback_days)]
        days = sorted(set(missing + recent))
        print(f"Checking {len(days)} dates: {len(missing)} previously unchecked, {len(recent)} recent")
        for day in days:
            row = download_day(day, force=day in recent)
            append_log(row)
            download_rows.append(row)
            statuses[row["date"]] = row.get("index_status")
        if any(row["errors"] for row in download_rows):
            raise RuntimeError("one or more daily bulletin downloads failed")
    save_archive_statuses(statuses)
    run("export_archive_evidence.py")

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/parse_bulletins.py"), "--merge-existing"],
        cwd=ROOT,
        check=True,
    )
    for script in ("build_database.py", "export_jsonl.py", "export_analysis.py", "package_open_data.py"):
        run(script)

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "started_at": started.isoformat(),
        "completed_at": datetime.now(HKT).isoformat(),
        "lookback_days": args.lookback_days,
        "downloads": download_rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Daily refresh completed: {STATE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
