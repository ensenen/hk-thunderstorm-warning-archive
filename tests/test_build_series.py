import importlib.util
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_series", ROOT / "scripts/build_series.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class BuildSeriesTest(unittest.TestCase):
    def event(self, event_type, event_at, start=None, until=None, bulletin_id="x"):
        return {
            "event_type": event_type,
            "event_at": event_at,
            "warning_started_at": start,
            "valid_until": until,
            "bulletin_id": bulletin_id,
            "source_url": f"https://example.test/{bulletin_id}.htm",
        }

    def test_silent_expiry(self):
        records = [self.event("issued", "2026-01-01T10:00:00+08:00", "2026-01-01T10:00:00+08:00", "2026-01-01T12:00:00+08:00")]
        result = MODULE.build(records)[0]
        self.assertEqual(result["terminal_type"], "expired")
        self.assertTrue(result["terminal_inferred"])
        self.assertEqual(result["source_references"][0]["source_url"], "https://example.test/x.htm")

    def test_early_cancellation(self):
        records = [
            self.event("issued", "2026-01-01T10:00:00+08:00", "2026-01-01T10:00:00+08:00", "2026-01-01T12:00:00+08:00"),
            self.event("cancelled", "2026-01-01T11:30:00+08:00", bulletin_id="cancel"),
        ]
        result = MODULE.build(records)[0]
        self.assertEqual(result["terminal_type"], "cancelled_early")
        self.assertFalse(result["terminal_inferred"])


if __name__ == "__main__":
    unittest.main()
