import unittest

from kdpniche.http_client import NetworkError
from kdpniche.keywords import expand, suggest_url


class FakeClient:
    """Stands in for HttpClient: returns canned autocomplete payloads."""

    def __init__(self, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    def get_json(self, url, language="en-US"):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise NetworkError("boom")
        return {"suggestions": [
            {"value": "gratitude journal for women"},
            {"value": "gratitude journal for kids"},
            {"value": "amazon prime books"},          # filtered out
            {"value": "gratitude journal"},
        ]}


class SuggestUrlTest(unittest.TestCase):
    def test_marketplace_id_and_alias(self):
        url = suggest_url("journal", "de", "kindle")
        self.assertIn("mid=A1PA6795UKMFR9", url)
        self.assertIn("alias=digital-text", url)
        self.assertIn("prefix=journal", url)


class ExpandTest(unittest.TestCase):
    def test_returns_ranked_ideas(self):
        ideas, warnings = expand(FakeClient(), "gratitude journal", breadth="narrow", limit=10)
        self.assertEqual(warnings, [])
        keywords = [idea.keyword for idea in ideas]
        self.assertIn("gratitude journal for women", keywords)
        self.assertTrue(all(0 <= idea.volume_score <= 100 for idea in ideas))
        scores = [idea.volume_score for idea in ideas]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_junk_suggestions_are_dropped(self):
        ideas, _ = expand(FakeClient(), "gratitude journal", breadth="narrow")
        self.assertNotIn("amazon prime books", [idea.keyword for idea in ideas])

    def test_seed_is_always_present(self):
        ideas, _ = expand(FakeClient(), "gratitude journal", breadth="narrow", limit=3)
        self.assertIn("gratitude journal", [idea.keyword for idea in ideas])

    def test_network_failure_degrades_gracefully(self):
        ideas, warnings = expand(FakeClient(fail_after=0), "journal", breadth="narrow")
        self.assertTrue(warnings)
        self.assertEqual([idea.keyword for idea in ideas], ["journal"])

    def test_wide_breadth_probes_more_prefixes(self):
        narrow, wide = FakeClient(), FakeClient()
        expand(narrow, "journal", breadth="narrow")
        expand(wide, "journal", breadth="wide")
        self.assertGreater(wide.calls, narrow.calls)


if __name__ == "__main__":
    unittest.main()
