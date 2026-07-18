import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("parse_bulletins", ROOT / "scripts/parse_bulletins.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ParseBulletinsTest(unittest.TestCase):
    def parse(self, day: str, bulletin_id: str):
        year, month, date = day.split("-")
        path = ROOT / "data/raw/info-gov-hk/bulletins" / year / month / date / f"{bulletin_id}.htm"
        return MODULE.parse_file(path)

    def test_issue(self):
        result = self.parse("2026-06-27", "P2026062700126")
        self.assertEqual(result["event_type"], "issued")
        self.assertEqual(result["warning_started_at"], "2026-06-27T05:20:00+08:00")
        self.assertEqual(result["valid_until"], "2026-06-27T07:30:00+08:00")
        self.assertEqual(
            result["source_url"],
            "https://www.info.gov.hk/gia/wr/202606/27/P2026062700126.htm",
        )

    def test_update(self):
        result = self.parse("2026-06-27", "P2026062700149")
        self.assertEqual(result["event_type"], "updated")
        self.assertEqual(result["valid_until"], "2026-06-27T07:30:00+08:00")

    def test_extension(self):
        result = self.parse("2026-06-27", "P2026062700168")
        self.assertEqual(result["event_type"], "extended")
        self.assertEqual(result["bulletin_at"], "2026-06-27T07:00:00+08:00")
        self.assertEqual(result["valid_until"], "2026-06-27T09:30:00+08:00")

    def test_cancellation(self):
        result = self.parse("2026-06-27", "P2026062700211")
        self.assertEqual(result["event_type"], "cancelled")
        self.assertEqual(result["event_at"], "2026-06-27T09:00:00+08:00")

    def test_cross_day_warning_start(self):
        result = self.parse("2026-06-26", "P2026062600021")
        self.assertEqual(result["warning_started_at"], "2026-06-25T21:30:00+08:00")
        self.assertEqual(result["valid_until"], "2026-06-26T03:30:00+08:00")

    def test_big5_source(self):
        result = self.parse("2006-02-28", "P200602280111")
        self.assertIn(result["source_encoding"], {"big5-hkscs", "big5"})

    def test_1998_chinese_numerals_and_duration_wording(self):
        result = self.parse("1998-06-19", "0619033")
        self.assertEqual(result["event_type"], "issued")
        self.assertEqual(result["warning_started_at"], "1998-06-19T07:50:00+08:00")
        self.assertEqual(result["valid_until"], "1998-06-19T09:50:00+08:00")

    def test_1998_chinese_numeral_extension(self):
        result = self.parse("1998-06-19", "0619052")
        self.assertEqual(result["event_type"], "extended")
        self.assertEqual(result["valid_until"], "1998-06-19T11:50:00+08:00")

    def test_noon(self):
        result = self.parse("2001-06-15", "0615116")
        self.assertEqual(result["valid_until"], "2001-06-15T12:00:00+08:00")

    def test_two_character_duration_wording(self):
        result = self.parse("1998-07-04", "0704031")
        self.assertEqual(result["event_type"], "issued")
        self.assertEqual(result["valid_until"], "1998-07-04T08:10:00+08:00")

    def test_valid_until_old_wording(self):
        result = self.parse("2003-05-04", "0504067")
        self.assertEqual(result["event_type"], "updated")
        self.assertEqual(result["valid_until"], "2003-05-04T08:00:00+08:00")

    def test_gust_only_update(self):
        result = self.parse("2019-04-30", "P2019043000467")
        self.assertEqual(result["event_type"], "updated")
        self.assertIsNone(result["warning_started_at"])
        self.assertIsNone(result["valid_until"])

    def test_explicit_date_midnight_is_preserved_and_flagged(self):
        result = self.parse("2001-06-09", "0609001")
        self.assertEqual(result["warning_started_at"], "2001-06-08T00:00:00+08:00")
        self.assertIn("explicit-date midnight 12 is date-boundary ambiguous", result["parse_warnings"])

    def test_issue_published_one_minute_later(self):
        result = self.parse("2026-06-26", "P2026062600629")
        self.assertEqual(result["event_type"], "issued")
        self.assertEqual(result["bulletin_at"], "2026-06-26T14:53:00+08:00")
        self.assertEqual(result["warning_started_at"], "2026-06-26T14:52:00+08:00")


if __name__ == "__main__":
    unittest.main()
