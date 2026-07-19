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
        self.assertIn("原文使用「午夜12時」，所屬日期可能有歧義", app)
        self.assertIn("延長稿沒有重述原警告的發出時間", app)
        self.assertIn("原文時間疑有筆誤", app)

    def test_analysis_ranges_are_data_driven(self):
        analysis = self.text("analysis.js")
        self.assertNotIn("tMax=2026", analysis)
        self.assertNotIn("length:29", analysis)
        self.assertIn("analysisEndYear", analysis)

    def test_filter_exposes_not_downloaded_state(self):
        page = self.text("index.html")
        self.assertIn('value="not_downloaded"', page)
        self.assertIn('id="sortFilter"', page)
        self.assertIn('原始天氣稿暫未下載', page)
        self.assertIn('官方 Archive 本身缺漏', page)

    def test_home_scope_annual_chart_and_mobile_filters(self):
        page = self.text("index.html")
        app = self.text("app.js")
        theme = self.text("theme-refresh.css")
        for element_id in ("scopeBar", "scopeToggle", "yearSelection", "mobileFilterToggle", "filterDrawer", "mobileCloseDialog"):
            self.assertIn(f'id="{element_id}"', page)
        self.assertIn("目前查看：", app)
        self.assertIn("scrollYearToActive", app)
        self.assertIn("組有天氣稿", app)
        self.assertIn("data-clear-filter", app)
        self.assertIn("clearFilter", app)
        self.assertIn("setFilterDrawer", app)
        self.assertIn("applyVisibleMobileFilter", app)
        self.assertIn("requestSubmit", app)
        self.assertIn('>更多 <span id="mobileFilterCount"', page)
        self.assertIn(".year-section .section-heading>p{display:block", theme)
        self.assertIn(".mobile-detail-toolbar{position:sticky", theme)
        self.assertIn("都盡可能還原成時間線", page)

    def test_refreshed_theme_is_loaded_on_every_page(self):
        for page in ("index.html", "evolution.html", "analysis.html"):
            self.assertIn('/theme-refresh.css', self.text(page))
            self.assertIn('/theme.js', self.text(page))
            self.assertIn('content="#080713"', self.text(page))
        theme = self.text("theme-refresh.css")
        for colour in ("--violet", "--orange", "--cyan"):
            self.assertIn(colour, theme)
        self.assertIn('html[data-mode="light"] .data-table a', theme)
        self.assertIn('text-underline-offset:3px', theme)
        self.assertIn('background:var(--text);color:var(--surface)', theme)
        self.assertNotIn('color:#171129', theme)
        self.assertIn('.detail-dialog .event-time{grid-column:2;grid-row:1', theme)
        self.assertIn('.detail-dialog .event-content{grid-column:2;grid-row:2', theme)
        self.assertIn('.detail-dialog{width:100%;max-width:none;height:100dvh', theme)
        toggle = self.text("theme.js")
        self.assertIn("prefers-color-scheme", toggle)
        self.assertIn("localStorage", toggle)
        self.assertIn("['midnight','深色']", toggle)
        self.assertIn("['paper','淺色']", toggle)
        self.assertIn("theme-toggle", toggle)
        self.assertNotIn("theme-picker", toggle)
        self.assertNotIn("position:fixed", theme[theme.find(".theme-toggle"):theme.find(".theme-toggle") + 300])
        self.assertNotIn("雷達綠光", toggle)
        self.assertNotIn("跟隨系統", toggle)

    def test_analysis_omits_low_value_cross_warning_panel(self):
        page = self.text("analysis.html")
        script = self.text("analysis.js")
        self.assertNotIn("同時生效嘅其他警告", page)
        self.assertNotIn("overlapStats", page)
        self.assertIn("有天氣稿可分析", script)
        self.assertIn("天氣稿刊登時間", script)
        self.assertIn("warningHref(id)", script)
        self.assertIn("排名</b><strong>警告系列</strong><span>事件數</span><span>延長次數", script)
        self.assertIn("排名</b><strong>警告系列</strong><span>開始日期</span><span>提早取消幅度", script)
        self.assertIn("#${i+1}", script)

    def test_static_adapter_supports_search_sort_and_details(self):
        adapter = self.text("static-api.js")
        self.assertIn("series-index.json", adapter)
        self.assertIn("cancellation_margin_desc", adapter)
        self.assertIn("dataRoot", adapter)
        self.assertIn("THUNDER_STATIC", self.text("app.js"))
        builder = (ROOT / "scripts" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertIn("'href=\"/\"', 'href=\"index.html\"'", builder)

    def test_archive_status_baseline_is_substantial(self):
        payload = json.loads((ROOT / "data/processed/archive-date-status.json").read_text(encoding="utf-8"))
        self.assertGreater(len(payload["dates"]), 2000)


if __name__ == "__main__":
    unittest.main()
