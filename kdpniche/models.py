"""Data structures shared by the scraper, the scorer and the API."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    return value


@dataclass
class Book:
    """One product row from an Amazon search page (optionally enriched)."""

    asin: str = ""
    title: str = ""
    author: str = ""
    price: float | None = None
    rating: float | None = None
    reviews: int = 0
    fmt: str = ""                     # Paperback / Kindle Edition / Hardcover ...
    position: int = 0                 # rank inside the search results
    sponsored: bool = False
    image: str = ""
    url: str = ""
    bsr: int | None = None            # main Best Sellers Rank (deep mode only)
    bsr_category: str = ""
    published: str = ""               # ISO date, deep mode only
    publisher: str = ""
    pages: int | None = None
    est_sales_month: float = 0.0
    est_revenue_month: float = 0.0
    est_royalty_month: float = 0.0

    def to_dict(self) -> dict:
        return {k: _clean(v) for k, v in asdict(self).items()}


@dataclass
class KeywordIdea:
    """A keyword suggested by Amazon's own autocomplete."""

    keyword: str
    source: str = "autocomplete"      # autocomplete | seed | alphabet | modifier
    depth: int = 0
    rank: int = 0                     # position in the suggestion list
    hits: int = 1                     # how many prefixes surfaced it
    volume_score: float = 0.0         # 0-100 proxy for search demand

    def to_dict(self) -> dict:
        return {k: _clean(v) for k, v in asdict(self).items()}


@dataclass
class NicheReport:
    """Everything the tool knows about one keyword / niche."""

    keyword: str
    marketplace: str = "us"
    store: str = "print"
    results_count: int | None = None      # "over 3,000 results"
    books: list[Book] = field(default_factory=list)
    analysed: int = 0

    # Demand
    est_sales_month: float = 0.0          # sum over the analysed top books
    est_revenue_month: float = 0.0
    est_royalty_month: float = 0.0
    median_sales_month: float = 0.0
    volume_score: float = 0.0

    # Competition
    avg_reviews: float = 0.0
    median_reviews: float = 0.0
    avg_rating: float = 0.0
    low_review_share: float = 0.0         # share of top books under 50 reviews
    indie_share: float = 0.0              # share published independently
    traditional_share: float = 0.0
    avg_age_days: float | None = None
    fresh_share: float | None = None      # share published in the last 12 months

    # Money
    avg_price: float = 0.0
    median_price: float = 0.0

    # Scores (0-100)
    demand_score: float = 0.0
    competition_score: float = 0.0        # 100 = brutal competition
    profit_score: float = 0.0
    opportunity_score: float = 0.0        # the headline "niche score"
    verdict: str = ""
    reasons: list[str] = field(default_factory=list)

    source: str = "amazon"                # amazon | cache | demo
    fetched_at: str = ""
    error: str = ""

    def to_dict(self, include_books: bool = True) -> dict:
        data = {k: _clean(v) for k, v in asdict(self).items()}
        if include_books:
            data["books"] = [b.to_dict() for b in self.books]
        else:
            data.pop("books", None)
        return data


@dataclass
class SearchRun:
    """The result of a full niche hunt (one seed -> many keywords)."""

    seed: str
    marketplace: str
    store: str
    keywords: list[KeywordIdea] = field(default_factory=list)
    niches: list[NicheReport] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    duration: float = 0.0
    source: str = "amazon"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self, include_books: bool = False) -> dict:
        return {
            "seed": self.seed,
            "marketplace": self.marketplace,
            "store": self.store,
            "keywords": [k.to_dict() for k in self.keywords],
            "niches": [n.to_dict(include_books=include_books) for n in self.niches],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": round(self.duration, 2),
            "source": self.source,
            "warnings": self.warnings,
        }
