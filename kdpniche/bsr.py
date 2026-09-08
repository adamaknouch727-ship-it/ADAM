"""Best Sellers Rank -> sales, revenue and KDP royalty estimation.

The curves are piecewise power laws fitted through the rank/sales anchor points
that the KDP community has published for the US store. Sales at the same rank
are much lower in the smaller marketplaces, so every estimate is scaled by the
marketplace factor from ``config.MARKETPLACES``.
"""

from __future__ import annotations

import math

from .config import MARKETPLACES

# (BSR, sales per day) anchors for amazon.com.
PRINT_CURVE: list[tuple[float, float]] = [
    (1, 2500), (5, 1100), (10, 700), (50, 260), (100, 170), (500, 60),
    (1_000, 38), (5_000, 11), (10_000, 6.2), (25_000, 2.9), (50_000, 1.6),
    (100_000, 0.85), (250_000, 0.34), (500_000, 0.17), (1_000_000, 0.075),
    (2_000_000, 0.03), (5_000_000, 0.008),
]

KINDLE_CURVE: list[tuple[float, float]] = [
    (1, 5200), (5, 2400), (10, 1500), (50, 600), (100, 400), (500, 145),
    (1_000, 95), (5_000, 28), (10_000, 16), (25_000, 7.2), (50_000, 3.6),
    (100_000, 1.6), (250_000, 0.55), (500_000, 0.22), (1_000_000, 0.08),
    (2_000_000, 0.03), (5_000_000, 0.006),
]


def _interpolate(curve: list[tuple[float, float]], bsr: float) -> float:
    """Log-log linear interpolation between the anchor points."""
    if bsr <= curve[0][0]:
        return curve[0][1]
    if bsr >= curve[-1][0]:
        # Extend the last segment instead of flat-lining.
        (x1, y1), (x2, y2) = curve[-2], curve[-1]
        slope = (math.log(y2) - math.log(y1)) / (math.log(x2) - math.log(x1))
        return math.exp(math.log(y2) + slope * (math.log(bsr) - math.log(x2)))
    for (x1, y1), (x2, y2) in zip(curve, curve[1:]):
        if x1 <= bsr <= x2:
            slope = (math.log(y2) - math.log(y1)) / (math.log(x2) - math.log(x1))
            return math.exp(math.log(y1) + slope * (math.log(bsr) - math.log(x1)))
    return curve[-1][1]


def sales_per_day(bsr: int | float | None, store: str = "print", marketplace: str = "us") -> float:
    """Estimated units sold per day for a book sitting at ``bsr``."""
    if not bsr or bsr <= 0:
        return 0.0
    curve = KINDLE_CURVE if store == "kindle" else PRINT_CURVE
    factor = MARKETPLACES[marketplace].sales_factor if marketplace in MARKETPLACES else 1.0
    return _interpolate(curve, float(bsr)) * factor


def sales_per_month(bsr: int | float | None, store: str = "print", marketplace: str = "us") -> float:
    return sales_per_day(bsr, store, marketplace) * 30.0


def bsr_for_sales(target_month: float, store: str = "print", marketplace: str = "us") -> int:
    """Inverse lookup: which BSR corresponds to N sales per month?"""
    target_day = max(target_month, 0.001) / 30.0
    lo, hi = 1.0, 5_000_000.0
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if sales_per_day(mid, store, marketplace) > target_day:
            lo = mid
        else:
            hi = mid
    return int(round(math.sqrt(lo * hi)))


def kindle_royalty(price: float, delivery_mb: float = 1.0) -> float:
    """KDP ebook royalty: 70% inside the $2.99-$9.99 band, 35% outside."""
    if price is None or price <= 0:
        return 0.0
    if 2.99 <= price <= 9.99:
        return max(price * 0.70 - delivery_mb * 0.15, 0.0)
    return price * 0.35


def print_cost(pages: int = 120, color: bool = False, marketplace: str = "us") -> float:
    """Amazon printing cost for a US-trade paperback (US rates, approximated)."""
    pages = max(int(pages or 120), 24)
    if color:
        # Standard colour, 6x9in
        base, per_page = (0.0, 0.0)
        cost = pages * (0.0255 if pages <= 108 else 0.0255)
        cost = max(cost, 3.65)
    else:
        if pages <= 108:
            cost = 2.30
        else:
            cost = 0.85 + pages * 0.012
    factor = {"us": 1.0, "uk": 0.85, "de": 0.95, "fr": 0.95, "es": 0.95,
              "it": 0.95, "ca": 1.15, "au": 1.25, "jp": 1.1}.get(marketplace, 1.0)
    return round(cost * factor, 2)


def paperback_royalty(price: float, pages: int = 120, color: bool = False,
                      marketplace: str = "us") -> float:
    """KDP paperback royalty: 60% of list price minus the printing cost."""
    if not price or price <= 0:
        return 0.0
    return max(price * 0.60 - print_cost(pages, color, marketplace), 0.0)


def royalty(price: float | None, store: str = "print", pages: int | None = None,
            marketplace: str = "us") -> float:
    if not price:
        return 0.0
    if store == "kindle":
        return kindle_royalty(price)
    return paperback_royalty(price, pages or 120, False, marketplace)
