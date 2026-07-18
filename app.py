#!/usr/bin/env python3
"""Serve the interactive thunderstorm warning archive using only the standard library."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from analysis import build_analysis


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DATABASE = ROOT / "data/thunderstorm-warnings.sqlite3"
HKO_METADATA = ROOT / "data/raw/weather-gov-hk/warndb/thunder.metadata.json"
ANALYSIS_EXPORT = ROOT / "data/processed/analysis.json"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def one(query: str, parameters=()) -> dict:
    with connect() as connection:
        row = connection.execute(query, parameters).fetchone()
    return dict(row) if row else {}


def all_rows(query: str, parameters=()) -> list[dict]:
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, parameters)]


def api_meta() -> dict:
    years = all_rows(
        """SELECT substr(started_at, 1, 4) AS year, count(*) AS count
        FROM warning_series GROUP BY year ORDER BY year DESC"""
    )
    source_metadata = json.loads(HKO_METADATA.read_text(encoding="utf-8")) if HKO_METADATA.exists() else {}
    database_metadata = {row["key"]: row["value"] for row in all_rows("SELECT key, value FROM database_metadata")}
    latest = one("SELECT max(started_at) AS latest_started_at, min(started_at) AS earliest_started_at FROM warning_series")
    return {
        "years": years,
        "terminal_types": ["expired", "cancelled_early", "unknown"],
        "bulletin_statuses": ["available", "not_archived", "not_downloaded", "archive_incomplete"],
        "source_fetched_at": source_metadata.get("fetched_at"),
        "source_sha256": source_metadata.get("sha256"),
        "database_created_at": database_metadata.get("created_at"),
        **latest,
    }


def api_stats(year: str | None = None) -> dict:
    clause = "WHERE substr(started_at, 1, 4) = ?" if year else ""
    parameters = (year,) if year else ()
    stats = one(
        f"""SELECT count(*) AS total_series,
        sum(CASE WHEN terminal_type='cancelled_early' THEN 1 ELSE 0 END) AS cancelled_early,
        sum(CASE WHEN terminal_type='expired' THEN 1 ELSE 0 END) AS expired,
        sum(CASE WHEN terminal_type='unknown' THEN 1 ELSE 0 END) AS unknown_terminal,
        sum(CASE WHEN weather_bulletin_status='available' THEN 1 ELSE 0 END) AS with_bulletins,
        round(avg(duration_minutes), 1) AS average_duration_minutes,
        max(duration_minutes) AS longest_duration_minutes
        FROM warning_series {clause}""",
        parameters,
    )
    event_clause = (
        "WHERE warning_series_id IN (SELECT id FROM warning_series WHERE substr(started_at,1,4)=?)"
        if year else ""
    )
    events = one(f"SELECT count(*) AS total_events FROM bulletin_events {event_clause}", parameters)
    stats.update(events)
    stats["year"] = year
    return stats


def api_yearly() -> list[dict]:
    return all_rows(
        """SELECT substr(started_at,1,4) AS year, count(*) AS total,
        sum(CASE WHEN terminal_type='cancelled_early' THEN 1 ELSE 0 END) AS cancelled_early,
        sum(CASE WHEN weather_bulletin_status='available' THEN 1 ELSE 0 END) AS available
        FROM warning_series GROUP BY year ORDER BY year"""
    )


def api_series(parameters: dict[str, list[str]]) -> dict:
    where = []
    values: list[object] = []
    year = parameters.get("year", [""])[0]
    terminal = parameters.get("terminal", [""])[0]
    status = parameters.get("status", [""])[0]
    query = parameters.get("q", [""])[0].strip()
    sort = parameters.get("sort", ["newest"])[0]
    order_by = {
        "newest": "ws.started_at DESC",
        "oldest": "ws.started_at ASC",
        "duration_desc": "ws.duration_minutes DESC, ws.started_at DESC",
        "duration_asc": "ws.duration_minutes ASC, ws.started_at DESC",
        "events_desc": "event_count DESC, ws.started_at DESC",
        "cancellation_margin_desc": "CASE WHEN ws.terminal_type='cancelled_early' AND ws.scheduled_until_at_end IS NOT NULL THEN julianday(ws.scheduled_until_at_end)-julianday(ws.ended_at) ELSE -1 END DESC, ws.started_at DESC",
    }.get(sort, "ws.started_at DESC")
    page = max(1, int(parameters.get("page", ["1"])[0]))
    page_size = min(50, max(5, int(parameters.get("page_size", ["20"])[0])))
    if year:
        where.append("substr(ws.started_at,1,4)=?")
        values.append(year)
    if terminal:
        where.append("ws.terminal_type=?")
        values.append(terminal)
    if status:
        where.append("ws.weather_bulletin_status=?")
        values.append(status)
    if query:
        where.append("(ws.id LIKE ? OR EXISTS (SELECT 1 FROM bulletin_events search WHERE search.warning_series_id=ws.id AND search.body_text LIKE ?))")
        values.extend([f"%{query}%", f"%{query}%"])
    clause = "WHERE " + " AND ".join(where) if where else ""
    with connect() as connection:
        total = connection.execute(f"SELECT count(*) FROM warning_series ws {clause}", values).fetchone()[0]
        rows = [
            dict(row)
            for row in connection.execute(
                f"""SELECT ws.*,
                (SELECT count(*) FROM bulletin_events be WHERE be.warning_series_id=ws.id) AS event_count,
                (SELECT body_text FROM bulletin_events be WHERE be.warning_series_id=ws.id ORDER BY event_at LIMIT 1) AS first_body
                FROM warning_series ws {clause}
                ORDER BY {order_by} LIMIT ? OFFSET ?""",
                [*values, page_size, (page - 1) * page_size],
            )
        ]
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size), "sort": sort if sort in {"newest", "oldest", "duration_desc", "duration_asc", "events_desc", "cancellation_margin_desc"} else "newest"}


def api_series_detail(series_id: str) -> dict | None:
    with connect() as connection:
        series = connection.execute("SELECT * FROM warning_series WHERE id=?", (series_id,)).fetchone()
        if not series:
            return None
        events = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM bulletin_events WHERE warning_series_id=? ORDER BY event_at,id", (series_id,)
            )
        ]
    for event in events:
        event["parse_warnings"] = json.loads(event.pop("parse_warnings_json"))
    result = dict(series)
    result["events"] = events
    return result


def api_anomalies() -> dict:
    return {
        "unmatched_events": all_rows("SELECT * FROM bulletin_events WHERE assignment_status='unmatched' ORDER BY event_at DESC"),
        "archive_incomplete": all_rows("SELECT * FROM warning_series WHERE weather_bulletin_status='archive_incomplete' ORDER BY started_at DESC"),
        "corroborating_sources": all_rows("SELECT * FROM corroborating_sources ORDER BY report_at"),
    }


def api_analysis() -> dict:
    source_paths = [DATABASE, ROOT / "data/raw/weather-gov-hk/analysis/rstorm.dat", ROOT / "data/raw/weather-gov-hk/analysis/tc.dat", ROOT / "data/raw/weather-gov-hk/analysis/thunderstorm-days.json"]
    if ANALYSIS_EXPORT.exists():
        # A published static bundle may intentionally contain only the derived
        # analysis.  Prefer it when the much larger raw source archive is absent.
        if not all(path.exists() for path in source_paths):
            return json.loads(ANALYSIS_EXPORT.read_text(encoding="utf-8"))
        if ANALYSIS_EXPORT.stat().st_mtime_ns >= max(path.stat().st_mtime_ns for path in source_paths):
            return json.loads(ANALYSIS_EXPORT.read_text(encoding="utf-8"))
    return build_analysis()


EVOLUTION_TERMS = [
    {"id": "relative-duration", "term": "後之…小時內", "pattern": "%後之%小時內%", "category": "有效時間", "description": "早期稿件常以發出時間加一段相對時長表達警告期。"},
    {"id": "valid-until", "term": "有效時間至", "pattern": "%有效時間至%", "category": "有效時間", "description": "直接列出警告有效至某個鐘點，讀者毋須自行換算。"},
    {"id": "extended-until", "term": "有效時間延長至", "pattern": "%有效時間延長至%", "category": "警告演變", "description": "延長稿重述原來發出時間，並交代新的有效時間。"},
    {"id": "precautions", "term": "請採取以下預防措施", "pattern": "%請採取以下預防措施%", "category": "安全提示", "description": "警告由簡短現象描述，演變成附帶結構化安全指引。"},
    {"id": "local-thunderstorm", "term": "局部地區雷暴", "pattern": "%局部地區雷暴%", "category": "影響範圍", "description": "以較直接的用字表示雷暴影響局部地區。"},
    {"id": "violent-gusts", "term": "猛烈陣風", "pattern": "%猛烈陣風%", "category": "高影響天氣", "description": "交代雷暴可能伴隨的陣風風速及相關風險。"},
    {"id": "hail", "term": "冰雹", "pattern": "%冰雹%", "category": "高影響天氣", "description": "在個別警告中指出觀測到或可能出現冰雹。"},
    {"id": "waterspout", "term": "水龍捲", "pattern": "%水龍捲%", "category": "高影響天氣", "description": "在罕見個案中加入水龍捲資訊。"},
]


def api_language_evolution() -> dict:
    terms = []
    with connect() as connection:
        for definition in EVOLUTION_TERMS:
            pattern = definition["pattern"]
            yearly = [dict(row) for row in connection.execute(
                """SELECT substr(bulletin_at,1,4) AS year, count(*) AS count
                FROM bulletin_events WHERE body_text LIKE ? GROUP BY year ORDER BY year""",
                (pattern,),
            )]
            samples = []
            for direction in ("ASC", "DESC"):
                row = connection.execute(
                    f"""SELECT bulletin_at, body_text, source_url FROM bulletin_events
                    WHERE body_text LIKE ? ORDER BY bulletin_at {direction}, id {direction} LIMIT 1""",
                    (pattern,),
                ).fetchone()
                if row and (not samples or row["source_url"] != samples[0]["source_url"]):
                    samples.append(dict(row))
            item = {key: value for key, value in definition.items() if key != "pattern"}
            item.update({
                "count": sum(row["count"] for row in yearly),
                "first_year": yearly[0]["year"] if yearly else None,
                "last_year": yearly[-1]["year"] if yearly else None,
                "yearly": yearly,
                "samples": samples,
            })
            terms.append(item)
    return {
        "archive_start_year": 1998,
        "archive_end_year": int(one("SELECT max(substr(bulletin_at,1,4)) AS year FROM bulletin_events")["year"]),
        "source_fetched_at": api_meta().get("source_fetched_at"),
        "method_note": "首次及最後出現年份按本專案現存政府新聞稿計算，不代表天文台歷來首次或最後使用。",
        "terms": terms,
    }


class Handler(SimpleHTTPRequestHandler):
    server_version = "ThunderArchive/1.0"

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                self.handle_api(parsed)
            except (ValueError, sqlite3.Error, FileNotFoundError) as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        path = unquote(parsed.path).lstrip("/") or "index.html"
        target = (WEB_ROOT / path).resolve()
        if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            target = WEB_ROOT / "index.html"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def handle_api(self, parsed):
        path = parsed.path
        params = parse_qs(parsed.query)
        if path == "/api/meta":
            self.send_json(api_meta())
        elif path == "/api/stats":
            self.send_json(api_stats(params.get("year", [None])[0]))
        elif path == "/api/yearly":
            self.send_json(api_yearly())
        elif path == "/api/series":
            self.send_json(api_series(params))
        elif path.startswith("/api/series/"):
            result = api_series_detail(unquote(path.removeprefix("/api/series/")))
            self.send_json(result if result else {"error": "not found"}, HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
        elif path == "/api/anomalies":
            self.send_json(api_anomalies())
        elif path == "/api/language-evolution":
            self.send_json(api_language_evolution())
        elif path == "/api/analysis":
            self.send_json(api_analysis())
        else:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"雷暴警告資料庫正在監聽：http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
