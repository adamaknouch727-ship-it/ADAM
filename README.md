# 📚 KDP Niche Finder

A complete Amazon KDP niche-research tool — the kind of workflow Book Beam's
niche finder gives you, running locally on your own machine, with no account, no
subscription and **no dependencies to install**. Pure Python 3.9+ standard
library plus a single-page web UI.

```
python3 run.py            # opens http://127.0.0.1:8777
```

![tabs](https://img.shields.io/badge/marketplaces-15-blue) ![tests](https://img.shields.io/badge/tests-55-green) ![deps](https://img.shields.io/badge/dependencies-none-brightgreen)

---

## What it does

1. **Expands your seed keyword** with Amazon's own autocomplete API — the
   "alphabet soup" method. Amazon only suggests phrases real shoppers type, so
   the suggestion list is the best free proxy for in-store search demand.
2. **Scrapes the Books / Kindle search page** for every keyword: titles,
   authors, prices, ratings, review counts, formats, sponsored slots.
3. **Estimates sales** from Best Sellers Rank with per-store, per-marketplace
   rank→sales curves, and converts them into real KDP royalties (70% / 35%
   Kindle bands, 60% print minus printing cost).
4. **Scores every niche** on demand, competition and profitability, then ranks
   them so the best opportunities float to the top.
5. **Lets you act**: shortlist niches, drill into a niche as a new seed, inspect
   page one book by book, export CSV / JSON / Markdown.

## Install

Nothing to install. You need Python 3.9 or newer.

```bash
git clone <this repo>
cd ADAM
python3 run.py
```

The web app opens at `http://127.0.0.1:8777`. Your shortlist, search history and
the HTTP cache live in `~/.kdpniche/`.

## The web app

| Tab | What you get |
| --- | --- |
| **Niches** | The ranked table: niche score, verdict, demand, competition, royalties/month, sales/month, median reviews, competing books, price. Sort any column, filter by score, competition or review wall, export. |
| **Keyword ideas** | Every phrase Amazon's autocomplete surfaced, with a search-demand proxy. One click re-runs the hunt using that phrase as the seed. |
| **Shortlist** | Niches you starred, saved to SQLite so they survive restarts. |
| **History** | Your last 50 searches, reopenable. |
| **BSR calculator** | Rank → sales → royalties, plus the reverse: "what rank do I need for $2,000/month?" |

Click any row to open the detail drawer: the score breakdown, the plain-English
reasons behind it, and the actual page-one books with their estimated sales.

## The command line

```bash
# Full niche hunt, export everything
python3 -m kdpniche find "gratitude journal" --market us --store print \
        --limit 40 --breadth wide --csv niches.csv --json run.json --md report.md

# One keyword, with the top 10 competing books
python3 -m kdpniche keyword "sudoku puzzle book for adults" --books 10

# Just the keyword ideas
python3 -m kdpniche keywords "coloring book" --limit 60

# Rank → money
python3 -m kdpniche bsr 25000 --store print --price 9.99 --pages 120

# Web app on another port, cache maintenance
python3 -m kdpniche serve --port 9000
python3 -m kdpniche cache --clear
```

Useful flags on every command: `--market` (15 marketplaces), `--store print|kindle`,
`--deep` (read product pages for real BSR, publisher and publication date — much
slower, much more accurate), `--delay` (seconds between requests),
`--workers`, `--offline`.

## How the scores work

**Niche score = 42% demand + 38% (100 − competition) + 20% profitability**, then
damped when page one earns almost nothing.

| Score | Verdict |
| --- | --- |
| 72–100 | Goldmine |
| 60–71 | Strong |
| 48–59 | Decent |
| 36–47 | Risky |
| 0–35 | Avoid |

**Demand** — estimated royalties moving on page one (45%), median sales per book
(35%), and how strongly Amazon's autocomplete pushes the phrase (20%).

**Competition** (lower is better) — the review wall on page one (40%), how many
competing books exist (22%), how *few* weak books there are (26%), the share of
slots held by traditional publishers (12%), plus a nudge for how much brand-new
product is being dumped into the niche.

**Profitability** — price level and royalty per sale after KDP's split and
printing costs.

### Sales estimation

`kdpniche/bsr.py` holds two piecewise power-law curves (print and Kindle) fitted
through published rank/sales anchors for amazon.com, interpolated in log-log
space and scaled per marketplace (`.co.uk` ≈ 26% of `.com` at the same rank,
`.de` ≈ 22%, `.fr` ≈ 11%, and so on).

Without `--deep`, a book's rank is inferred from its search position and review
count. With `--deep`, the tool reads the product page and uses the **real** Best
Sellers Rank, publisher and publication date. Deep mode is slower and gets you
publisher mix and book age on top.

## Scraping responsibly

Amazon does not publish sales data and does not want to be hammered. The client
throttles itself (1.6s between requests by default, jittered), rotates user
agents, retries with exponential backoff, detects CAPTCHA walls and caches every
response for 12 hours in SQLite, so re-running a search costs nothing.

If Amazon blocks you: raise `--delay`, lower `--workers`, wait a while, or route
through a proxy with `--proxy` / the `KDPNICHE_PROXY` environment variable.

## Demo mode

Some machines cannot reach Amazon at all (corporate proxies, sandboxes, hard
blocks). Instead of showing an empty screen, the tool falls back to a built-in,
deterministic demo dataset and labels every screen **DEMO DATA**. Force it with
`--offline` or the "Demo mode" checkbox. Those numbers are simulated — never
make a publishing decision on them.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

55 tests cover the rank curves and royalty maths, the scoring model, the HTML
parsers (against saved Amazon fixtures), keyword expansion, the analyzer's cache
and fallback paths, and the whole HTTP API end to end.

## Project layout

```
kdpniche/
  config.py       marketplaces, stores, tunable settings
  http_client.py  throttled stdlib HTTP client with CAPTCHA detection
  keywords.py     Amazon autocomplete expansion (alphabet soup)
  parser.py       tolerant search-page and product-page parsing
  bsr.py          rank → sales → royalty maths
  scoring.py      demand / competition / profitability / niche score
  analyzer.py     the engine that ties it together
  demo.py         offline dataset
  cache.py        SQLite HTTP cache
  storage.py      shortlist and search history
  export.py       CSV / JSON / Markdown
  server.py       JSON API + static hosting
  cli.py          command line
web/              the single-page app (HTML / CSS / vanilla JS)
tests/            unittest suites and Amazon HTML fixtures
```

## Honest limits

- Every sales figure on every KDP tool, this one included, is a **model**.
  Amazon publishes no unit data. Treat the numbers as relative, not absolute.
- Search-page scraping is the free path. It breaks the day Amazon changes its
  markup; the parser is written defensively but will need updates over time.
- The autocomplete "search volume" is a proxy, not a real volume figure. There
  is no free source of true Amazon search volume.
- Check trademarks yourself before publishing into any niche
  (<https://tmsearch.uspto.gov>). No tool does that for you.

---

## بالدارجة — كيفاش تخدم بيه

**آش كيدير هاد التول:**
كتعطيه كلمة وحدة (مثلا `gratitude journal`)، وهو كيمشي عند أمازون، كيجيب منها
الكلمات اللي كيقلبو عليها الناس بحق، ومن بعد كيشوف الكتوبة اللي مصنفين ف كل
كلمة، كيحسب شحال كيبيعو وشحال دايرين ديال الفلوس، وشحال صعيبة المنافسة، ومن
بعد كيرتبهم ليك من الأحسن للأخيب.

**كيفاش تشغلو:**

```bash
python3 run.py
```

من بعد حل `http://127.0.0.1:8777` ف المتصفح، كتب الكلمة ديالك، وضغط
**Find niches**.

**فهم الأرقام:**

- **Niche score** — النقطة العامة من 100. 72 وفوق = نيش زوين بزاف. قل من 36 = بعد عليه.
- **Demand** — شحال ديال الفلوس كتدور ف هاد الكلمة.
- **Competition** — المنافسة. هنا **قل هو حسن**.
- **Royalties / mo** — تقدير ديال الأرباح ف الشهر ديال الصفحة الأولى كاملة.
- **Median reviews** — إلا كانت قليلة، تقدر تدخل بسهولة.

**نصيحة ف الخدمة:** قلب على نيش النقطة ديالو فوق 60 و التعليقات (reviews) قل من
150. من بعد ضغط على السطر باش تشوف الكتوبة اللي ف الصفحة الأولى — إلا كانو
الأغلفة ديالهم ضعاف، تقدر تغلبهم.

**ملاحظة مهمة:** إلا كان أمازون محجوب ف الشبكة ديالك، التول كيخدم ب **DEMO DATA**
(أرقام تجريبية ماشي حقيقية) وكيبين ليك ديك العلامة الصفراء فوق. باش تجيب أرقام
حقيقية خاصك تشغلو من جهاز عندو اتصال عادي ب `amazon.com`.

---

MIT-style use: it's your copy, do what you want with it.
