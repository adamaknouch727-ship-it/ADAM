"""Turn raw search results into demand / competition / opportunity scores."""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime

from . import bsr as bsr_mod
from .models import Book, NicheReport
from .parser import classify_publisher

# Weights of the headline opportunity score.
W_DEMAND = 0.42
W_COMPETITION = 0.38
W_PROFIT = 0.20


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _log_scale(value: float, low: float, high: float) -> float:
    """Map value onto 0-100 on a log scale between two anchors."""
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    return 100.0 * (math.log(value) - math.log(low)) / (math.log(high) - math.log(low))


def estimate_book_sales(book: Book, store: str, marketplace: str, position_fallback: bool = True) -> None:
    """Fill in the per-book sales/revenue/royalty estimates, in place."""
    rank = book.bsr
    if rank is None and position_fallback:
        # Without a detail-page BSR, approximate from the search position:
        # page-one books for a real keyword typically sit between #8k and #900k.
        position = max(book.position, 1)
        review_weight = math.log10(max(book.reviews, 1) + 1) + 1
        rank = int(30_000 * position ** 0.85 / review_weight)
    book.est_sales_month = round(bsr_mod.sales_per_month(rank, store, marketplace), 1)
    price = book.price or 0.0
    book.est_revenue_month = round(book.est_sales_month * price, 2)
    book.est_royalty_month = round(
        book.est_sales_month * bsr_mod.royalty(price, store, book.pages, marketplace), 2)


def _age_days(published: str) -> float | None:
    if not published:
        return None
    try:
        day = datetime.fromisoformat(published).date()
    except ValueError:
        return None
    return max((date.today() - day).days, 0)


def summarise(report: NicheReport, volume_score: float = 0.0) -> NicheReport:
    """Compute every aggregate metric and score for one niche."""
    books = [b for b in report.books if not b.sponsored] or report.books
    report.analysed = len(books)
    if not books:
        report.verdict = "No data"
        return report

    # Estimate for every row (sponsored tiles are still shown in the UI) but
    # aggregate only over the organic ones.
    for book in report.books:
        estimate_book_sales(book, report.store, report.marketplace)

    sales = [b.est_sales_month for b in books]
    revenue = [b.est_revenue_month for b in books]
    royalties = [b.est_royalty_month for b in books]
    reviews = [float(b.reviews) for b in books]
    prices = [b.price for b in books if b.price]
    ratings = [b.rating for b in books if b.rating]

    report.est_sales_month = round(sum(sales), 1)
    report.est_revenue_month = round(sum(revenue), 2)
    report.est_royalty_month = round(sum(royalties), 2)
    report.median_sales_month = round(_median(sales), 1)
    report.avg_reviews = round(_mean(reviews), 1)
    report.median_reviews = round(_median(reviews), 1)
    report.avg_rating = round(_mean(ratings), 2)
    report.avg_price = round(_mean(prices), 2)
    report.median_price = round(_median(prices), 2)
    report.low_review_share = round(
        sum(1 for r in reviews if r < 50) / len(reviews), 3)
    report.volume_score = round(volume_score, 1)

    kinds = [classify_publisher(b.publisher, b.author) for b in books]
    known = [k for k in kinds if k != "unknown"]
    if known:
        report.indie_share = round(known.count("indie") / len(known), 3)
        report.traditional_share = round(known.count("traditional") / len(known), 3)

    ages = [a for a in (_age_days(b.published) for b in books) if a is not None]
    if ages:
        report.avg_age_days = round(_mean(ages), 1)
        report.fresh_share = round(sum(1 for a in ages if a <= 365) / len(ages), 3)

    _score(report)
    return report


def _score(report: NicheReport) -> None:
    # ---- Demand: how much money is actually moving on page one ----------
    revenue_part = _log_scale(report.est_royalty_month, 150, 25_000)
    depth_part = _log_scale(report.median_sales_month, 3, 400)
    volume_part = report.volume_score
    demand = 0.45 * revenue_part + 0.35 * depth_part + 0.20 * volume_part

    # ---- Competition: how hard it is to break into page one -------------
    review_wall = _log_scale(report.median_reviews, 5, 3000)
    saturation = _log_scale(report.results_count or 1000, 200, 60_000)
    weak_spots = (1.0 - report.low_review_share) * 100
    big_pub = report.traditional_share * 100
    competition = (0.40 * review_wall + 0.22 * saturation +
                   0.26 * weak_spots + 0.12 * big_pub)
    if report.fresh_share is not None:
        # Lots of brand-new books means the niche is being piled into.
        competition = 0.9 * competition + 0.1 * (report.fresh_share * 100)

    # ---- Profitability: price level and royalty per sale ----------------
    price_part = _log_scale(report.median_price, 3.5, 24.0)
    royalty_per_sale = (report.est_royalty_month / report.est_sales_month
                        if report.est_sales_month else 0.0)
    unit_part = _log_scale(royalty_per_sale, 0.8, 8.0)
    profit = 0.5 * price_part + 0.5 * unit_part

    report.demand_score = round(max(0.0, min(100.0, demand)), 1)
    report.competition_score = round(max(0.0, min(100.0, competition)), 1)
    report.profit_score = round(max(0.0, min(100.0, profit)), 1)

    opportunity = (W_DEMAND * report.demand_score +
                   W_COMPETITION * (100 - report.competition_score) +
                   W_PROFIT * report.profit_score)
    # A niche with no money in it is never an opportunity, however empty it is.
    if report.est_royalty_month < 300:
        opportunity *= 0.55 + 0.45 * (report.est_royalty_month / 300)
    report.opportunity_score = round(max(0.0, min(100.0, opportunity)), 1)
    report.verdict = verdict_for(report.opportunity_score)
    report.reasons = explain(report)


def verdict_for(score: float) -> str:
    if score >= 72:
        return "Goldmine"
    if score >= 60:
        return "Strong"
    if score >= 48:
        return "Decent"
    if score >= 36:
        return "Risky"
    return "Avoid"


def explain(report: NicheReport) -> list[str]:
    out: list[str] = []
    if report.median_reviews <= 60:
        out.append(f"Top books average only {report.median_reviews:.0f} reviews — beatable.")
    elif report.median_reviews >= 800:
        out.append(f"Review wall: median {report.median_reviews:.0f} reviews on page one.")
    if report.low_review_share >= 0.35:
        out.append(f"{report.low_review_share * 100:.0f}% of page one has under 50 reviews.")
    if report.est_royalty_month >= 4000:
        out.append(f"Page one earns about {report.est_royalty_month:,.0f} in royalties per month.")
    elif report.est_royalty_month < 500:
        out.append("Very little money moving in this keyword.")
    if report.results_count and report.results_count > 30_000:
        out.append(f"Crowded: {report.results_count:,} competing books.")
    elif report.results_count and report.results_count < 2_000:
        out.append(f"Only {report.results_count:,} competing books.")
    if report.median_price and report.median_price < 6:
        out.append("Low price point squeezes the royalty per sale.")
    if report.traditional_share >= 0.4:
        out.append("Dominated by traditional publishers.")
    elif report.indie_share >= 0.6:
        out.append("Mostly self-published — an indie can rank here.")
    return out[:5]
