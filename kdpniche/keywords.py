"""Keyword discovery through Amazon's own autocomplete ("alphabet soup").

Amazon only suggests strings that real shoppers actually type, so the
suggestion list is the closest free proxy for search demand inside the store.
"""

from __future__ import annotations

import re
import string
import urllib.parse

from .config import MARKETPLACES, STORES
from .http_client import BlockedError, HttpClient, NetworkError
from .models import KeywordIdea

# Buyer-intent modifiers that reliably surface low-content and niche books.
MODIFIERS = [
    "for kids", "for adults", "for women", "for men", "for beginners",
    "for teens", "for seniors", "gift", "large print", "workbook", "planner",
    "journal", "notebook", "log book", "tracker", "coloring book", "puzzle book",
    "activity book", "prompts", "daily", "weekly", "2026", "christmas", "funny",
]

PREFIXES = ["best ", "cute ", "funny ", "simple ", "easy ", "personalized "]

STOP_PATTERNS = re.compile(
    r"(amazon|prime|kindle unlimited|free shipping|\bapp\b|login|account)", re.I)


def suggest_url(prefix: str, marketplace: str = "us", store: str = "print",
                limit: int = 11) -> str:
    market = MARKETPLACES[marketplace]
    alias = STORES.get(store, "stripbooks")
    params = {
        "limit": limit,
        "prefix": prefix,
        "suggestion-type": "KEYWORD",
        "page-type": "Search",
        "alias": alias,
        "site-variant": "desktop",
        "version": "3",
        "event": "onKeyPress",
        "wc": "",
        "lop": market.language,
        "last-prefix": "",
        "avg-ks-time": "0",
        "fb": "1",
        "plain-mid": "1",
        "client-info": "amazon-search-ui",
        "mid": market.mid,
    }
    return "https://completion.amazon.com/api/2017/suggestions?" + urllib.parse.urlencode(params)


def fetch_suggestions(client: HttpClient, prefix: str, marketplace: str = "us",
                      store: str = "print") -> list[str]:
    payload = client.get_json(suggest_url(prefix, marketplace, store))
    out: list[str] = []
    for item in payload.get("suggestions", []) or []:
        value = (item.get("value") or "").strip().lower()
        if value and not STOP_PATTERNS.search(value):
            out.append(value)
    return out


def _prefixes_for(seed: str, breadth: str) -> list[str]:
    seed = seed.strip().lower()
    probes = [seed]
    if breadth in ("normal", "wide"):
        probes += [f"{seed} {letter}" for letter in string.ascii_lowercase[:12]]
        probes += [f"{seed} {m}" for m in MODIFIERS[:10]]
    if breadth == "wide":
        probes += [f"{seed} {letter}" for letter in string.ascii_lowercase[12:]]
        probes += [f"{seed} {m}" for m in MODIFIERS[10:]]
        probes += [f"{p}{seed}" for p in PREFIXES]
    return probes


def expand(client: HttpClient, seed: str, marketplace: str = "us", store: str = "print",
           breadth: str = "normal", limit: int = 60,
           on_progress=None) -> tuple[list[KeywordIdea], list[str]]:
    """Expand a seed into ranked keyword ideas. Returns (ideas, warnings)."""
    seed = seed.strip().lower()
    warnings: list[str] = []
    scores: dict[str, dict] = {}

    def record(keyword: str, rank: int, source: str) -> None:
        keyword = re.sub(r"\s+", " ", keyword).strip()
        if len(keyword) < 3 or len(keyword) > 80:
            return
        entry = scores.setdefault(keyword, {"hits": 0, "best_rank": 99, "source": source})
        entry["hits"] += 1
        entry["best_rank"] = min(entry["best_rank"], rank)

    record(seed, 0, "seed")
    probes = _prefixes_for(seed, breadth)
    for index, probe in enumerate(probes):
        try:
            for rank, suggestion in enumerate(fetch_suggestions(client, probe, marketplace, store)):
                record(suggestion, rank, "autocomplete")
        except BlockedError:
            warnings.append("Amazon rate-limited the autocomplete API; keyword list is partial.")
            break
        except NetworkError as exc:
            warnings.append(f"Autocomplete unavailable: {exc}")
            break
        if on_progress:
            on_progress(index + 1, len(probes), probe)

    ideas: list[KeywordIdea] = []
    max_hits = max((entry["hits"] for entry in scores.values()), default=1)
    for keyword, entry in scores.items():
        # More prefixes surfacing a phrase + a high position = more demand.
        hit_part = entry["hits"] / max_hits
        rank_part = max(0.0, 1.0 - entry["best_rank"] / 12.0)
        words = len(keyword.split())
        length_bonus = 1.0 if 2 <= words <= 6 else 0.75
        volume = round(min(100.0, (0.6 * hit_part + 0.4 * rank_part) * 100 * length_bonus), 1)
        ideas.append(KeywordIdea(keyword=keyword, source=entry["source"],
                                 rank=entry["best_rank"], hits=entry["hits"],
                                 volume_score=volume))

    ideas.sort(key=lambda idea: (-idea.volume_score, idea.keyword))
    # Always keep the seed itself in the list.
    if all(idea.keyword != seed for idea in ideas[:limit]):
        seed_idea = next((i for i in ideas if i.keyword == seed), None)
        if seed_idea:
            ideas = [seed_idea] + [i for i in ideas if i.keyword != seed]
    return ideas[:limit], warnings
