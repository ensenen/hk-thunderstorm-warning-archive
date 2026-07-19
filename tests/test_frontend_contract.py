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
        self.assertIn("month:'long',day:'numeric'", app)
        self.assertIn("天氣稿發出：<time", app)
        self.assertIn("新有效時間：", app)
        self.assertIn('class="event-heading"', app)
        self.assertIn('<time datetime="${e.event_at}">', app)

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
        for element_id in ("scopeBar", "scopeToggle", "yearSelection", "yearInsight", "mobileFilterToggle", "filterDrawer", "mobileCloseDialog"):
            self.assertIn(f'id="{element_id}"', page)
        self.assertLess(page.index('class="archive-section"'), page.index('class="year-section panel"'))
        self.assertIn("LOOK UP A WARNING", page)
        self.assertIn('class="series-columns"', page)
        self.assertIn("日期、時間及時長", page)
        self.assertIn("series-overview", app)
        self.assertIn("series-id", app)
        self.assertIn("較 ${previous.year} 年", app)
        self.assertIn("目前查看：", app)
        self.assertIn("scrollYearToActive", app)
        self.assertIn("組有天氣稿", app)
        self.assertIn("data-clear-filter", app)
        self.assertIn("clearFilter", app)
        self.assertIn("setFilterDrawer", app)
        self.assertIn("applyVisibleMobileFilter", app)
        self.assertIn("requestSubmit", app)
        self.assertIn('>其他篩選 <span id="mobileFilterCount"', page)
        self.assertIn(".filter-drawer>.terminal-label,.filter-drawer>.status-label,.filter-drawer>.filter-apply{grid-area:auto}", theme)
        self.assertIn(".year-section .section-heading>p{display:block", theme)
        self.assertIn(".mobile-detail-toolbar{position:sticky", theme)
        self.assertIn("max-height:100dvh;padding:0 20px 28px", theme)
        self.assertIn("margin:0 -20px 22px", theme)
        self.assertIn("background:var(--surface);box-shadow:", theme)
        self.assertIn(".detail-dialog .detail-header>.eyebrow{display:none}", theme)
        self.assertIn("$('#mobileDetailTitle').textContent=s.id", app)
        self.assertIn("都盡可能還原成時間線", page)
        self.assertIn('aria-label="第一頁"', app)
        self.assertIn('aria-label="最後一頁，第 ${d.pages} 頁"', app)
        self.assertIn('aria-current="page"', app)
        self.assertIn('html[data-mode="light"] .pagination button.active', theme)

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
        self.assertIn('.detail-dialog .event{grid-template-columns:18px minmax(0,1fr)', theme)
        self.assertIn('.event-heading{display:flex', theme)
        self.assertIn('.event-timing{display:flex', theme)
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
        self.assertIn('class="analysis-guide"', page)
        for section_id in ("when", "changes", "where", "quality", "audit"):
            self.assertIn(f'id="{section_id}" class="analysis-section"', page)
        self.assertIn("section-takeaway", page)
        self.assertNotIn("同時生效嘅其他警告", page)
        self.assertNotIn("overlapStats", page)
        self.assertNotIn("警告系列與觀測雷暴日", page)
        self.assertNotIn("CLIMATE CONTEXT", page)
        self.assertNotIn("renderClimate", script)
        self.assertIn("有天氣稿可分析", script)
        self.assertIn("天氣稿刊登時間", script)
        self.assertIn("warningHref(id)", script)
        self.assertIn("排名</b><strong>警告系列</strong><span>事件數</span><span>延長次數", script)
        self.assertIn("排名</b><strong>警告系列</strong><span>開始日期</span><span>提早取消幅度", script)
        self.assertIn("#${i+1}", script)
        self.assertIn("陣風上限</strong><span>天氣稿日期</span><span>警告系列", script)
        self.assertIn("代表模板</span><span>首次至最後出現年份</span><strong>稿件數", script)
        for legend in ("顏色深淺代表警告組數", "年度細柱由左至右排列", "每條直柱代表一年"):
            self.assertIn(legend, page)
        self.assertIn('id="coverageAxis"', page)
        self.assertIn("data-tip", script)

    def test_static_adapter_supports_search_sort_and_details(self):
        adapter = self.text("static-api.js")
        self.assertIn("series-index.json", adapter)
        self.assertIn("cancellation_margin_desc", adapter)
        self.assertIn("dataRoot", adapter)
        self.assertIn("THUNDER_STATIC", self.text("app.js"))
        builder = (ROOT / "scripts" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertIn("'href=\"/\"', 'href=\"index.html\"'", builder)
        self.assertIn("hashlib.sha256", builder)
        self.assertIn("?v={version}", builder)

    def test_page_scripts_only_target_existing_elements(self):
        import re

        for page_name, script_name in (("index.html", "app.js"), ("evolution.html", "evolution.js"), ("analysis.html", "analysis.js")):
            page_ids = set(re.findall(r'id="([^"]+)"', self.text(page_name)))
            script_ids = set(re.findall(r"\$\('#([^']+)'\)", self.text(script_name)))
            self.assertEqual(script_ids - page_ids, set(), f"{script_name} targets missing IDs")

    def test_light_palette_and_hover_data_are_readable(self):
        import re

        theme = self.text("theme-refresh.css")
        block = re.search(r'html\[data-theme="paper"\]\{([^}]+)\}', theme).group(1)
        colours = dict(re.findall(r'--([\w-]+):(#[0-9a-fA-F]{6})', block))

        def luminance(value):
            channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return sum(weight * channel for weight, channel in zip((0.2126, 0.7152, 0.0722), linear))

        def contrast(first, second):
            high, low = sorted((luminance(first), luminance(second)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        for foreground in ("text", "muted", "lime", "cyan", "orange"):
            self.assertGreaterEqual(contrast(colours[foreground], colours["surface"]), 4.5, foreground)
        for selector in (".filter-chip", ".badge.available", ".badge.expired", ".badge.historic-time"):
            self.assertIn(f'html[data-mode="light"] {selector}', theme)
        self.assertIn('html[data-mode="light"] .brand-mark', theme)
        self.assertIn('html[data-mode="light"] .filters input::placeholder', theme)
        self.assertIn(".data-tip-popover", theme)
        self.assertIn("background:var(--text);color:var(--surface)", theme)
        self.assertIn("installDataTips", self.text("theme.js"))
        self.assertIn("data-tip", self.text("evolution.js"))

    def test_archive_status_baseline_is_substantial(self):
        payload = json.loads((ROOT / "data/processed/archive-date-status.json").read_text(encoding="utf-8"))
        self.assertGreater(len(payload["dates"]), 2000)


if __name__ == "__main__":
    unittest.main()
