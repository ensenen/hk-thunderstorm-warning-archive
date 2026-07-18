#!/usr/bin/env python3
"""Precompute the analysis payload for static hosting and fast first load."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis import build_analysis  # noqa: E402

OUTPUT = ROOT / "data/processed/analysis.json"


def main() -> int:
    payload = build_analysis()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported analysis payload to {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
