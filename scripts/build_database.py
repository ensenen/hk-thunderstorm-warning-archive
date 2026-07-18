#!/usr/bin/env python3
"""Build the queryable SQLite database from raw HKO data and parsed bulletins."""

from __future__ import annotations

import json
import sqlite3
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "thunderstorm-warnings.sqlite3"
HKO_SOURCE = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"
EVENTS_SOURCE = ROOT / "data/processed/bulletin-events.jsonl"
DOWNLOAD_LOG = ROOT / "data/raw/info-gov-hk/full-download-log.jsonl"
DOWNLOAD_STATE = ROOT / "data/processed/archive-date-status.json"
CORROBORATING_MANIFESTS = ROOT / "data/raw/info-gov-hk/corroborating"
ENGLISH_PROBE_MANIFEST = ROOT / "data/raw/info-gov-hk/english-index-probes/manifest.json"
REPRODUCIBILITY_STATE = ROOT / "data/processed/archive-evidence-state.json"
HONG_KONG = ZoneInfo("Asia/Hong_Kong")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE warning_series (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL UNIQUE,
    ended_at TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    hko_stated_duration_minutes INTEGER NOT NULL,
    start_utc_offset TEXT NOT NULL,
    end_utc_offset TEXT NOT NULL,
    crosses_day INTEGER NOT NULL CHECK (crosses_day IN (0, 1)),
    crosses_month INTEGER NOT NULL CHECK (crosses_month IN (0, 1)),
    crosses_year INTEGER NOT NULL CHECK (crosses_year IN (0, 1)),
    terminal_type TEXT NOT NULL CHECK (terminal_type IN ('expired', 'cancelled_early', 'unknown')),
    terminal_inferred INTEGER NOT NULL CHECK (terminal_inferred IN (0, 1)),
    scheduled_until_at_end TEXT,
    terminal_source_url TEXT,
    has_weather_bulletin INTEGER NOT NULL CHECK (has_weather_bulletin IN (0, 1)),
    weather_bulletin_status TEXT NOT NULL CHECK (
        weather_bulletin_status IN ('available', 'not_archived', 'not_downloaded', 'archive_incomplete')
    ),
    weather_bulletin_note TEXT,
    official_source_url TEXT NOT NULL,
    raw_source_file TEXT NOT NULL
);

CREATE TABLE bulletin_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    warning_series_id TEXT REFERENCES warning_series(id),
    assignment_status TEXT NOT NULL CHECK (assignment_status IN ('matched', 'unmatched')),
    assignment_note TEXT,
    bulletin_id TEXT NOT NULL,
    bulletin_number INTEGER,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    bulletin_at TEXT NOT NULL,
    reported_warning_started_at TEXT,
    official_start_delta_minutes INTEGER,
    valid_until TEXT,
    body_text TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    source_encoding TEXT NOT NULL,
    is_correction INTEGER NOT NULL CHECK (is_correction IN (0, 1)),
    parse_warnings_json TEXT NOT NULL
);

CREATE INDEX warning_series_started_at_idx ON warning_series(started_at);
CREATE INDEX warning_series_bulletin_status_idx ON warning_series(weather_bulletin_status);
CREATE INDEX bulletin_events_series_idx ON bulletin_events(warning_series_id, event_at);

CREATE TABLE corroborating_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulletin_event_source_url TEXT NOT NULL REFERENCES bulletin_events(source_url),
    source_url TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    report_at TEXT NOT NULL,
    observation TEXT NOT NULL,
    finding TEXT NOT NULL
);

CREATE VIEW warnings_without_weather_bulletins AS
SELECT * FROM warning_series WHERE has_weather_bulletin = 0;

CREATE VIEW warnings_with_weather_bulletins AS
SELECT * FROM warning_series WHERE has_weather_bulletin = 1;

