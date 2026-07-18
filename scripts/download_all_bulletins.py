#!/usr/bin/env python3
"""Download every obtainable thunderstorm bulletin referenced by official warning dates."""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from download_2026 import RAW_ROOT, archive, bulletin_links, index_url, paths


ROOT = Path(__file__).resolve().parents[1]
HKO_SOURCE = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"
LOG = RAW_ROOT / "full-download-log.jsonl"
LOG_LOCK = threading.Lock()


def candidate_dates() -> list[date]:
    days: set[date] = set()
    for line in HKO_SOURCE.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if not fields or not fields[0].isdigit():
            continue
        sy, sm, sd, _, _, ey, em, ed = map(int, fields[:8])
        start, end = date(sy, sm, sd), date(ey, em, ed)
        current = max(start, date(1998, 1, 1))
        while current <= end:
            days.add(current)
            current += timedelta(days=1)
    return sorted(days)


def completed_404s() -> set[str]:
    if not LOG.exists():
        return set()
    latest = {}
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            latest[row["date"]] = row
        except (json.JSONDecodeError, KeyError):
            pass
    return {day for day, row in latest.items() if row.get("index_status") == 404}


def append_log(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG_LOCK, LOG.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def with_retries(function, attempts: int = 3):
    last_error = None
    for attempt in range(attempts):
        try:
            return function()
        except HTTPError as error:
            if error.code == 404:
                raise
            last_error = error
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(1.5 * (attempt + 1))
    raise last_error


def download_day(day: date, force: bool) -> dict:
    source_url = index_url(day)
    index_html, index_meta = paths("indexes", day, "index.html")
    try:
        body = with_retries(lambda: archive(source_url, index_html, index_meta, force))
    except HTTPError as error:
        return {"date": day.isoformat(), "index_status": error.code, "bulletins": 0, "errors": []}
    except (URLError, TimeoutError, OSError) as error:
        return {"date": day.isoformat(), "index_status": None, "bulletins": 0, "errors": [str(error)]}

    links = bulletin_links(body, source_url)
    downloaded = 0
    errors = []
    for url in links:
        filename = Path(urlparse(url).path).name
        if not filename.lower().endswith((".htm", ".html")):
            continue
        target, metadata = paths("bulletins", day, filename)
        try:
            with_retries(lambda u=url, t=target, m=metadata: archive(u, t, m, force))
            downloaded += 1
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            errors.append({"source_url": url, "error": str(error)})
    return {
        "date": day.isoformat(),
        "index_status": 200,
        "bulletins": downloaded,
        "warning_links": len(links),
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, help="testing only: maximum candidate dates")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    days = candidate_dates()
    skipped = completed_404s() if not args.force else set()
    days = [day for day in days if day.isoformat() not in skipped]
    if args.limit:
        days = days[: args.limit]
    totals = {"days": 0, "indexes": 0, "not_found": len(skipped), "bulletins": 0, "errors": 0}
    print(f"Processing {len(days)} candidate dates ({len(skipped)} known 404 dates skipped)")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_day, day, args.force): day for day in days}
        for future in as_completed(futures):
            row = future.result()
            append_log(row)
            totals["days"] += 1
            totals["indexes"] += int(row["index_status"] == 200)
            totals["not_found"] += int(row["index_status"] == 404)
            totals["bulletins"] += row["bulletins"]
            totals["errors"] += len(row["errors"])
            if totals["days"] % 100 == 0:
                print(json.dumps(totals))
    print(json.dumps(totals))
    return 1 if totals["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

