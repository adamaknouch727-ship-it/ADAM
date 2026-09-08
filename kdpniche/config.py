"""Marketplace tables and tunable constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Marketplace:
    code: str
    name: str
    domain: str
    mid: str                 # marketplace id used by completion.amazon.com
    currency: str
    symbol: str
    language: str
    # Sales at an identical BSR are far lower in small stores than on .com.
    sales_factor: float
    print_store: str = "stripbooks"
    kindle_store: str = "digital-text"


MARKETPLACES: dict[str, Marketplace] = {
    m.code: m
    for m in [
        Marketplace("us", "United States", "www.amazon.com", "ATVPDKIKX0DER", "USD", "$", "en_US", 1.00),
        Marketplace("uk", "United Kingdom", "www.amazon.co.uk", "A1F83G8C2ARO7P", "GBP", "£", "en_GB", 0.26),
        Marketplace("de", "Germany", "www.amazon.de", "A1PA6795UKMFR9", "EUR", "€", "de_DE", 0.22),
        Marketplace("fr", "France", "www.amazon.fr", "A13V1IB3VIYZZH", "EUR", "€", "fr_FR", 0.11),
        Marketplace("es", "Spain", "www.amazon.es", "A1RKKUPIHCS9HS", "EUR", "€", "es_ES", 0.07),
        Marketplace("it", "Italy", "www.amazon.it", "APJ6JRA9NG5V4", "EUR", "€", "it_IT", 0.07),
        Marketplace("ca", "Canada", "www.amazon.ca", "A2EUQ1WTGCTBG2", "CAD", "$", "en_CA", 0.09),
        Marketplace("au", "Australia", "www.amazon.com.au", "A39IBJ37TRP1C6", "AUD", "$", "en_AU", 0.06),
        Marketplace("jp", "Japan", "www.amazon.co.jp", "A1VC38T7YXB528", "JPY", "¥", "ja_JP", 0.16),
        Marketplace("in", "India", "www.amazon.in", "A21TJRUUN4KGV", "INR", "₹", "en_IN", 0.04),
        Marketplace("nl", "Netherlands", "www.amazon.nl", "A1805IZSGTT6HS", "EUR", "€", "nl_NL", 0.03),
        Marketplace("mx", "Mexico", "www.amazon.com.mx", "A1AM78C64UM0Y8", "MXN", "$", "es_MX", 0.03),
        Marketplace("br", "Brazil", "www.amazon.com.br", "A2Q3Y263D00KWC", "BRL", "R$", "pt_BR", 0.02),
        Marketplace("se", "Sweden", "www.amazon.se", "A2NODRKZP88ZB9", "SEK", "kr", "sv_SE", 0.02),
        Marketplace("pl", "Poland", "www.amazon.pl", "A1C3SOZRARQ6R3", "PLN", "zł", "pl_PL", 0.02),
    ]
}

DEFAULT_MARKETPLACE = "us"

# Amazon search department aliases the tool knows how to query.
STORES: dict[str, str] = {
    "print": "stripbooks",       # paperback / hardcover
    "kindle": "digital-text",    # Kindle ebooks
    "all": "stripbooks",
}


@dataclass
class Settings:
    """Runtime knobs, overridable from the environment or the web UI."""

    marketplace: str = DEFAULT_MARKETPLACE
    store: str = "print"
    request_delay: float = 1.6          # seconds between requests to one domain
    timeout: float = 20.0
    max_retries: int = 3
    workers: int = 4                    # parallel keyword analyses
    cache_ttl: int = 60 * 60 * 12       # 12 hours
    products_per_keyword: int = 24
    deep: bool = False                  # also fetch product detail pages (BSR, date)
    deep_products: int = 8
    proxy: str | None = None
    user_agent: str | None = None
    offline: bool = False               # force the built-in demo dataset
    allow_demo_fallback: bool = True    # use demo data when Amazon is unreachable
    data_dir: str = field(default_factory=lambda: os.environ.get(
        "KDPNICHE_HOME", os.path.join(os.path.expanduser("~"), ".kdpniche")))

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        env = os.environ
        s.marketplace = env.get("KDPNICHE_MARKET", s.marketplace)
        s.store = env.get("KDPNICHE_STORE", s.store)
        s.request_delay = float(env.get("KDPNICHE_DELAY", s.request_delay))
        s.workers = int(env.get("KDPNICHE_WORKERS", s.workers))
        s.proxy = env.get("KDPNICHE_PROXY") or env.get("HTTPS_PROXY") or None
        s.offline = env.get("KDPNICHE_OFFLINE", "").lower() in {"1", "true", "yes"}
        return s

    def market(self) -> Marketplace:
        return MARKETPLACES.get(self.marketplace, MARKETPLACES[DEFAULT_MARKETPLACE])


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Publisher names that mean "this is a self-published / indie book".
INDIE_PUBLISHER_MARKERS = [
    "independently published", "createspace", "kindle direct publishing",
    "amazon digital services", "self-published", "lulu", "bookbaby",
    "ingramspark", "draft2digital", "blurb",
]

TRADITIONAL_PUBLISHERS = [
    "penguin", "random house", "harpercollins", "simon & schuster", "hachette",
    "macmillan", "scholastic", "wiley", "pearson", "oxford", "cambridge",
    "bloomsbury", "dk", "usborne", "workman", "chronicle books", "rockridge",
    "callisto", "sourcebooks", "quarto", "disney", "st. martin", "little, brown",
]
