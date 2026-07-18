#!/usr/bin/env python3
"""Use hourly weather reports to corroborate archive-incomplete warning series."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/thunderstorm-warnings.sqlite3"
INDEX_ROOT = ROOT / "data/raw/info-gov-hk/indexes"
RAW_ROOT = ROOT / "data/raw/info-gov-hk/corroborating/missing-series-hourly"
MANIFEST = RAW_ROOT / "manifest.json"
BASE = "https://www.info.gov.hk/gia/wr/"


def decode(raw: bytes) -> str:
    for encoding in ("utf-8", "big5-hkscs", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href = None
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            text = re.sub(r"\s+", "", "".join(self.parts))
            if "每小時溫度濕度報告" in text:
                self.links.append(self.href)
            self.href = None


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def hourly_links(day: str) -> list[str]:
    year, month, date = day.split("-")
    index = INDEX_ROOT / year / month / date / "index.html"
    parser = LinkParser()
    parser.feed(decode(index.read_bytes()))
    source = f"{BASE}{year}{month}/{date}c.htm"
    return sorted({urljoin(source, link) for link in parser.links})


def fetch(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "hko-thunderstorm-archive/0.1"})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    path_parts = urlparse(url).path.split("/")
    ym, day, filename = path_parts[-3:]
    target = RAW_ROOT / ym[:4] / ym[4:] / day / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    parser = TextParser()
    parser.feed(decode(raw))
    text = re.sub(r"\s+", "", "".join(parser.parts))
    issued = re.search(r"以上天氣稿由天文台於(\d{4})年(\d{2})月(\d{2})日(\d{2})時(\d{2})分發出", text)
    report_at = None
    if issued:
        report_at = f"{issued.group(1)}-{issued.group(2)}-{issued.group(3)}T{issued.group(4)}:{issued.group(5)}:00+08:00"
    attention = ""
    start = text.find("請注意：")
    if start >= 0:
        end = text.find("本港其他地區", start)
        attention = text[start : end if end >= 0 else start + 500]
    return {
        "source_url": url,
        "source_file": str(target.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "report_at": report_at,
        "mentions_thunderstorm_warning": "雷暴警告" in attention,
        "attention_text": attention,
    }


def main() -> int:
    connection = sqlite3.connect(DATABASE)
    series = [
        {"id": row[0], "started_at": row[1], "ended_at": row[2]}
        for row in connection.execute(
            """SELECT id, started_at, ended_at FROM warning_series
            WHERE weather_bulletin_status='archive_incomplete' ORDER BY started_at"""
        )
    ]
    connection.close()
    all_days = set()
    for row in series:
        current = datetime.fromisoformat(row["started_at"]).date()
        end = datetime.fromisoformat(row["ended_at"]).date()
        while current <= end:
            all_days.add(current.isoformat())
            current += timedelta(days=1)
    links = sorted({link for day in all_days for link in hourly_links(day)})
    reports = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, link) for link in links]
        for future in as_completed(futures):
            reports.append(future.result())
    reports.sort(key=lambda row: row["report_at"] or "")
    for item in series:
        start, end = datetime.fromisoformat(item["started_at"]), datetime.fromisoformat(item["ended_at"])
        window_start, window_end = start - timedelta(hours=1), end + timedelta(hours=1)
        item["hourly_reports"] = [
            row for row in reports
            if row["report_at"] and window_start <= datetime.fromisoformat(row["report_at"]) <= window_end
        ]
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"series": series, "all_downloaded_reports": len(reports)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Downloaded {len(reports)} hourly reports")
    for item in series:
        print("\n", item["id"], item["started_at"], item["ended_at"])
        for row in item["hourly_reports"]:
            print(row["report_at"], row["mentions_thunderstorm_warning"], row["attention_text"], row["source_url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

