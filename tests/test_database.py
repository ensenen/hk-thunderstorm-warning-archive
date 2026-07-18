import sqlite3
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/thunderstorm-warnings.sqlite3"
HKO_SOURCE = ROOT / "data/raw/weather-gov-hk/warndb/thunder.dat"


class DatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "scripts/build_database.py"], cwd=ROOT, check=True)
        cls.connection = sqlite3.connect(DATABASE)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_all_official_records_are_stored(self):
        count = self.connection.execute("SELECT count(*) FROM warning_series").fetchone()[0]
        official_count = sum(
            1
            for line in HKO_SOURCE.read_text(encoding="utf-8").splitlines()
            if line.split("\t", 1)[0].isdigit()
        )
        self.assertEqual(count, official_count)

    def test_old_records_are_marked_without_bulletins(self):
        row = self.connection.execute(
            """SELECT has_weather_bulletin, weather_bulletin_status
            FROM warning_series WHERE started_at LIKE '1975-04-19T23:00:%'"""
        ).fetchone()
        self.assertEqual(row, (0, "not_archived"))

    def test_source_reference_is_stored(self):
        row = self.connection.execute(
            "SELECT source_url FROM bulletin_events WHERE bulletin_id = 'P2026062700126'"
        ).fetchone()
        self.assertEqual(
            row[0], "https://www.info.gov.hk/gia/wr/202606/27/P2026062700126.htm"
        )


if __name__ == "__main__":
    unittest.main()
