#!/usr/bin/env python3
"""Archive the HKO thunderstorm warning database source file."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.weather.gov.hk/dps/wxinfo/climat/warndb/thunder.dat"
RAW = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"
META = ROOT / "data/raw/weather-gov-hk/warndb/thunder.metadata.json"
HKT = timezone(timedelta(hours=8))


def main() -> int:
    request = Request(URL, headers={"User-Agent": "hko-thunderstorm-archive/0.1"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        status = response.status
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_bytes(body)
    META.write_text(
        json.dumps(
            {
                "source_url": URL,
                "fetched_at": datetime.now(HKT).isoformat(),
                "status": status,
                "content_type": headers.get("content-type"),
                "last_modified": headers.get("last-modified"),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Archived {len(body)} bytes to {RAW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

