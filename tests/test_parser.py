import os
import unittest

from kdpniche.parser import classify_publisher, parse_product, parse_search

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


class SearchParserTest(unittest.TestCase):
    def setUp(self):
        self.books, self.count = parse_search(load("search_sample.html"))

    def test_finds_every_result(self):
        self.assertEqual(len(self.books), 3)

    def test_reads_the_total_result_count(self):
        self.assertEqual(self.count, 4000)

    def test_titles_and_asins(self):
        self.assertEqual(self.books[0].asin, "1234567890")
        self.assertIn("Sudoku Puzzle Book for Adults", self.books[0].title)

    def test_prices_ratings_reviews(self):
        self.assertEqual(self.books[0].price, 8.99)
        self.assertEqual(self.books[0].rating, 4.6)
        self.assertEqual(self.books[0].reviews, 1254)
        self.assertEqual(self.books[1].reviews, 37)

    def test_format_and_author(self):
        self.assertEqual(self.books[1].fmt, "Paperback")
        self.assertEqual(self.books[2].fmt, "Kindle Edition")
        self.assertEqual(self.books[0].author, "Ava Bennett")

    def test_sponsored_flag(self):
        self.assertTrue(self.books[0].sponsored)
        self.assertFalse(self.books[1].sponsored)

    def test_positions_are_sequential(self):
        self.assertEqual([b.position for b in self.books], [1, 2, 3])

    def test_garbage_html_is_safe(self):
        books, count = parse_search("<html><body>nope</body></html>")
        self.assertEqual(books, [])
        self.assertIsNone(count)


class ProductParserTest(unittest.TestCase):
    def setUp(self):
        self.info = parse_product(load("product_sample.html"))

    def test_bsr_is_the_widest_rank(self):
        self.assertEqual(self.info["bsr"], 12345)
        self.assertIn("Books", self.info["bsr_category"])

    def test_publication_date(self):
        self.assertEqual(self.info["published"], "2023-03-04")

    def test_pages_and_publisher(self):
        self.assertEqual(self.info["pages"], 124)
        self.assertIn("Independently published", self.info["publisher"])


class PublisherClassifierTest(unittest.TestCase):
    def test_indie(self):
        self.assertEqual(classify_publisher("Independently published"), "indie")
        self.assertEqual(classify_publisher("CreateSpace Independent Publishing"), "indie")

    def test_traditional(self):
        self.assertEqual(classify_publisher("Penguin Random House"), "traditional")

    def test_unknown(self):
        self.assertEqual(classify_publisher(""), "unknown")

    def test_author_as_publisher_is_indie(self):
        self.assertEqual(classify_publisher("Ava Bennett", "Ava Bennett"), "indie")


if __name__ == "__main__":
    unittest.main()
