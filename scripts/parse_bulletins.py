#!/usr/bin/env python3
"""Parse archived thunderstorm bulletin HTML into derived JSON records."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "info-gov-hk" / "bulletins"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "bulletin-events.jsonl"
HKT = timezone(timedelta(hours=8))
INFO_GOV_BASE = "https://www.info.gov.hk/gia/wr"

CHINESE_HOUR = re.compile(
    r"(?P<period>上午|下午|晚上|凌晨|中午|正午|午夜)?"
    r"(?P<hour>[零〇一二兩三四五六七八九十廿卅\d]{1,3})時"
    r"(?:(?P<minute>[零〇一二兩三四五六七八九十廿卅\d]{1,3})分|(?P<half>半)|(?P<exact>正))?"
)


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(html)
    return re.sub(r"\s+", "", "".join(parser.parts))


def decode_html(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8", "big5-hkscs", "big5"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    raise UnicodeError("HTML is neither UTF-8 nor Big5")


def bulletin_body(text: str) -> str:
    end = text.find("以上天氣稿")
    start = text.rfind("天文台", 0, end)
    if start < 0 or end < 0:
        raise ValueError("thunderstorm bulletin body not found")
    return text[start:end]


def number(value: str | None) -> int:
    if not value:
        return 0
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value.startswith("廿"):
        return 20 + number(value[1:])
    if value.startswith("卅"):
        return 30 + number(value[1:])
    if "十" in value:
        left, right = value.split("十", 1)
        return (number(left) if left else 1) * 10 + number(right)
    result = 0
    for char in value:
        result = result * 10 + digits[char]
    return result


def local_datetime(year: int, month: int, day: int, time_match: re.Match) -> datetime:
    hour = number(time_match.group("hour"))
    minute = 30 if time_match.group("half") else number(time_match.group("minute"))
    period = time_match.group("period")
    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif period in {"上午", "凌晨", "午夜"} and hour == 12:
        hour = 0
    return datetime(year, month, day, hour, minute, tzinfo=HKT)


def parse_full_timestamp(value: str) -> datetime:
    match = re.fullmatch(
        r"(?P<year>\d{4})年(?P<month>\d{2})月(?P<day>\d{2})日(?P<clock>.+)", value
    )
    if not match:
        raise ValueError(f"unsupported full timestamp: {value}")
    clock = CHINESE_HOUR.fullmatch(match.group("clock"))
    if not clock:
        raise ValueError(f"unsupported clock: {match.group('clock')}")
    return local_datetime(
        int(match.group("year")), int(match.group("month")), int(match.group("day")), clock
    )


def parse_month_day_time(value: str, reference: datetime) -> datetime:
    day_offset = 0
    if value.startswith("昨日"):
        day_offset = -1
        value = value[2:]
    else:
        value = re.sub(r"^(今日|今)", "", value)
    numeral = r"[零〇一二兩三四五六七八九十廿卅\d]{1,3}"
    match = re.fullmatch(
        rf"(?:(?P<month>{numeral})月(?P<day>{numeral})日)?(?P<clock>.+)", value
    )
    if not match:
        raise ValueError(f"unsupported month/day timestamp: {value}")
    clock = CHINESE_HOUR.fullmatch(match.group("clock"))
    if not clock:
        raise ValueError(f"unsupported clock: {match.group('clock')}")
    month = number(match.group("month")) if match.group("month") else reference.month
    day = number(match.group("day")) if match.group("day") else reference.day
    candidate = local_datetime(reference.year, month, day, clock)
    if not match.group("month") and day_offset:
        target = reference.date() + timedelta(days=day_offset)
        candidate = candidate.replace(year=target.year, month=target.month, day=target.day)
    # Handles a December bulletin referring to a January timestamp.
    if candidate - reference > timedelta(days=180):
        candidate = candidate.replace(year=candidate.year - 1)
    elif reference - candidate > timedelta(days=180):
        candidate = candidate.replace(year=candidate.year + 1)
    return candidate


def parse_relative_until(value: str, bulletin_at: datetime) -> datetime:
    if "月" in value and "日" in value:
        return parse_month_day_time(value, bulletin_at)
    day_offset = 0
    if value.startswith(("明日", "明早")):
        day_offset = 1
    if value.startswith("今晚午夜"):
        day_offset = 1
    clock_text = re.sub(r"^(今日|明日|明早|今早|今晚)", "", value)
    clock = CHINESE_HOUR.fullmatch(clock_text)
    if not clock:
        raise ValueError(f"unsupported effective-until timestamp: {value}")
    day = (bulletin_at + timedelta(days=day_offset)).date()
    return local_datetime(day.year, day.month, day.day, clock)


def parse_file(path: Path) -> dict:
    raw = path.read_bytes()
    html, source_encoding = decode_html(raw)
    text = visible_text(html)
    body = bulletin_body(text)
    warnings: list[str] = []
    parsing_body = body
    source_corrections = {
        "上午七時分": "上午七時",
        "上七午時": "上午七時",
    }
    for original, normalized in source_corrections.items():
        if original in parsing_body:
            parsing_body = parsing_body.replace(original, normalized)
            warnings.append(f"source time typo normalised: {original} -> {normalized}")

    bulletin_match = re.search(r"以上天氣稿由天文台於([^發]+)發出", text)
    if not bulletin_match:
        raise ValueError("bulletin timestamp not found")
    bulletin_at = parse_full_timestamp(bulletin_match.group(1))

    cancel_match = re.search(r"天文台(?:在)?(.+?)取消雷暴警告", parsing_body)
    issue_match = re.search(r"天文台(?:在)?(.+?)發出(?:之)?雷暴警告", parsing_body)
    until_match = re.search(r"有效時間(?:延長至|直至|至)(.+?)(?:，|。)", parsing_body)
    duration_match = re.search(
        r"(?:後之?|未來)([零〇一二兩三四五六七八九十廿卅\d]+)個?小時內",
        parsing_body,
    )
    range_until_match = re.search(r"後至(.+?)(?:會有|有|，|。)", parsing_body)
    if issue_match and "午夜12時" in issue_match.group(1):
        warnings.append("explicit-date midnight 12 is date-boundary ambiguous")

    if cancel_match:
        event_type = "cancelled"
        event_at = parse_month_day_time(cancel_match.group(1), bulletin_at)
        warning_started_at = None
        valid_until = None
    elif issue_match:
        warning_started_at = parse_month_day_time(issue_match.group(1), bulletin_at)
        event_at = bulletin_at
        if not until_match:
            if duration_match:
                valid_until = warning_started_at + timedelta(hours=number(duration_match.group(1)))
                event_type = "issued" if bulletin_at - warning_started_at <= timedelta(minutes=1) else "updated"
            elif range_until_match:
                valid_until = parse_relative_until(range_until_match.group(1), bulletin_at)
                event_type = "issued" if bulletin_at - warning_started_at <= timedelta(minutes=1) else "updated"
            else:
                event_type = "unknown"
                valid_until = None
                warnings.append("effective-until timestamp not found")
        else:
            valid_until = parse_relative_until(until_match.group(1), bulletin_at)
            if "有效時間延長至" in parsing_body:
                event_type = "extended"
            elif timedelta(0) <= bulletin_at - warning_started_at <= timedelta(minutes=1):
                event_type = "issued"
            else:
                event_type = "updated"
    elif until_match and "有效時間延長至" in parsing_body:
        event_type = "extended"
        event_at = bulletin_at
        warning_started_at = None
        valid_until = parse_relative_until(until_match.group(1), bulletin_at)
        warnings.append("original warning start omitted from extension bulletin")
    elif "預料高達" in parsing_body and "陣風" in parsing_body:
        event_type = "updated"
        event_at = bulletin_at
        warning_started_at = None
        valid_until = None
        warnings.append("gust update does not repeat warning start or valid-until time")
    else:
        event_type = "unknown"
        event_at = bulletin_at
        warning_started_at = None
        valid_until = None
        warnings.append("event wording not recognised")

    title_match = re.search(r"天氣稿第(\d+)號-雷暴警告", text)
    relative_parts = path.relative_to(RAW_ROOT).parts
    if len(relative_parts) != 4:
        raise ValueError(f"unexpected archive path: {path}")
    year, month, day, filename = relative_parts
    source_url = f"{INFO_GOV_BASE}/{year}{month}/{day}/{filename}"
    return {
        "source_file": str(path.relative_to(ROOT)),
        "source_url": source_url,
        "source_encoding": source_encoding,
        "is_correction": "更正" in text[: text.find("天文台在")],
        "bulletin_id": path.stem,
        "bulletin_number": int(title_match.group(1)) if title_match else None,
        "event_type": event_type,
        "event_at": event_at.isoformat(),
        "bulletin_at": bulletin_at.isoformat(),
        "warning_started_at": warning_started_at.isoformat() if warning_started_at else None,
        "valid_until": valid_until.isoformat() if valid_until else None,
        "body_text": body,
        "parse_warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--merge-existing",
        action="store_true",
        help="retain previously parsed source URLs when only recent raw HTML is present",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = []
    if args.merge_existing and args.output.exists():
        records = [json.loads(line) for line in args.output.read_text(encoding="utf-8").splitlines()]
    by_url = {record["source_url"]: record for record in records}
    errors = []
    for path in sorted(args.input.glob("**/*.htm")):
        try:
            record = parse_file(path)
            by_url[record["source_url"]] = record
        except (UnicodeError, ValueError) as error:
            errors.append({"source_file": str(path.relative_to(ROOT)), "error": str(error)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for record in sorted(by_url.values(), key=lambda row: (row["bulletin_at"], row["source_url"])):
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    error_path = args.output.with_name("parse-errors.jsonl")
    with error_path.open("w", encoding="utf-8") as output:
        for error in errors:
            output.write(json.dumps(error, ensure_ascii=False) + "\n")
    print(f"Stored {len(by_url)} parsed bulletins; {len(errors)} errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
