import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("web_app", ROOT / "app.py")
APP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(APP)


class WebApiTest(unittest.TestCase):
    def test_stats(self):
        result = APP.api_stats("2026")
        self.assertGreater(result["total_series"], 0)
        self.assertGreater(result["total_events"], 0)

    def test_filtered_series(self):
        result = APP.api_series({"year": ["2026"], "page": ["1"], "page_size": ["5"]})
        self.assertEqual(len(result["items"]), 5)
        self.assertTrue(all(row["started_at"].startswith("2026") for row in result["items"]))

    def test_series_sorting_is_applied_before_pagination(self):
        longest = APP.api_series({"year": ["2026"], "sort": ["duration_desc"], "page_size": ["5"]})
        self.assertEqual([row["duration_minutes"] for row in longest["items"]], sorted((row["duration_minutes"] for row in longest["items"]), reverse=True))
        busiest = APP.api_series({"year": ["2026"], "sort": ["events_desc"], "page_size": ["5"]})
        self.assertEqual([row["event_count"] for row in busiest["items"]], sorted((row["event_count"] for row in busiest["items"]), reverse=True))

    def test_unknown_sort_falls_back_safely(self):
        result = APP.api_series({"sort": ["not-sql"], "page_size": ["5"]})
        self.assertEqual(result["sort"], "newest")

    def test_series_detail_has_timeline_and_sources(self):
        result = APP.api_series_detail("WTS-20260627-0520")
        self.assertEqual(result["terminal_type"], "cancelled_early")
        self.assertEqual(len(result["events"]), 5)
        self.assertTrue(result["events"][0]["source_url"].startswith("https://www.info.gov.hk/"))

    def test_historic_summer_time_offsets_are_preserved(self):
        result = APP.api_series_detail("WTS-19750419-2300")
        self.assertEqual(result["start_utc_offset"], "+0800")
        self.assertEqual(result["end_utc_offset"], "+0900")
        self.assertEqual(result["duration_minutes"], 360)

    def test_language_evolution_has_years_and_source_samples(self):
        result = APP.api_language_evolution()
        self.assertIsNotNone(result["source_fetched_at"])
        violent_gusts = next(term for term in result["terms"] if term["id"] == "violent-gusts")
        self.assertGreater(violent_gusts["count"], 0)
        self.assertLessEqual(violent_gusts["first_year"], violent_gusts["last_year"])
        self.assertTrue(violent_gusts["samples"][0]["source_url"].startswith("https://www.info.gov.hk/"))

    def test_analysis_includes_internal_and_external_evidence(self):
        result = APP.api_analysis()
        self.assertEqual(result["generated_from"]["series"], APP.api_stats()["total_series"])
        self.assertEqual(len(result["behavior"]["heatmap"]), 12)
        self.assertGreater(result["overlaps"]["rainstorm_records"], 0)
        self.assertGreater(len(result["climate"]["annual"]), 50)
        self.assertEqual(result["extensions"]["analysed_series"] + result["extensions"]["unknown_series"], result["generated_from"]["series"])
        self.assertEqual(len(result["climate"]["pearson_by_period"]), 3)
        violent_gusts = next(row for row in result["hazards"]["terms"] if row["key"] == "violent_gusts")
        self.assertLess(violent_gusts["count"], violent_gusts["bulletin_count"])
        self.assertGreaterEqual(result["overlaps"]["counts"]["rain_any"], result["overlaps"]["counts"]["rain_R"])
        self.assertEqual(
            [row["place"] for row in result["geography"]],
            ["香港", "新界北部", "新界東部", "新界西部", "新界", "香港東部水域", "大嶼山", "香港南部水域及島嶼", "香港島及九龍"],
        )

    def test_reproducibility_state_is_present(self):
        state = ROOT / "data/processed/archive-evidence-state.json"
        self.assertTrue(state.exists())



if __name__ == "__main__":
    unittest.main()
