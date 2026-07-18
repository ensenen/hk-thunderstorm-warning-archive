#!/usr/bin/env python3
"""Archive thunderstorm-warning HTML from HKSAR weather bulletins."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://www.info.gov.hk/gia/wr/"
ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "info-gov-hk"
USER_AGENT = "hko-thunderstorm-archive/0.1 (research archive)"
HKT = timezone(timedelta(hours=8))


class BulletinIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = re.sub(r"\s+", "", "".join(self._text))
        if "雷暴警告" in text:
            self.links.append(self._href)
        self._href = None
        self._text = []


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def index_url(day: date) -> str:
    return f"{BASE_URL}{day:%Y%m}/{day:%d}c.htm"


def paths(kind: str, day: date, filename: str) -> tuple[Path, Path]:
    html_path = RAW_ROOT / kind / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / filename
    relative = html_path.relative_to(RAW_ROOT / kind)
    metadata_path = RAW_ROOT / "metadata" / kind / relative.with_suffix(".json")
    return html_path, metadata_path


def fetch(url: str) -> tuple[bytes, dict[str, str], int]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        return body, headers, response.status


def archive(url: str, html_path: Path, metadata_path: Path, force: bool) -> bytes:
    if html_path.exists() and not force:
        return html_path.read_bytes()

    body, headers, status = fetch(url)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_bytes(body)
    metadata = {
        "source_url": url,
        "fetched_at": datetime.now(HKT).isoformat(),
        "status": status,
        "content_type": headers.get("content-type"),
        "last_modified": headers.get("last-modified"),
        "etag": headers.get("etag"),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return body


def decode_html(body: bytes) -> str:
    # Government archive pages may use either UTF-8 or Big5.
    for encoding in ("utf-8", "big5-hkscs", "big5"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            pass
    return body.decode("utf-8", errors="replace")


def bulletin_links(body: bytes, source_url: str) -> list[str]:
    parser = BulletinIndexParser()
    parser.feed(decode_html(body))
    urls = {urljoin(source_url, href) for href in parser.links}
    return sorted(url for url in urls if urlparse(url).netloc == "www.info.gov.hk")


def log_result(record: dict) -> None:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    with (RAW_ROOT / "download-log.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def download_day(day: date, force: bool, delay: float) -> tuple[int, int]:
    source_url = index_url(day)
    index_html, index_meta = paths("indexes", day, "index.html")
    try:
        body = archive(source_url, index_html, index_meta, force)
        links = bulletin_links(body, source_url)
        downloaded = 0
        for url in links:
            filename = Path(urlparse(url).path).name
            if not filename.lower().endswith((".htm", ".html")):
                continue
            target, metadata = paths("bulletins", day, filename)
            archive(url, target, metadata, force)
            downloaded += 1
            if delay:
                time.sleep(delay)
        log_result({"date": day.isoformat(), "status": "ok", "bulletins": downloaded})
        return 1, downloaded
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        log_result({"date": day.isoformat(), "status": "error", "error": str(error)})
        print(f"{day}: {error}", file=sys.stderr)
        return 0, 0


def parse_args() -> argparse.Namespace:
    today = datetime.now(HKT).date()
    default_end = min(today, date(2026, 12, 31))
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=default_end)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay", type=float, default=0.15, help="delay between bulletin requests")
    args = parser.parse_args()
    if args.start < date(1967, 1, 1) or args.end > default_end or args.start > args.end:
        parser.error(f"dates must be ordered between 1967-01-01 and {default_end}")
    return args


def main() -> int:
    args = parse_args()
    indexes = bulletins = 0
    for day in daterange(args.start, args.end):
        index_count, bulletin_count = download_day(day, args.force, args.delay)
        indexes += index_count
        bulletins += bulletin_count
    print(f"Archived {indexes} daily indexes and {bulletins} thunderstorm bulletins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
