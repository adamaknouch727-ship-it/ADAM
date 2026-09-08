"""The engine: seed keyword -> keyword ideas -> scraped niches -> ranked report."""

from __future__ import annotations

import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from . import demo as demo_mod
from . import keywords as kw_mod
from .cache import Cache
from .config import MARKETPLACES, STORES, Settings
from .http_client import BlockedError, HttpClient, NetworkError
from .models import Book, KeywordIdea, NicheReport, SearchRun
from .parser import parse_product, parse_search
from .scoring import summarise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def search_url(keyword: str, marketplace: str = "us", store: str = "print",
               page: int = 1) -> str:
    market = MARKETPLACES[marketplace]
    params = {"k": keyword, "i": STORES.get(store, "stripbooks"), "ref": "nb_sb_noss"}
    if page > 1:
        params["page"] = page
    return f"https://{market.domain}/s?" + urllib.parse.urlencode(params)


class NicheFinder:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        os.makedirs(self.settings.data_dir, exist_ok=True)
        self.cache = Cache(os.path.join(self.settings.data_dir, "cache.sqlite"),
                           ttl=self.settings.cache_ttl)
        self.client = HttpClient(
            delay=self.settings.request_delay, timeout=self.settings.timeout,
            retries=self.settings.max_retries, proxy=self.settings.proxy,
            user_agent=self.settings.user_agent,
        )
        self.degraded = False   # set once Amazon refuses to talk to us

    # ------------------------------------------------------------------ fetch
    def _get(self, url: str, kind: str, ttl: int | None = None) -> str:
        key = f"{kind}:{url}"
        cached = self.cache.get(key, ttl)
        if cached is not None:
            return cached
        market = MARKETPLACES[self.settings.marketplace]
        html = self.client.get(url, market.language)
        self.cache.set(key, html)
        return html

    # -------------------------------------------------------------- one niche
    def analyse_keyword(self, keyword: str, volume_score: float = 0.0,
                        pages: int = 1) -> NicheReport:
        settings = self.settings
        report = NicheReport(keyword=keyword, marketplace=settings.marketplace,
                             store=settings.store, fetched_at=_now())

        if settings.offline or self.degraded:
            return demo_mod.demo_report(keyword, settings.marketplace, settings.store,
                                        volume_score)

        books: list[Book] = []
        try:
            for page in range(1, max(1, pages) + 1):
                html = self._get(search_url(keyword, settings.marketplace, settings.store, page),
                                 "search")
                page_books, count = parse_search(
                    html, f"https://{MARKETPLACES[settings.marketplace].domain}")
                if report.results_count is None:
                    report.results_count = count
                books.extend(page_books)
                if len(books) >= settings.products_per_keyword:
                    break
        except (BlockedError, NetworkError) as exc:
            if settings.allow_demo_fallback:
                self.degraded = True
                fallback = demo_mod.demo_report(keyword, settings.marketplace,
                                                settings.store, volume_score)
                fallback.error = str(exc)
                return fallback
            report.error = str(exc)
            return report

        for index, book in enumerate(books):
            book.position = index + 1
        report.books = books[: settings.products_per_keyword]

        if settings.deep and report.books:
            self._enrich(report.books[: settings.deep_products])

        return summarise(report, volume_score)

    def _enrich(self, books: list[Book]) -> None:
        """Fetch detail pages for the top books: real BSR, publisher, date."""
        for book in books:
            try:
                html = self._get(book.url, "product", ttl=self.settings.cache_ttl * 4)
            except (BlockedError, NetworkError):
                self.degraded = True
                return
            info = parse_product(html)
            book.bsr = info.get("bsr") or book.bsr
            book.bsr_category = info.get("bsr_category", book.bsr_category)
            book.published = info.get("published", book.published)
            book.publisher = info.get("publisher", book.publisher)
            book.pages = info.get("pages", book.pages)

    # -------------------------------------------------------------- full hunt
    def find_niches(self, seed: str, breadth: str = "normal", limit: int = 25,
                    on_progress=None) -> SearchRun:
        settings = self.settings
        started = time.time()
        run = SearchRun(seed=seed, marketplace=settings.marketplace, store=settings.store,
                        started_at=_now())

        if settings.offline:
            ideas = demo_mod.demo_keywords(seed, limit)
            run.source = "demo"
            run.warnings.append("Demo mode: these figures are simulated, "
                                "not scraped from Amazon.")
        else:
            try:
                ideas, warnings = kw_mod.expand(
                    self.client, seed, settings.marketplace, settings.store,
                    breadth=breadth, limit=limit,
                    on_progress=(lambda done, total, probe: on_progress(
                        "keywords", done, total, probe)) if on_progress else None)
                run.warnings.extend(warnings)
            except (BlockedError, NetworkError) as exc:
                run.warnings.append(f"Keyword expansion failed: {exc}")
                ideas = []
            if not ideas and settings.allow_demo_fallback:
                self.degraded = True
                ideas = demo_mod.demo_keywords(seed, limit)
                run.source = "demo"
                run.warnings.append(
                    "Amazon was unreachable, so the tool switched to its built-in demo dataset.")

        run.keywords = ideas
        total = len(ideas)
        done = 0

        with ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
            futures = {
                pool.submit(self.analyse_keyword, idea.keyword, idea.volume_score): idea
                for idea in ideas
            }
            for future in as_completed(futures):
                idea = futures[future]
                done += 1
                try:
                    report = future.result()
                except Exception as exc:  # never let one keyword kill the run
                    report = NicheReport(keyword=idea.keyword, marketplace=settings.marketplace,
                                         store=settings.store, error=str(exc))
                run.niches.append(report)
                if on_progress:
                    on_progress("niches", done, total, idea.keyword)

        if any(n.source == "demo" for n in run.niches):
            run.source = "demo"
            if settings.offline:
                run.warnings = [w for w in run.warnings if "demo dataset" not in w]
                run.warnings.insert(0, "Demo mode: these figures are simulated, "
                                       "not scraped from Amazon.")
            elif not any("demo dataset" in w for w in run.warnings):
                run.warnings.append(
                    "Amazon was unreachable, so the tool switched to its built-in demo dataset.")

        run.warnings = list(dict.fromkeys(run.warnings))
        run.niches.sort(key=lambda n: (-n.opportunity_score, n.keyword))
        run.finished_at = _now()
        run.duration = time.time() - started
        return run
