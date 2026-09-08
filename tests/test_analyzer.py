import os
import tempfile
import unittest

from kdpniche.analyzer import NicheFinder, search_url
from kdpniche.config import Settings
from kdpniche.http_client import NetworkError

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def temp_settings(**kwargs):
    settings = Settings(**kwargs)
    settings.data_dir = tempfile.mkdtemp(prefix="kdpniche-test-")
    settings.request_delay = 0
    return settings


class SearchUrlTest(unittest.TestCase):
    def test_builds_marketplace_specific_url(self):
        url = search_url("dream journal", "uk", "kindle")
        self.assertTrue(url.startswith("https://www.amazon.co.uk/s?"))
        self.assertIn("k=dream+journal", url)
        self.assertIn("i=digital-text", url)

    def test_pagination(self):
        self.assertIn("page=3", search_url("x", "us", "print", page=3))


class AnalyseKeywordTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(FIXTURES, "search_sample.html"), encoding="utf-8") as handle:
            self.html = handle.read()

    def test_parses_and_scores_a_live_page(self):
        finder = NicheFinder(temp_settings())
        finder._get = lambda url, kind, ttl=None: self.html
        report = finder.analyse_keyword("sudoku puzzle book", volume_score=70)
        self.assertEqual(report.results_count, 4000)
        self.assertEqual(report.analysed, 2)          # the sponsored tile is excluded
        self.assertGreater(report.opportunity_score, 0)
        self.assertGreater(report.est_royalty_month, 0)
        self.assertEqual(report.source, "amazon")

    def test_falls_back_to_demo_when_amazon_is_unreachable(self):
        finder = NicheFinder(temp_settings())

        def boom(url, kind, ttl=None):
            raise NetworkError("blocked")

        finder._get = boom
        report = finder.analyse_keyword("sudoku puzzle book")
        self.assertEqual(report.source, "demo")
        self.assertTrue(report.books)
        self.assertIn("blocked", report.error)

    def test_fallback_can_be_disabled(self):
        settings = temp_settings()
        settings.allow_demo_fallback = False
        finder = NicheFinder(settings)

        def boom(url, kind, ttl=None):
            raise NetworkError("blocked")

        finder._get = boom
        report = finder.analyse_keyword("x")
        self.assertEqual(report.source, "amazon")
        self.assertTrue(report.error)
        self.assertEqual(report.books, [])


class OfflineRunTest(unittest.TestCase):
    def test_full_run_offline(self):
        settings = temp_settings(offline=True)
        run = NicheFinder(settings).find_niches("journal", limit=8)
        self.assertTrue(run.niches)
        self.assertEqual(run.source, "demo")
        scores = [n.opportunity_score for n in run.niches]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_results_are_deterministic(self):
        settings = temp_settings(offline=True)
        first = NicheFinder(settings).find_niches("coloring", limit=5)
        second = NicheFinder(settings).find_niches("coloring", limit=5)
        self.assertEqual([n.keyword for n in first.niches], [n.keyword for n in second.niches])
        self.assertEqual([n.opportunity_score for n in first.niches],
                         [n.opportunity_score for n in second.niches])


class CacheTest(unittest.TestCase):
    def test_second_call_hits_the_cache(self):
        finder = NicheFinder(temp_settings())
        calls = {"n": 0}

        def counted(url, language="en-US"):
            calls["n"] += 1
            return "<html>ok</html>"

        finder.client.get = counted
        finder._get("https://example.com/x", "search")
        finder._get("https://example.com/x", "search")
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
