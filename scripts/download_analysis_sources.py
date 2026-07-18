#!/usr/bin/env python3
"""Archive official datasets used by the analysis dashboard."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
HKT = ZoneInfo("Asia/Hong_Kong")
SOURCES = {
    "rstorm.dat": "https://www.weather.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat",
    "tc.dat": "https://www.weather.gov.hk/dps/wxinfo/climat/warndb/tc.dat",
    "thunderstorm-days.json": "https://www.hko.gov.hk/cis/statistic/tsday_statistic_e_html.json",
}


def main() -> int:
    target_dir = ROOT / "data/raw/weather-gov-hk/analysis"
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        request = Request(url, headers={"User-Agent": "hko-thunderstorm-archive/0.1"})
        with urlopen(request, timeout=30) as response:
            body = response.read()
            status = response.status
        path = target_dir / filename
        path.write_bytes(body)
        path.with_suffix(path.suffix + ".metadata.json").write_text(json.dumps({
            "source_url": url,
            "fetched_at": datetime.now(HKT).isoformat(),
            "status": status,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Archived {filename}: {len(body)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
