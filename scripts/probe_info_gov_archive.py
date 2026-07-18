#!/usr/bin/env python3
"""Probe representative thunderstorm dates across archive decade batches."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"
RAW_ROOT = ROOT / "data/raw/info-gov-hk/archive-probes"
REPORT = ROOT / "data/processed/info-gov-archive-probes.json"
HKT = timezone(timedelta(hours=8))
BATCHES = [(2026, 2026)] + [(start, start + 9) for start in range(2016, 1965, -10)]
BOUNDARY_YEARS = range(1996, 2002)


def warning_dates() -> list[date]:
    dates = []
    for line in DATABASE.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if fields and fields[0].isdigit():
            dates.append(date(int(fields[0]), int(fields[1]), int(fields[2])))
    return sorted(set(dates))


def samples_for_batch(dates: list[date], start: int, end: int) -> list[date]:
    selected = [day for day in dates if start <= day.year <= end]
    if len(selected) <= 3:
        return selected
    return [selected[0], selected[len(selected) // 2], selected[-1]]


def probe(day: date) -> dict:
    url = f"https://www.info.gov.hk/gia/wr/{day:%Y%m}/{day:%d}c.htm"
    request = Request(url, headers={"User-Agent": "hko-thunderstorm-archive/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
            status = response.status
            final_url = response.url
        decoded = None
        encoding = None
        for candidate in ("utf-8", "big5-hkscs", "big5"):
            try:
                decoded = body.decode(candidate)
                encoding = candidate
                break
            except UnicodeDecodeError:
                pass
        contains_warning = decoded is not None and "雷暴警告" in decoded
        path = RAW_ROOT / f"{day:%Y/%m/%d}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return {
            "date": day.isoformat(),
            "source_url": url,
            "final_url": final_url,
            "status": status,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "contains_thunderstorm_warning": contains_warning,
            "encoding": encoding,
            "raw_file": str(path.relative_to(ROOT)),
        }
    except HTTPError as error:
        return {"date": day.isoformat(), "source_url": url, "status": error.code, "error": str(error)}
    except (URLError, TimeoutError, OSError) as error:
        return {"date": day.isoformat(), "source_url": url, "status": None, "error": str(error)}


def main() -> int:
    dates = warning_dates()
    jobs = []
    for start, end in BATCHES:
        for day in samples_for_batch(dates, start, end):
            jobs.append((start, end, day))
    for year in BOUNDARY_YEARS:
        for day in samples_for_batch(dates, year, year):
            jobs.append((year, year, day))
    jobs = list(dict.fromkeys(jobs))
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(probe, day): (start, end) for start, end, day in jobs}
        for future in as_completed(futures):
            start, end = futures[future]
            result = future.result()
            result["batch"] = f"{start}-{end}"
            results.append(result)
    results.sort(key=lambda row: row["date"])
    report = {
        "generated_at": datetime.now(HKT).isoformat(),
        "method": "first, middle and last thunderstorm start date in each batch",
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print(row["batch"], row["date"], row["status"], row.get("contains_thunderstorm_warning"), row.get("bytes"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