CREATE TABLE database_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def parse_hko_records() -> list[dict]:
    records = []
    for line_number, line in enumerate(HKO_SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split("\t")
        if not fields or not fields[0].isdigit():
            continue
        sy, sm, sd, sh, smin, ey, em, ed, eh, emin, hours, minutes = map(int, fields[:12])
        start = datetime(sy, sm, sd, sh, smin, tzinfo=HONG_KONG)
        if eh == 24:
            end = datetime(ey, em, ed, tzinfo=HONG_KONG) + timedelta(days=1, minutes=emin)
        else:
            end = datetime(ey, em, ed, eh, emin, tzinfo=HONG_KONG)
        records.append(
            {
                "id": f"WTS-{start:%Y%m%d-%H%M}",
                "start": start,
                "end": end,
                "duration": hours * 60 + minutes,
                "line": line_number,
            }
        )
    return records


def parsed_events() -> list[dict]:
    if not EVENTS_SOURCE.exists():
        return []
    return [json.loads(line) for line in EVENTS_SOURCE.read_text(encoding="utf-8").splitlines()]


def download_statuses() -> dict[str, int | None]:
    latest = {}
    if DOWNLOAD_STATE.exists():
        try:
            latest.update(json.loads(DOWNLOAD_STATE.read_text(encoding="utf-8")).get("dates", {}))
        except json.JSONDecodeError:
            pass
    if not DOWNLOAD_LOG.exists():
        return latest
    for line in DOWNLOAD_LOG.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            latest[row["date"]] = row.get("index_status")
        except (json.JSONDecodeError, KeyError):
            pass
    return latest


def bulletin_status(
    start: datetime, has_events: bool, downloads: dict[str, int | None], english_probes: set[str]
) -> tuple[str, str | None]:
    if has_events:
        return "available", None
    if start.year <= 1997:
        return "not_archived", "政府新聞公報HTML archive抽樣顯示1997年及以前沒有可用頁面"
    index_status = downloads.get(start.date().isoformat())
    if index_status == 404:
        return "not_archived", "該日政府新聞公報索引回傳HTTP 404"
    if index_status == 200:
        if start.date().isoformat() in english_probes:
            return "archive_incomplete", "繁體中文及英文政府新聞公報索引均存在，但兩者都沒有雷暴警告連結"
        return "archive_incomplete", "政府新聞公報索引存在，但沒有可配對的雷暴警告天氣稿"
    return "not_downloaded", "該日尚未成功檢查政府新聞公報索引"


def interval_distance_minutes(event_at: datetime, record: dict) -> int:
    if record["start"] <= event_at <= record["end"]:
        return 0
    boundary = record["start"] if event_at < record["start"] else record["end"]
    return int(abs((event_at - boundary).total_seconds()) // 60)


def terminal_details(group: list[dict], official_end: datetime) -> tuple[str, int, str | None, str | None]:
    ordered = sorted(group, key=lambda row: (row["event_at"], row["bulletin_id"]))
    cancellations = [row for row in ordered if row["event_type"] == "cancelled"]
    terminal_event = cancellations[-1] if cancellations else None
    cutoff = datetime.fromisoformat(terminal_event["event_at"]) if terminal_event else official_end
    scheduled_values = [
        datetime.fromisoformat(row["valid_until"])
        for row in ordered
        if row["valid_until"] and datetime.fromisoformat(row["event_at"]) <= cutoff
    ]
    scheduled = scheduled_values[-1] if scheduled_values else None
    if terminal_event and scheduled:
        terminal_type = "cancelled_early" if official_end < scheduled else "expired"
    elif terminal_event:
        terminal_type = "unknown"
    elif scheduled and official_end == scheduled:
        terminal_type = "expired"
    elif scheduled and official_end < scheduled:
        terminal_type = "cancelled_early"
    else:
        terminal_type = "unknown"
    return (
        terminal_type,
        int(terminal_event is None),
        scheduled.isoformat() if scheduled else None,
        terminal_event["source_url"] if terminal_event else None,
    )


def group_events(events: list[dict], official: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    grouped: dict[str, list[dict]] = {}
    unassigned = []
    by_start = {row["start"].isoformat(): row for row in official}
    starts = [row["start"] for row in official]
    for event in events:
        event_at = datetime.fromisoformat(event["event_at"])
        reported_start = event["warning_started_at"]
        if reported_start and reported_start in by_start:
            owner = by_start[reported_start]
            grouped.setdefault(owner["start"].isoformat(), []).append(event)
            continue
        position = bisect_right(starts, event_at)
        nearby_rows = official[max(0, position - 2) : min(len(official), position + 2)]
        candidates = [row for row in nearby_rows if row["start"] <= event_at <= row["end"]]
        if not candidates:
            nearby = sorted(nearby_rows, key=lambda row: interval_distance_minutes(event_at, row))
            if nearby and interval_distance_minutes(event_at, nearby[0]) <= 15:
                candidates = [nearby[0]]
        if not candidates:
            unassigned.append(event)
            continue
        if event["event_type"] == "cancelled":
            owner = min(candidates, key=lambda row: row["start"])
        else:
            owner = max(candidates, key=lambda row: row["start"])
        grouped.setdefault(owner["start"].isoformat(), []).append(event)
    return grouped, unassigned


def main() -> int:
    official = parse_hko_records()
    all_events = parsed_events()
    grouped, unassigned = group_events(all_events, official)
    downloads = download_statuses()
    evidence_state = json.loads(REPRODUCIBILITY_STATE.read_text(encoding="utf-8")) if REPRODUCIBILITY_STATE.exists() else {}
    probe_payload = (
        json.loads(ENGLISH_PROBE_MANIFEST.read_text(encoding="utf-8"))
        if ENGLISH_PROBE_MANIFEST.exists() else evidence_state.get("english_index_probes", {})
    )
    english_probes = {row["date"] for row in probe_payload.get("probes", [])}
    if DATABASE.exists():
        DATABASE.unlink()
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.executescript(SCHEMA)

    for record in official:
        start, end = record["start"], record["end"]
        group = grouped.get(start.isoformat(), [])
        status, note = bulletin_status(start, bool(group), downloads, english_probes)
        terminal_type, terminal_inferred, scheduled_until, terminal_source = terminal_details(group, end)
        connection.execute(
            """INSERT INTO warning_series VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                record["id"], start.isoformat(), end.isoformat(), record["duration"], record["duration"],
                start.strftime("%z"), end.strftime("%z"),
                int(start.date() != end.date()),
                int((start.year, start.month) != (end.year, end.month)),
                int(start.year != end.year), terminal_type, terminal_inferred, scheduled_until,
                terminal_source, int(bool(group)), status, note,
                "https://www.weather.gov.hk/dps/wxinfo/climat/warndb/thunder.dat",
                "data/raw/weather-gov-hk/warndb/thunder.dat",
            ),
        )
        for event in sorted(group, key=lambda row: row["event_at"]):
            connection.execute(
                """INSERT INTO bulletin_events (
                    warning_series_id, assignment_status, assignment_note,
                    bulletin_id, bulletin_number, event_type, event_at,
                    bulletin_at, reported_warning_started_at, official_start_delta_minutes,
                    valid_until, body_text, source_url, source_file,
                    source_encoding, is_correction, parse_warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["id"], "matched", None,
                    event["bulletin_id"], event["bulletin_number"], event["event_type"],
                    event["event_at"], event["bulletin_at"], event["warning_started_at"],
                    int((datetime.fromisoformat(event["warning_started_at"]) - start).total_seconds() // 60)
                    if event["warning_started_at"] else None,
                    event["valid_until"], event["body_text"],
                    event["source_url"], event["source_file"], event["source_encoding"],
                    int(event.get("is_correction", False)),
                    json.dumps(event["parse_warnings"], ensure_ascii=False),
                ),
            )

    for event in unassigned:
        connection.execute(
            """INSERT INTO bulletin_events (
                warning_series_id, assignment_status, assignment_note,
                bulletin_id, bulletin_number, event_type, event_at, bulletin_at,
                reported_warning_started_at, official_start_delta_minutes, valid_until,
                body_text, source_url, source_file, source_encoding, is_correction,
                parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                None, "unmatched", "天氣稿有雷暴警告事件，但天文台官方資料庫沒有可配對系列",
                event["bulletin_id"], event["bulletin_number"], event["event_type"],
                event["event_at"], event["bulletin_at"], event["warning_started_at"], None,
                event["valid_until"], event["body_text"], event["source_url"],
                event["source_file"], event["source_encoding"],
                int(event.get("is_correction", False)),
                json.dumps(event["parse_warnings"], ensure_ascii=False),
            ),
        )

    corroborating_count = 0
    raw_corroborating = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CORROBORATING_MANIFESTS.glob("**/manifest.json"))
    ]
    corroborating_manifests = raw_corroborating or evidence_state.get("corroborating_manifests", [])
    for manifest in corroborating_manifests:
        if "corroborates_event_source_url" not in manifest:
            continue
        event_url = manifest["corroborates_event_source_url"]
        for source in manifest["sources"]:
            connection.execute(
                """INSERT INTO corroborating_sources (
                    bulletin_event_source_url, source_url, source_file, sha256,
                    report_at, observation, finding
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_url, source["source_url"], source["source_file"], source["sha256"],
                    source["report_at"], source["observation"], manifest["finding"],
                ),
            )
            corroborating_count += 1
        connection.execute(
            """UPDATE bulletin_events SET assignment_note = ? WHERE source_url = ?""",
            (manifest["finding"], event_url),
        )

    metadata = {
        "schema_version": "1",
        "created_at": datetime.now(HONG_KONG).isoformat(),
        "official_warning_series": str(len(official)),
        "parsed_bulletin_files": str(len(all_events)),
        "unassigned_bulletin_files": str(len(unassigned)),
        "corroborating_sources": str(corroborating_count),
        "timezone": "Asia/Hong_Kong",
    }
    connection.executemany("INSERT INTO database_metadata VALUES (?, ?)", metadata.items())
    connection.commit()
    counts = connection.execute(
        """SELECT weather_bulletin_status, count(*) FROM warning_series
        GROUP BY weather_bulletin_status ORDER BY weather_bulletin_status"""
    ).fetchall()
    event_count = connection.execute("SELECT count(*) FROM bulletin_events").fetchone()[0]
    connection.close()
    print(f"Built {DATABASE.relative_to(ROOT)} with {len(official)} series and {event_count} events")
    print(f"Unassigned events: {len(unassigned)}")
    for status, count in counts:
        print(f"{status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
