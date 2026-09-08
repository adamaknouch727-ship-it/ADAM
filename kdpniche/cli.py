"""Command line interface: `python -m kdpniche ...`"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from . import bsr as bsr_mod
from . import export
from .analyzer import NicheFinder
from .config import MARKETPLACES, Settings
from .http_client import HttpClient
from .keywords import expand
from .storage import Storage

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
COLORS = {"Goldmine": "\033[92m", "Strong": "\033[96m", "Decent": "\033[93m",
          "Risky": "\033[33m", "Avoid": "\033[91m", "No data": "\033[90m"}


def _color(text: str, verdict: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{COLORS.get(verdict, '')}{text}{RESET}"


def _settings(args) -> Settings:
    settings = Settings.from_env()
    settings.marketplace = args.market
    settings.store = args.store
    settings.offline = getattr(args, "offline", False) or settings.offline
    settings.deep = getattr(args, "deep", False)
    settings.workers = getattr(args, "workers", settings.workers)
    settings.request_delay = getattr(args, "delay", settings.request_delay)
    return settings


def _print_table(niches: list[dict], symbol: str, limit: int) -> None:
    header = (f"{'#':>3} {'KEYWORD':<38} {'SCORE':>6} {'VERDICT':<9} {'DEM':>4} {'COMP':>5} "
              f"{'ROYALTY/MO':>11} {'MED.REV':>8} {'BOOKS':>8}")
    print(BOLD + header + RESET)
    print(DIM + "-" * len(header) + RESET)
    for index, niche in enumerate(niches[:limit], 1):
        keyword = niche["keyword"][:37]
        line = (f"{index:>3} {keyword:<38} {niche['opportunity_score']:>6.1f} "
                f"{niche['verdict']:<9} {niche['demand_score']:>4.0f} "
                f"{niche['competition_score']:>5.0f} "
                f"{symbol}{niche['est_royalty_month']:>10,.0f} "
                f"{niche['median_reviews']:>8,.0f} "
                f"{(niche.get('results_count') or 0):>8,}")
        print(_color(line, niche["verdict"]))


def cmd_find(args) -> int:
    settings = _settings(args)
    finder = NicheFinder(settings)
    market = MARKETPLACES[settings.marketplace]
    print(f"{BOLD}KDP Niche Finder{RESET} — seed \"{args.seed}\" on {market.domain} "
          f"({settings.store})")

    def progress(stage, done, total, label):
        if args.quiet:
            return
        bar_total = max(total, 1)
        filled = int(28 * done / bar_total)
        sys.stderr.write(f"\r  {stage:<9} [{'█' * filled}{'·' * (28 - filled)}] "
                         f"{done}/{total} {label[:32]:<32}")
        sys.stderr.flush()

    run = finder.find_niches(args.seed, breadth=args.breadth, limit=args.limit,
                             on_progress=progress)
    if not args.quiet:
        sys.stderr.write("\r" + " " * 100 + "\r")

    data = run.to_dict(include_books=True)
    for warning in run.warnings:
        print(f"  ! {warning}")
    print()
    _print_table(data["niches"], market.symbol, args.top)
    print()
    print(f"{DIM}{len(run.niches)} keywords analysed in {run.duration:.1f}s · "
          f"source: {run.source}{RESET}")

    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(export.niches_to_csv(data["niches"]))
        print(f"  CSV  -> {args.csv}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            handle.write(export.run_to_json(data))
        print(f"  JSON -> {args.json}")
    if args.md:
        with open(args.md, "w", encoding="utf-8") as handle:
            handle.write(export.run_to_markdown(data))
        print(f"  MD   -> {args.md}")

    storage = Storage(os.path.join(settings.data_dir, "kdpniche.sqlite"))
    storage.save_run(run.to_dict(include_books=False))
    return 0


def cmd_keyword(args) -> int:
    settings = _settings(args)
    finder = NicheFinder(settings)
    report = finder.analyse_keyword(args.keyword)
    market = MARKETPLACES[settings.marketplace]
    print(f"\n{BOLD}{report.keyword}{RESET}  ({market.domain}, {report.store})")
    print(f"  Niche score      {_color(f'{report.opportunity_score:.1f} / 100  {report.verdict}', report.verdict)}")
    print(f"  Demand           {report.demand_score:.1f}")
    print(f"  Competition      {report.competition_score:.1f}  (lower is better)")
    print(f"  Profitability    {report.profit_score:.1f}")
    print(f"  Competing books  {report.results_count or 0:,}")
    print(f"  Page-one money   {market.symbol}{report.est_royalty_month:,.0f} royalties / month")
    print(f"  Median reviews   {report.median_reviews:,.0f}   avg rating {report.avg_rating}")
    print(f"  Median price     {market.symbol}{report.median_price}")
    for reason in report.reasons:
        print(f"   • {reason}")
    if args.books:
        print(f"\n  {'#':>2} {'TITLE':<52} {'REVIEWS':>8} {'PRICE':>8} {'SALES/MO':>9}")
        for book in report.books[:args.books]:
            print(f"  {book.position:>2} {book.title[:51]:<52} {book.reviews:>8,} "
                  f"{(book.price or 0):>8.2f} {book.est_sales_month:>9,.0f}")
    if report.source == "demo":
        print(f"\n{DIM}  (demo dataset — Amazon was unreachable){RESET}")
    return 0


def cmd_keywords(args) -> int:
    settings = _settings(args)
    client = HttpClient(delay=settings.request_delay, proxy=settings.proxy)
    ideas, warnings = expand(client, args.seed, settings.marketplace, settings.store,
                             breadth=args.breadth, limit=args.limit)
    for warning in warnings:
        print(f"! {warning}")
    for idea in ideas:
        print(f"{idea.volume_score:>6.1f}  {idea.keyword}")
    return 0


def cmd_bsr(args) -> int:
    sales = bsr_mod.sales_per_month(args.rank, args.store, args.market)
    market = MARKETPLACES[args.market]
    print(f"BSR #{args.rank:,} in {market.name} ({args.store})")
    print(f"  ≈ {sales / 30:,.1f} sales/day   {sales:,.0f} sales/month")
    if args.price:
        unit = bsr_mod.royalty(args.price, args.store, args.pages, args.market)
        print(f"  ≈ {market.symbol}{sales * unit:,.0f} royalties/month at "
              f"{market.symbol}{args.price} ({market.symbol}{unit:.2f}/sale)")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    settings = _settings(args)
    httpd = serve(args.host, args.port, settings)
    url = f"http://{args.host}:{args.port}/"
    print(f"{BOLD}KDP Niche Finder{RESET} running at {url}   (Ctrl+C to stop)")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


def cmd_cache(args) -> int:
    settings = _settings(args)
    finder = NicheFinder(settings)
    if args.clear:
        finder.cache.clear()
        print("cache cleared")
    print(finder.cache.stats())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kdpniche", description="Find profitable Amazon KDP niches.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--market", default="us", choices=sorted(MARKETPLACES),
                        help="Amazon marketplace (default: us)")
        sp.add_argument("--store", default="print", choices=["print", "kindle"])
        sp.add_argument("--offline", action="store_true", help="use the built-in demo dataset")
        sp.add_argument("--delay", type=float, default=1.6, help="seconds between requests")
        sp.add_argument("--workers", type=int, default=4)
        return sp

    find = common(sub.add_parser("find", help="full niche hunt from a seed keyword"))
    find.add_argument("seed")
    find.add_argument("--limit", type=int, default=25, help="keywords to analyse")
    find.add_argument("--top", type=int, default=25, help="rows to print")
    find.add_argument("--breadth", default="normal", choices=["narrow", "normal", "wide"])
    find.add_argument("--deep", action="store_true", help="also read product pages for real BSR")
    find.add_argument("--csv"); find.add_argument("--json"); find.add_argument("--md")
    find.add_argument("--quiet", action="store_true")
    find.set_defaults(func=cmd_find)

    one = common(sub.add_parser("keyword", help="analyse a single keyword"))
    one.add_argument("keyword")
    one.add_argument("--deep", action="store_true")
    one.add_argument("--books", type=int, default=10, help="how many books to list")
    one.set_defaults(func=cmd_keyword)

    ideas = common(sub.add_parser("keywords", help="keyword ideas from Amazon autocomplete"))
    ideas.add_argument("seed")
    ideas.add_argument("--limit", type=int, default=60)
    ideas.add_argument("--breadth", default="normal", choices=["narrow", "normal", "wide"])
    ideas.set_defaults(func=cmd_keywords)

    rank = sub.add_parser("bsr", help="convert a Best Sellers Rank into sales")
    rank.add_argument("rank", type=int)
    rank.add_argument("--store", default="print", choices=["print", "kindle"])
    rank.add_argument("--market", default="us", choices=sorted(MARKETPLACES))
    rank.add_argument("--price", type=float)
    rank.add_argument("--pages", type=int, default=120)
    rank.set_defaults(func=cmd_bsr)

    web = common(sub.add_parser("serve", help="start the web app"))
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8777)
    web.add_argument("--no-browser", action="store_true")
    web.add_argument("--deep", action="store_true")
    web.set_defaults(func=cmd_serve)

    cache = common(sub.add_parser("cache", help="inspect or clear the HTTP cache"))
    cache.add_argument("--clear", action="store_true")
    cache.set_defaults(func=cmd_cache)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
