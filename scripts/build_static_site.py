#!/usr/bin/env python3
"""Build a self-contained GitHub Pages version of the interactive archive."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app  # noqa: E402


OUTPUT = ROOT / "dist" / "site"
WEB = ROOT / "web"
DATABASE = ROOT / "data" / "thunderstorm-warnings.sqlite3"


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export_series() -> tuple[int, int]:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    series = [dict(row) for row in connection.execute("SELECT * FROM warning_series ORDER BY started_at")]
    events_by_series: dict[str, list[dict]] = defaultdict(list)
    for row in connection.execute("SELECT * FROM bulletin_events ORDER BY warning_series_id,event_at,id"):
        event = dict(row)
        event["parse_warnings"] = json.loads(event.pop("parse_warnings_json"))
        if event["warning_series_id"]:
            events_by_series[event["warning_series_id"]].append(event)
    connection.close()

    summaries = []
    search_index = {}
    for record in series:
        events = events_by_series.get(record["id"], [])
        detail = {**record, "events": events}
        write_json(OUTPUT / "data" / "series" / f"{record['id']}.json", detail)
        summaries.append({
            **{key: record[key] for key in (
                "id", "started_at", "ended_at", "duration_minutes", "start_utc_offset",
                "end_utc_offset", "crosses_day", "terminal_type", "scheduled_until_at_end",
                "weather_bulletin_status", "weather_bulletin_note",
            )},
            "event_count": len(events),
            "first_body": events[0]["body_text"] if events else None,
        })
        if events:
            search_index[record["id"]] = "\n".join(event["body_text"] for event in events)
    write_json(OUTPUT / "data" / "series-index.json", summaries)
    write_json(OUTPUT / "data" / "search-index.json", search_index)
    return len(series), sum(len(rows) for rows in events_by_series.values())


def make_pages_portable() -> None:
    boot = '<script>window.THUNDER_STATIC=true</script><script src="static-api.js"></script>'
    for path in OUTPUT.glob("*.html"):
        html = path.read_text(encoding="utf-8")
        html = html.replace('href="/', 'href="').replace('src="/', 'src="')
        html = html.replace("</body>", f"{boot}</body>")
        path.write_text(html, encoding="utf-8")
    (OUTPUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUTPUT / "404.html").write_text("""<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>正在開啟警告</title><script>
const match=location.pathname.match(/^(.*)\\/warnings\\/(WTS-\\d{8}-\\d{4})\\/?$/);
if(match)location.replace(`${match[1]}/?q=${encodeURIComponent(match[2])}`);else document.write('<p>找不到頁面。<a href="./">返回雷暴檔案</a></p>');
</script></html>""", encoding="utf-8")


def main() -> int:
    if not DATABASE.exists():
        raise SystemExit("SQLite database is missing; run scripts/build_database.py first")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(WEB, OUTPUT)
    data = OUTPUT / "data"
    write_json(data / "meta.json", app.api_meta())
    write_json(data / "yearly.json", app.api_yearly())
    years = [row["year"] for row in app.api_meta()["years"]]
    write_json(data / "stats.json", {"all": app.api_stats(), "years": {year: app.api_stats(year) for year in years}})
    write_json(data / "analysis.json", app.api_analysis())
    write_json(data / "language-evolution.json", app.api_language_evolution())
    series_count, event_count = export_series()
    make_pages_portable()
    size = sum(path.stat().st_size for path in OUTPUT.rglob("*") if path.is_file())
    print(f"Built {OUTPUT.relative_to(ROOT)}: {series_count} series, {event_count} events, {size / 1024 / 1024:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
