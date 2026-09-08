import unittest

from kdpniche import bsr


class BsrCurveTest(unittest.TestCase):
    def test_monotonic_decreasing(self):
        previous = float("inf")
        for rank in [1, 10, 100, 1_000, 10_000, 100_000, 1_000_000, 4_000_000]:
            sales = bsr.sales_per_day(rank)
            self.assertLess(sales, previous, f"sales should fall as rank {rank} grows")
            previous = sales

    def test_known_anchors(self):
        self.assertAlmostEqual(bsr.sales_per_day(100), 170, delta=1)
        self.assertAlmostEqual(bsr.sales_per_day(10_000, "kindle"), 16, delta=1)

    def test_kindle_outsells_print_at_same_rank(self):
        self.assertGreater(bsr.sales_per_day(5_000, "kindle"), bsr.sales_per_day(5_000, "print"))

    def test_marketplace_scaling(self):
        self.assertLess(bsr.sales_per_day(5_000, "print", "de"),
                        bsr.sales_per_day(5_000, "print", "us"))

    def test_zero_and_none(self):
        self.assertEqual(bsr.sales_per_day(None), 0.0)
        self.assertEqual(bsr.sales_per_day(0), 0.0)

    def test_inverse_roundtrip(self):
        for target in (50, 500, 5_000):
            rank = bsr.bsr_for_sales(target)
            self.assertAlmostEqual(bsr.sales_per_month(rank), target, delta=target * 0.05)


class RoyaltyTest(unittest.TestCase):
    def test_kindle_70_percent_band(self):
        self.assertAlmostEqual(bsr.kindle_royalty(4.99), 4.99 * 0.7 - 0.15, places=2)

    def test_kindle_35_percent_outside_band(self):
        self.assertAlmostEqual(bsr.kindle_royalty(12.99), 12.99 * 0.35, places=2)
        self.assertAlmostEqual(bsr.kindle_royalty(1.99), 1.99 * 0.35, places=2)

    def test_paperback_royalty_after_print_cost(self):
        value = bsr.paperback_royalty(9.99, pages=120)
        self.assertGreater(value, 0)
        self.assertLess(value, 9.99 * 0.6)

    def test_paperback_royalty_never_negative(self):
        self.assertEqual(bsr.paperback_royalty(2.99, pages=800), 0.0)


if __name__ == "__main__":
    unittest.main()
