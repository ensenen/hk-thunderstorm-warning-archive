"""Reproducible calculations for the public analysis dashboard."""

from __future__ import annotations

import html
import json
import math
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data/thunderstorm-warnings.sqlite3"
EXTERNAL = ROOT / "data/raw/weather-gov-hk/analysis"
HKT = ZoneInfo("Asia/Hong_Kong")

REGIONS = [
    "香港", "新界北部", "新界東部", "新界西部", "新界",
    "香港東部水域", "大嶼山", "香港南部水域及島嶼", "香港島及九龍",
]
TEMPLATES = [
    ("相對時長", "後之%小時內"),
    ("明確有效時間", "有效時間至"),
    ("結構化預防措施", "請採取以下預防措施"),
    ("地區化描述", "局部地區雷暴"),
    ("猛烈陣風", "猛烈陣風"),
]


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def iso_datetime(year, month, day, hour, minute) -> datetime:
    year, month, day, hour, minute = map(int, (year, month, day, hour, minute))
    if hour == 24:
        return datetime(year, month, day, tzinfo=HKT) + timedelta(days=1, minutes=minute)
    return datetime(year, month, day, hour, minute, tzinfo=HKT)


def parse_rainstorm() -> list[dict]:
    rows = []
    for line in (EXTERNAL / "rstorm.dat").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("\t")
        if len(fields) < 11:
            continue
        rows.append({"level": fields[0], "start": iso_datetime(*fields[1:6]), "end": iso_datetime(*fields[6:11])})
    return rows


def hhmm(value: str) -> tuple[int, int]:
    number = int(value)
    return number // 100, number % 100


def parse_tc() -> list[dict]:
    rows = []
    for line in (EXTERNAL / "tc.dat").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("\t")
        if len(fields) < 16 or not fields[0].isdigit() or fields[3] == "0":
            continue
        sh, sm = hhmm(fields[5]); eh, em = hhmm(fields[10])
        try:
            start = iso_datetime(fields[8], fields[7], fields[6], sh, sm)
            end = iso_datetime(fields[13], fields[12], fields[11], eh, em)
        except ValueError:
            continue
        rows.append({"signal": fields[3], "name": fields[2], "start": start, "end": end})
    return rows


def thunderstorm_days() -> list[dict]:
    raw = json.loads((EXTERNAL / "thunderstorm-days.json").read_text(encoding="utf-8"))
    table = raw["ext_tslg_statistic"]["html_table"][0]
    rows = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.I | re.S):
        cells = []
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S):
            text = html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
            cells.append(text)
        if len(cells) >= 14 and re.fullmatch(r"\d{4}", cells[0]):
            values = [0 if value in ("-", "") else int(value) for value in cells[1:14]]
            rows.append({"year": int(cells[0]), "months": values[:12], "total": values[12]})
    return rows


def overlaps(start: datetime, end: datetime, other: dict) -> bool:
    return start < other["end"] and end > other["start"]


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return round(numerator / denominator, 3) if denominator else None


def affected_regions(text: str) -> set[str]:
    regions = {region for region in REGIONS[1:] if region in text}
    territory_patterns = ("預料香港有", "預料香港會有", "香港將受雷暴影響", "雷暴將影響香港")
    if any(pattern in text for pattern in territory_patterns):
        regions.add("香港")
    elif not regions and any(pattern in text for pattern in ("內有雷暴", "內會有雷暴", "內有狂風雷暴", "局部地區性狂風雷暴")):
        regions.add("香港")
    return regions


def build_analysis() -> dict:
    sources = [DATABASE, EXTERNAL / "rstorm.dat", EXTERNAL / "tc.dat", EXTERNAL / "thunderstorm-days.json"]
    version = tuple(path.stat().st_mtime_ns for path in sources)
    return _build_analysis(version)


