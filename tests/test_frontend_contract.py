import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTest(unittest.TestCase):
    def text(self, name):
        return (ROOT / "web" / name).read_text(encoding="utf-8")

    def test_hong_kong_timezone_and_deep_links(self):
        app = self.text("app.js")
        self.assertIn("Asia/Hong_Kong", app)
        self.assertIn("/warnings/", app)
        self.assertNotIn("state={year:'2026'", app)
        self.assertIn("香港夏令時間（UTC+9）", app)
        self.assertIn("香港標準時間（UTC+8）", app)

    def test_analysis_ranges_are_data_driven(self):
        analysis = self.text("analysis.js")
        self.assertNotIn("tMax=2026", analysis)
        self.assertNotIn("length:29", analysis)
        self.assertIn("analysisEndYear", analysis)

    def test_filter_exposes_not_downloaded_state(self):
        self.assertIn('value="not_downloaded"', self.text("index.html"))
        self.assertIn('id="sortFilter"', self.text("index.html"))

    def test_refreshed_theme_is_loaded_on_every_page(self):
        for page in ("index.html", "evolution.html", "analysis.html"):
            self.assertIn('/theme-refresh.css', self.text(page))
            self.assertIn('/theme.js', self.text(page))
            self.assertIn('content="#080713"', self.text(page))
        theme = self.text("theme-refresh.css")
        for colour in ("--violet", "--orange", "--cyan"):
            self.assertIn(colour, theme)
        picker = self.text("theme.js")
        self.assertIn("prefers-color-scheme", picker)
        self.assertIn("localStorage", picker)
        self.assertIn("['midnight','深色']", picker)
        self.assertIn("['paper','淺色']", picker)
        self.assertNotIn("雷達綠光", picker)
        self.assertNotIn("跟隨系統", picker)

    def test_analysis_omits_low_value_cross_warning_panel(self):
        page = self.text("analysis.html")
        script = self.text("analysis.js")
        self.assertNotIn("同時生效嘅其他警告", page)
        self.assertNotIn("overlapStats", page)
        self.assertIn("有天氣稿可分析", script)

    def test_static_adapter_supports_search_sort_and_details(self):
        adapter = self.text("static-api.js")
        self.assertIn("series-index.json", adapter)
        self.assertIn("cancellation_margin_desc", adapter)
        self.assertIn("dataRoot", adapter)
        self.assertIn("THUNDER_STATIC", self.text("app.js"))

    def test_archive_status_baseline_is_substantial(self):
        payload = json.loads((ROOT / "data/processed/archive-date-status.json").read_text(encoding="utf-8"))
        self.assertGreater(len(payload["dates"]), 2000)


if __name__ == "__main__":
    unittest.main()
