import unittest

from kdpniche.models import Book, NicheReport
from kdpniche.scoring import summarise, verdict_for


def make_report(reviews, price=12.99, results=5_000, publisher="Independently published"):
    report = NicheReport(keyword="test niche", results_count=results)
    report.books = [
        Book(asin=f"A{i:09d}", title=f"Book {i}", position=i + 1, price=price,
             rating=4.5, reviews=reviews[i % len(reviews)], publisher=publisher,
             bsr=20_000 + i * 5_000)
        for i in range(20)
    ]
    return summarise(report, volume_score=60)


class ScoringTest(unittest.TestCase):
    def test_low_competition_beats_high_competition(self):
        easy = make_report([5, 12, 30, 8])
        hard = make_report([4200, 9800, 6100, 15000])
        self.assertLess(easy.competition_score, hard.competition_score)
        self.assertGreater(easy.opportunity_score, hard.opportunity_score)

    def test_scores_stay_in_range(self):
        for report in (make_report([0]), make_report([99_000]), make_report([50, 60])):
            for score in (report.demand_score, report.competition_score,
                          report.profit_score, report.opportunity_score):
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

    def test_higher_price_lifts_profit_score(self):
        cheap = make_report([40], price=4.99)
        rich = make_report([40], price=18.99)
        self.assertGreater(rich.profit_score, cheap.profit_score)

    def test_saturation_hurts(self):
        small = make_report([40], results=800)
        huge = make_report([40], results=250_000)
        self.assertGreater(huge.competition_score, small.competition_score)

    def test_traditional_publishers_raise_competition(self):
        indie = make_report([40], publisher="Independently published")
        trad = make_report([40], publisher="Penguin Random House")
        self.assertGreater(trad.competition_score, indie.competition_score)

    def test_empty_report_is_safe(self):
        report = summarise(NicheReport(keyword="nothing"))
        self.assertEqual(report.verdict, "No data")
        self.assertEqual(report.opportunity_score, 0)

    def test_verdict_bands(self):
        self.assertEqual(verdict_for(90), "Goldmine")
        self.assertEqual(verdict_for(65), "Strong")
        self.assertEqual(verdict_for(50), "Decent")
        self.assertEqual(verdict_for(40), "Risky")
        self.assertEqual(verdict_for(10), "Avoid")

    def test_sponsored_books_are_excluded(self):
        report = NicheReport(keyword="k", results_count=1000)
        report.books = [Book(asin="A", title="ad", position=1, sponsored=True, price=9.99, reviews=10),
                        Book(asin="B", title="real", position=2, price=9.99, reviews=10)]
        summarise(report)
        self.assertEqual(report.analysed, 1)


if __name__ == "__main__":
    unittest.main()