@lru_cache(maxsize=2)
def _build_analysis(_version: tuple[int, ...]) -> dict:
    with connection() as db:
        series = [dict(row) for row in db.execute("SELECT * FROM warning_series ORDER BY started_at")]
        events = [dict(row) for row in db.execute("SELECT * FROM bulletin_events ORDER BY bulletin_at")]
    heatmap = [[0 for _ in range(24)] for _ in range(12)]
    years = defaultdict(list)
    months = Counter()
    for row in series:
        start = datetime.fromisoformat(row["started_at"])
        heatmap[start.month - 1][start.hour] += 1
        months[start.month] += 1
        years[start.year].append(row["duration_minutes"])
    duration_trend = [{"year": year, "count": len(values), "average": round(statistics.mean(values), 1), "median": statistics.median(values)} for year, values in sorted(years.items())]
    duration_buckets = []
    for label, low, high in [("<1小時", 0, 60), ("1–2小時", 60, 120), ("2–4小時", 120, 240), ("4–8小時", 240, 480), ("8–24小時", 480, 1440), ("≥24小時", 1440, 10**9)]:
        duration_buckets.append({"label": label, "count": sum(low <= row["duration_minutes"] < high for row in series)})

    events_by_series = defaultdict(list)
    for event in events:
        if event["warning_series_id"]:
            events_by_series[event["warning_series_id"]].append(event)
    complexity = []
    extension_distribution = Counter()
    extension_unknown = 0
    for row in series:
        group = events_by_series[row["id"]]
        extensions = sum(event["event_type"] == "extended" for event in group)
        if row["weather_bulletin_status"] == "available":
            extension_distribution["0" if extensions == 0 else "1" if extensions == 1 else "2–3" if extensions <= 3 else "4–7" if extensions <= 7 else "8+"] += 1
        else:
            extension_unknown += 1
        complexity.append({"id": row["id"], "started_at": row["started_at"], "events": len(group), "extensions": extensions, "duration": row["duration_minutes"]})
    complexity.sort(key=lambda row: (row["events"], row["extensions"], row["duration"]), reverse=True)

    margins = []
    for row in series:
        if row["terminal_type"] == "cancelled_early" and row["scheduled_until_at_end"]:
            margin = int((datetime.fromisoformat(row["scheduled_until_at_end"]) - datetime.fromisoformat(row["ended_at"])).total_seconds() / 60)
            if margin > 0:
                margins.append({"id": row["id"], "started_at": row["started_at"], "minutes": margin})
    margins.sort(key=lambda row: row["minutes"], reverse=True)

    region_events = {region: [] for region in REGIONS}
    for event in events:
        for region in affected_regions(event["body_text"]):
            region_events[region].append(event)
    place_counts = []
    for region in REGIONS:
        matches = region_events[region]
        series_ids = {event["warning_series_id"] for event in matches if event["warning_series_id"]}
        series_by_year = defaultdict(set)
        for event in matches:
            if event["warning_series_id"]:
                series_by_year[event["bulletin_at"][:4]].add(event["warning_series_id"])
        place_counts.append({
            "place": region,
            "count": len(series_ids),
            "bulletin_count": len(matches),
            "first_year": min((event["bulletin_at"][:4] for event in matches), default=None),
            "last_year": max((event["bulletin_at"][:4] for event in matches), default=None),
            "yearly": {year: len(ids) for year, ids in series_by_year.items()},
        })

    gusts_by_series = {}
    for event in events:
        speeds = [int(value) for value in re.findall(r"每小時\s*(\d{2,3})\s*公里", event["body_text"])]
        if speeds and event["warning_series_id"]:
            candidate = {"speed": max(speeds), "at": event["bulletin_at"], "source_url": event["source_url"], "series_id": event["warning_series_id"]}
            existing = gusts_by_series.get(event["warning_series_id"])
            if not existing or candidate["speed"] > existing["speed"]:
                gusts_by_series[event["warning_series_id"]] = candidate
    gusts = list(gusts_by_series.values())
    gusts.sort(key=lambda row: (row["speed"], row["at"]), reverse=True)
    hazards = []
    for key, label in [("violent_gusts", "猛烈陣風"), ("hail", "冰雹"), ("waterspout", "水龍捲"), ("severe_squally_thunderstorm", "強烈狂風雷暴")]:
        matches = [event for event in events if label in event["body_text"]]
        series_ids = {event["warning_series_id"] for event in matches if event["warning_series_id"]}
        series_by_year = defaultdict(set)
        for event in matches:
            if event["warning_series_id"]:
                series_by_year[event["bulletin_at"][:4]].add(event["warning_series_id"])
        hazards.append({"key": key, "label": label, "count": len(series_ids), "bulletin_count": len(matches), "years": {year: len(ids) for year, ids in series_by_year.items()}})

    templates = []
    for label, phrase in TEMPLATES:
        token = phrase.replace("%", "")
        matching = [event for event in events if all(part in event["body_text"] for part in phrase.split("%") if part)]
        templates.append({"label": label, "count": len(matching), "first": min((event["bulletin_at"][:4] for event in matching), default=None), "last": max((event["bulletin_at"][:4] for event in matching), default=None), "yearly": dict(Counter(event["bulletin_at"][:4] for event in matching))})

    quality_years = []
    for year in sorted({row["started_at"][:4] for row in series}):
        subset = [row for row in series if row["started_at"].startswith(year)]
        quality_years.append({"year": year, **dict(Counter(row["weather_bulletin_status"] for row in subset))})
    deltas = [event for event in events if event["official_start_delta_minutes"] not in (None, 0)]
    deltas.sort(key=lambda row: abs(row["official_start_delta_minutes"]), reverse=True)

    rainstorms, cyclones = parse_rainstorm(), parse_tc()
    overlap_counts = Counter()
    overlap_years = defaultdict(Counter)
    for row in series:
        start, end = datetime.fromisoformat(row["started_at"]), datetime.fromisoformat(row["ended_at"])
        year = str(start.year)
        rain_levels = {other["level"] for other in rainstorms if overlaps(start, end, other)}
        if rain_levels:
            overlap_counts["rain_any"] += 1; overlap_years[year]["rain_any"] += 1
        for level in rain_levels:
            overlap_counts[f"rain_{level}"] += 1; overlap_years[year][f"rain_{level}"] += 1
        signals = {other["signal"] for other in cyclones if overlaps(start, end, other)}
        if signals:
            overlap_counts["tc_any"] += 1; overlap_years[year]["tc_any"] += 1
        if any(signal in {"8", "9", "10"} for signal in signals):
            overlap_counts["tc_8plus"] += 1; overlap_years[year]["tc_8plus"] += 1

    observed = thunderstorm_days()
    warning_counts = Counter(datetime.fromisoformat(row["started_at"]).year for row in series)
    climate_rows = [{"year": row["year"], "thunderstorm_days": row["total"], "warning_series": warning_counts[row["year"]]} for row in observed if row["year"] >= 1967]
    pairs = [(row["thunderstorm_days"], row["warning_series"]) for row in climate_rows]
    climate_periods = []
    for label, start_year, end_year in [("1967–1997", 1967, 1997), ("1998–2004", 1998, 2004), ("2005後", 2005, 9999)]:
        subset = [(row["thunderstorm_days"], row["warning_series"]) for row in climate_rows if start_year <= row["year"] <= end_year]
        climate_periods.append({"period": label, "years": len(subset), "pearson": pearson(subset)})
    normal_rows = [row for row in observed if 1991 <= row["year"] <= 2020]
    monthly_normals = [round(statistics.mean(row["months"][month] for row in normal_rows), 2) for month in range(12)]
    normal_warning_months = Counter(
        datetime.fromisoformat(row["started_at"]).month
        for row in series
        if 1991 <= datetime.fromisoformat(row["started_at"]).year <= 2020
    )
    monthly_warning_average = [round(normal_warning_months[month] / 30, 2) for month in range(1, 13)]

    all_durations = [row["duration_minutes"] for row in series]
    return {
        "generated_from": {"series": len(series), "events": len(events), "generated_at": datetime.now(HKT).isoformat(), "warning_start_year": min(row["started_at"][:4] for row in series), "warning_end_year": max(row["started_at"][:4] for row in series), "bulletin_start_year": min(event["bulletin_at"][:4] for event in events), "bulletin_end_year": max(event["bulletin_at"][:4] for event in events), "external_sources": ["rstorm.dat", "tc.dat", "thunderstorm-days.json"]},
        "behavior": {"heatmap": heatmap, "monthly": [months[i] for i in range(1, 13)], "duration_trend": duration_trend, "duration_buckets": duration_buckets, "duration_summary": {"median": statistics.median(all_durations), "p90": percentile(all_durations, .9), "maximum": max(all_durations)}},
        "extensions": {"distribution": dict(extension_distribution), "analysed_series": sum(extension_distribution.values()), "unknown_series": extension_unknown, "top_complex": complexity[:12]},
        "cancellations": {"count": len(margins), "median_margin": statistics.median([row["minutes"] for row in margins]), "p90_margin": percentile([row["minutes"] for row in margins], .9), "top": margins[:10]},
        "geography": place_counts,
        "geography_method": {"method": "由天氣稿文字規則推斷官方九個預設分區", "classified_bulletins": sum(bool(affected_regions(event["body_text"])) for event in events), "unclassified_bulletins": sum(not affected_regions(event["body_text"]) for event in events), "multi_region_bulletins": sum(len(affected_regions(event["body_text"])) > 1 for event in events)},
        "hazards": {"terms": hazards, "top_gusts": gusts[:12]},
        "templates": templates,
        "quality": {"by_year": quality_years, "different_start_count": len(deltas), "corrections": sum(event["is_correction"] for event in events), "unmatched": sum(event["assignment_status"] == "unmatched" for event in events), "largest_start_deltas": [{key: row[key] for key in ("warning_series_id", "bulletin_at", "official_start_delta_minutes", "source_url")} for row in deltas[:12]]},
        "overlaps": {"counts": dict(overlap_counts), "by_year": [{"year": year, **counts} for year, counts in sorted(overlap_years.items())], "rainstorm_records": len(rainstorms), "tc_records": len(cyclones)},
        "climate": {"annual": climate_rows, "pearson_all": pearson(pairs), "pearson_by_period": climate_periods, "monthly_thunderstorm_day_normals_1991_2020": monthly_normals, "monthly_warning_series_average_1991_2020": monthly_warning_average, "note": "雷暴日是天文台總部觀測值；警告系列受制度、預報能力及發布方法改變影響。相關系數只描述兩組年度數據同步程度，不代表因果。月份圖兩組數據各自縮放，只適合比較季節形狀。"},
    }
