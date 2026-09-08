"""Tolerant HTML parsing of Amazon search and product pages (stdlib only).

Amazon rewrites its markup constantly, so every field is extracted with several
fallback patterns and a missing field never breaks the analysis.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import datetime

from .config import INDIE_PUBLISHER_MARKERS, TRADITIONAL_PUBLISHERS
from .models import Book

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def text(fragment: str | None) -> str:
    if not fragment:
        return ""
    return _WS_RE.sub(" ", htmllib.unescape(_TAG_RE.sub(" ", fragment))).strip()


def _first(patterns: list[str], blob: str, group: int = 1) -> str:
    for pattern in patterns:
        match = re.search(pattern, blob, re.I | re.S)
        if match:
            return match.group(group)
    return ""


def _number(value: str) -> float | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,]", "", value)
    if not cleaned:
        return None
    # 1.234,56 (EU) vs 1,234.56 (US)
    if cleaned.count(",") and cleaned.count("."):
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1 and len(cleaned.split(",")[-1]) in (1, 2):
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _int(value: str) -> int:
    number = _number(value)
    return int(number) if number is not None else 0


FORMATS = [
    "Paperback", "Hardcover", "Kindle Edition", "Spiral-bound", "Board book",
    "Audible Audiobook", "Audio CD", "Mass Market Paperback", "Library Binding",
    "Broché", "Taschenbuch", "Gebundene Ausgabe", "Tapa blanda", "Copertina flessibile",
]


def split_results(html: str) -> list[str]:
    """Cut the search page into one blob per product tile."""
    blocks: list[str] = []
    markers = [
        r'<div[^>]+data-component-type="s-search-result"',
        r'<div[^>]+data-asin="[A-Z0-9]{10}"[^>]*data-index=',
        r'<div[^>]+role="listitem"[^>]+data-asin="[A-Z0-9]{10}"',
    ]
    for marker in markers:
        positions = [m.start() for m in re.finditer(marker, html, re.I)]
        if len(positions) >= 3:
            positions.append(len(html))
            blocks = [html[positions[i]:positions[i + 1]] for i in range(len(positions) - 1)]
            break
    return blocks


def parse_search(html: str, base_url: str = "https://www.amazon.com") -> tuple[list[Book], int | None]:
    """Return (books, total result count) for one search results page."""
    books: list[Book] = []
    for index, block in enumerate(split_results(html)):
        asin = _first([r'data-asin="([A-Z0-9]{10})"'], block)
        if not asin:
            continue
        title = text(_first([
            r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>',
            r'<h2[^>]*aria-label="([^"]+)"',
            r'class="[^"]*s-line-clamp-[^"]*"[^>]*>\s*<span[^>]*>(.*?)</span>',
        ], block))
        if not title or len(title) < 2:
            continue

        rating_raw = _first([
            r'<span[^>]*aria-label="([\d.,]+)\s+out of 5',
            r'<span class="a-icon-alt">([\d.,]+)\s+(?:out of|von|sur|su|de)\s',
            r'aria-label="([\d.,]+) de 5 estrellas"',
        ], block)
        rating = _number(rating_raw)
        if rating is not None and rating > 5:
            rating = rating / 10 if rating <= 50 else None

        reviews_raw = _first([
            r'aria-label="([\d.,]+)\s+(?:ratings|reviews|évaluations|Bewertungen|valoraciones|recensioni)"',
            r'<span[^>]*class="[^"]*s-underline-text[^"]*"[^>]*>([\d.,]+)</span>',
            r'customerReviews[^>]*>.*?<span[^>]*>\(?([\d.,]+)\)?</span>',
        ], block)
        reviews = _int(reviews_raw)

        price_raw = _first([
            r'<span class="a-price"[^>]*>\s*<span class="a-offscreen">([^<]+)</span>',
            r'<span class="a-offscreen">([^<]+)</span>',
            r'<span class="a-price-whole">([\d.,]+)</span>',
        ], block)
        price = _number(price_raw)
        if price is not None and price <= 0:
            price = None

        fmt = ""
        for candidate in FORMATS:
            if re.search(rf">\s*{re.escape(candidate)}\s*<", block, re.I):
                fmt = candidate
                break

        author = text(_first([
            r'<span class="a-size-base">\s*(?:by|von|par|di|de)\s*</span>\s*<a[^>]*>(.*?)</a>',
            r'(?:by|von|par|di|de)\s*</span>\s*<span[^>]*class="a-size-base"[^>]*>(.*?)</span>',
            r'<a class="a-size-base a-link-normal s-underline-text[^"]*"[^>]*>(.*?)</a>',
        ], block))

        image = _first([r'<img[^>]+class="s-image"[^>]+src="([^"]+)"',
                        r'<img[^>]+src="(https://m\.media-amazon\.com/images/[^"]+)"'], block)
        sponsored = bool(re.search(r'>\s*Sponsored\s*<|data-component-type="sp-sponsored-result"',
                                   block, re.I))

        books.append(Book(
            asin=asin, title=title, author=author, price=price, rating=rating,
            reviews=reviews, fmt=fmt, position=index + 1, sponsored=sponsored,
            image=image, url=f"{base_url}/dp/{asin}",
        ))

    return books, parse_result_count(html)


def parse_result_count(html: str) -> int | None:
    match = re.search(
        r'(?:of\s+(?:over\s+)?|von\s+(?:über\s+)?|sur\s+(?:plus de\s+)?|de\s+(?:más de\s+)?)'
        r'([\d.,]{2,15})\s*(?:results|Ergebnissen|résultats|resultados|risultati)',
        html, re.I)
    if match:
        return _int(match.group(1))
    match = re.search(r'"totalResultCount"\s*:\s*(\d+)', html)
    if match:
        return int(match.group(1))
    return None


_DATE_FORMATS = [
    "%B %d, %Y", "%d %B %Y", "%d. %B %Y", "%Y/%m/%d", "%d/%m/%Y", "%b %d, %Y",
]


def _parse_date(raw: str) -> str:
    raw = raw.strip().strip(",")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"(\d{4})", raw)
    return f"{match.group(1)}-01-01" if match else ""


def parse_product(html: str) -> dict:
    """Pull BSR, publisher, publication date and page count off a detail page."""
    info: dict = {}

    ranks = re.findall(r"#([\d.,]+)\s+(?:in|en|dans|di)\s+([^(<\n]{2,60})", html)
    if ranks:
        clean = [(_int(rank), text(cat)) for rank, cat in ranks if _int(rank) > 0]
        if clean:
            best = max(clean, key=lambda pair: pair[0])  # the widest category
            info["bsr"] = best[0]
            info["bsr_category"] = best[1].strip()
            info["sub_ranks"] = [
                {"rank": rank, "category": cat} for rank, cat in clean if rank != best[0]
            ][:5]

    date_raw = _first([
        r'Publication date[^<]*</span>\s*<span[^>]*>([^<]+)</span>',
        r'Publication date.{0,120}?>\s*([A-Z][a-z]+ \d{1,2}, \d{4})',
        r'"publicationDate"\s*:\s*"([^"]+)"',
        r'(?:Erscheinungstermin|Date de publication|Fecha de publicación|Data di pubblicazione)[^<]*</span>\s*<span[^>]*>([^<]+)</span>',
    ], html)
    if date_raw:
        info["published"] = _parse_date(text(date_raw))

    publisher = text(_first([
        r'Publisher[^<]*</span>\s*<span[^>]*>([^<]+)</span>',
        r'(?:Herausgeber|Éditeur|Editorial|Editore)[^<]*</span>\s*<span[^>]*>([^<]+)</span>',
    ], html))
    if publisher:
        info["publisher"] = re.sub(r"\(.*?\)", "", publisher).strip(" ;")

    pages = _first([
        r'([\d.,]+)\s*pages',
        r'Print length[^<]*</span>\s*<span[^>]*>\s*([\d.,]+)',
        r'([\d.,]+)\s*(?:Seiten|páginas|pagine)',
    ], html)
    if pages:
        value = _int(pages)
        if 10 <= value <= 3000:
            info["pages"] = value

    return info


def classify_publisher(publisher: str, author: str = "") -> str:
    """indie | traditional | unknown"""
    blob = (publisher or "").lower()
    if not blob:
        return "unknown"
    if any(marker in blob for marker in INDIE_PUBLISHER_MARKERS):
        return "indie"
    if any(marker in blob for marker in TRADITIONAL_PUBLISHERS):
        return "traditional"
    # A "publisher" identical to the author name is a self-publisher.
    if author and author.lower().strip() in blob:
        return "indie"
    return "unknown"
