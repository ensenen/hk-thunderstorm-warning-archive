#!/usr/bin/env python3
"""Export the small archive-investigation manifests needed for reproducible builds."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "data/raw/info-gov-hk/english-index-probes/manifest.json"
CORROBORATING = ROOT / "data/raw/info-gov-hk/corroborating"
OUTPUT = ROOT / "data/processed/archive-evidence-state.json"


def main() -> int:
    previous = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    probes = json.loads(PROBES.read_text(encoding="utf-8")) if PROBES.exists() else previous.get("english_index_probes", {})
    manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CORROBORATING.glob("**/manifest.json"))
    ] or previous.get("corroborating_manifests", [])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "generated_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "english_index_probes": probes,
        "corroborating_manifests": manifests,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
