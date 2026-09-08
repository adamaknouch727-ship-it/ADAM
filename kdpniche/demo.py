"""Built-in offline dataset.

Amazon is not reachable from every machine (corporate proxies, sandboxes, hard
rate limits). Rather than showing an empty screen, the tool falls back to this
deterministic, clearly-labelled demo dataset so the whole workflow — keywords,
scores, tables, exports — stays usable. Numbers here are simulated, not scraped.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from .models import Book, KeywordIdea, NicheReport
from .scoring import summarise

# Real, commonly-researched KDP niche families used to build demo keyword sets.
NICHE_LIBRARY: dict[str, list[str]] = {
    "journal": ["gratitude journal", "prayer journal for women", "dream journal",
                "fitness journal for women", "travel journal for kids",
                "5 minute journal", "shadow work journal", "bullet journal dot grid"],
    "planner": ["undated daily planner", "meal planner notebook", "homeschool planner",
                "wedding planner book", "budget planner 2026", "teacher lesson planner",
                "adhd planner for adults"],
    "log book": ["blood pressure log book", "mileage log book", "blood sugar log book",
                 "rental property log book", "vehicle maintenance log book",
                 "beekeeping log book", "medication log book for seniors"],
    "coloring": ["adult coloring book flowers", "bold and easy coloring book",
                 "coloring book for toddlers", "mandala coloring book for adults",
                 "halloween coloring book for kids", "grayscale coloring book",
                 "coloring book for seniors with dementia"],
    "puzzle": ["sudoku puzzle book for adults", "word search large print",
               "crossword puzzles for seniors", "kakuro puzzle book",
               "maze book for kids", "cryptogram puzzle book", "hidden pictures book"],
    "notebook": ["composition notebook aesthetic", "cornell notes notebook",
                 "graph paper notebook", "music manuscript paper notebook",
                 "recipe notebook blank", "password book for seniors"],
    "kids": ["bedtime stories for kids", "handwriting practice book for kids",
             "activity book for 5 year olds", "dot markers activity book",
             "scissor skills workbook", "sight words workbook kindergarten"],
    "business": ["etsy shop planner", "small business bookkeeping ledger",
                 "invoice book for small business", "client tracker notebook",
                 "content planner for creators"],
    "health": ["low sodium cookbook for beginners", "anti inflammatory diet cookbook",
               "food and symptom diary", "workout log book for men",
               "intermittent fasting journal"],
}

TITLE_TEMPLATES = [
    "{kw_title}: 120 Pages for Daily Use | Large Print Edition",
    "The Ultimate {kw_title} Book for Beginners",
    "{kw_title} — Simple Layout, 6x9 in, Gift Edition",
    "My {kw_title}: A Guided Workbook",
    "{kw_title} for Busy People (Volume 2)",
    "{kw_title}: 100 Puzzles With Solutions",
    "Big Book of {kw_title}",
    "{kw_title} Tracker & Notebook",
    "{kw_title}: A 90-Day Companion",
    "{kw_title} Made Easy",
]

AUTHORS = ["Ava Bennett", "Liam Carter", "Noor Haddad", "S. R. Whitfield", "Mia Delacroix",
           "Jonas Keller", "Priya Raman", "Oakwood Press", "Bright Page Studio",
           "T. J. Morgan", "Elena Rossi", "Blue Harbor Books"]

PUBLISHERS_INDIE = ["Independently published", "", "", "Bright Page Studio"]
PUBLISHERS_TRAD = ["Rockridge Press", "Penguin Random House", "DK", "Usborne", "Callisto"]


def _rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def demo_keywords(seed: str, limit: int = 25) -> list[KeywordIdea]:
    seed = seed.strip().lower() or "journal"
    rng = _rng("kw", seed)
    pool: list[str] = []
    for family, entries in NICHE_LIBRARY.items():
        if family in seed or seed in family or any(word in seed for word in family.split()):
            pool.extend(entries)
    if not pool:
        pool = [f"{seed} {suffix}" for suffix in
                ["for adults", "for kids", "for women", "for beginners", "for seniors",
                 "large print", "notebook", "journal", "workbook", "planner", "gift",
                 "log book", "tracker", "2026", "funny", "daily", "with prompts"]]
        for entries in NICHE_LIBRARY.values():
            pool.extend(entries[:2])
    pool = [seed] + [p for p in dict.fromkeys(pool) if p != seed]

    ideas: list[KeywordIdea] = []
    for index, keyword in enumerate(pool[:limit]):
        volume = 100.0 if index == 0 else round(max(8.0, 92 - index * 2.4 + rng.uniform(-8, 8)), 1)
        ideas.append(KeywordIdea(keyword=keyword, source="demo", rank=index,
                                 hits=max(1, 12 - index // 3), volume_score=volume))
    ideas.sort(key=lambda i: -i.volume_score)
    return ideas


def demo_report(keyword: str, marketplace: str = "us", store: str = "print",
                volume_score: float = 0.0) -> NicheReport:
    rng = _rng("niche", keyword, marketplace, store)
    report = NicheReport(keyword=keyword, marketplace=marketplace, store=store,
                         source="demo",
                         fetched_at=date.today().isoformat())
    report.results_count = int(rng.lognormvariate(8.4, 1.25)) + 120

    # A niche has a "hotness" that drives both money and competition.
    hotness = rng.betavariate(2.2, 2.6)
    review_center = 10 ** (0.9 + hotness * 2.4)
    offset = rng.randrange(len(TITLE_TEMPLATES))
    books: list[Book] = []
    for position in range(1, 21):
        reviews = int(max(0, rng.lognormvariate(
            max(0.5, __import__("math").log(review_center)) - position * 0.06, 1.05)))
        price = round(rng.uniform(3.99, 9.99) if store == "kindle"
                      else rng.uniform(5.99, 16.99), 2)
        indie = rng.random() < (0.75 - 0.35 * hotness)
        published = date.today() - timedelta(days=int(rng.expovariate(1 / 620)) + 20)
        books.append(Book(
            asin=f"D{hashlib.md5(f'{keyword}{position}'.encode()).hexdigest()[:9].upper()}",
            title=TITLE_TEMPLATES[(position + offset) % len(TITLE_TEMPLATES)]
            .format(kw_title=keyword.title()),
            author=rng.choice(AUTHORS),
            price=price,
            rating=round(min(5.0, max(3.2, rng.gauss(4.5, 0.3))), 1),
            reviews=reviews,
            fmt="Kindle Edition" if store == "kindle" else "Paperback",
            position=position,
            sponsored=position in (1, 5) and rng.random() < 0.4,
            url="https://www.amazon.com/dp/DEMO",
            publisher=rng.choice(PUBLISHERS_INDIE if indie else PUBLISHERS_TRAD),
            published=published.isoformat(),
            pages=int(rng.choice([60, 90, 110, 120, 150, 200])),
            bsr=int(max(300, rng.lognormvariate(11.2 - hotness * 2.6 + position * 0.11, 0.9))),
        ))
    report.books = books
    return summarise(report, volume_score or rng.uniform(30, 90))
