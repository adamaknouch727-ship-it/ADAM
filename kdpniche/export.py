"""CSV / JSON / Markdown export of niche reports."""

from __future__ import annotations

import csv
import io
import json

NICHE_COLUMNS = [
    ("keyword", "Keyword"),
    ("opportunity_score", "Niche score"),
    ("verdict", "Verdict"),
    ("demand_score", "Demand"),
    ("competition_score", "Competition"),
    ("profit_score", "Profit"),
    ("volume_score", "Search volume"),
    ("results_count", "Competing books"),
    ("est_sales_month", "Est. sales/mo (top 20)"),
    ("est_revenue_month", "Est. revenue/mo"),
    ("est_royalty_month", "Est. royalties/mo"),
    ("median_sales_month", "Median sales/mo"),
    ("median_reviews", "Median reviews"),
    ("avg_reviews", "Avg reviews"),
    ("avg_rating", "Avg rating"),
    ("low_review_share", "Share under 50 reviews"),
    ("indie_share", "Self-published share"),
    ("traditional_share", "Traditional pub share"),
    ("median_price", "Median price"),
    ("avg_price", "Avg price"),
    ("marketplace", "Marketplace"),
    ("store", "Store"),
    ("source", "Data source"),
]

BOOK_COLUMNS = [
    ("position", "#"), ("title", "Title"), ("author", "Author"), ("asin", "ASIN"),
    ("fmt", "Format"), ("price", "Price"), ("rating", "Rating"), ("reviews", "Reviews"),
    ("bsr", "BSR"), ("est_sales_month", "Est. sales/mo"),
    ("est_royalty_month", "Est. royalties/mo"), ("published", "Published"),
    ("publisher", "Publisher"), ("url", "URL"),
]


def niches_to_csv(niches: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in NICHE_COLUMNS])
    for niche in niches:
        writer.writerow([niche.get(key, "") for key, _ in NICHE_COLUMNS])
    return buffer.getvalue()


def books_to_csv(books: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in BOOK_COLUMNS])
    for book in books:
        writer.writerow([book.get(key, "") for key, _ in BOOK_COLUMNS])
    return buffer.getvalue()


def run_to_json(run: dict) -> str:
    return json.dumps(run, indent=2, ensure_ascii=False)


def run_to_markdown(run: dict) -> str:
    lines = [
        f"# KDP niche report — \"{run.get('seed', '')}\"",
        "",
        f"Marketplace: **{run.get('marketplace', '').upper()}** · Store: "
        f"**{run.get('store', '')}** · Generated: {run.get('finished_at', '')}",
        "",
        "| Keyword | Score | Verdict | Demand | Competition | Royalties/mo | Median reviews |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for niche in run.get("niches", []):
        lines.append(
            f"| {niche.get('keyword', '')} | {niche.get('opportunity_score', 0)} | "
            f"{niche.get('verdict', '')} | {niche.get('demand_score', 0)} | "
            f"{niche.get('competition_score', 0)} | {niche.get('est_royalty_month', 0):,.0f} | "
            f"{niche.get('median_reviews', 0):,.0f} |")
    if run.get("source") == "demo":
        lines += ["", "> Generated from the built-in demo dataset (Amazon was unreachable)."]
    return "\n".join(lines)
