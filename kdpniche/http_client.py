"""Polite stdlib HTTP client for Amazon: throttling, retries, bot detection."""

from __future__ import annotations

import gzip
import io
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from .config import USER_AGENTS


class BlockedError(RuntimeError):
    """Amazon answered with a CAPTCHA / bot wall."""


class NetworkError(RuntimeError):
    """The request never reached Amazon (DNS, proxy, timeout)."""


_BOT_MARKERS = (
    "Enter the characters you see below",
    "To discuss automated access to Amazon data",
    "api-services-support@amazon.com",
    "captcha",
    "Type the characters you see in this image",
)


class Throttle:
    """One token bucket per host, so parallel workers stay polite."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                last = self._last.get(host, 0.0)
                gap = self.delay * random.uniform(0.75, 1.35)
                if now - last >= gap:
                    self._last[host] = now
                    return
                sleep_for = gap - (now - last)
            time.sleep(min(sleep_for, 5.0))


class HttpClient:
    def __init__(self, delay: float = 1.6, timeout: float = 20.0, retries: int = 3,
                 proxy: str | None = None, user_agent: str | None = None) -> None:
        self.throttle = Throttle(delay)
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.HTTPCookieProcessor(),
        ]
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        self._opener = urllib.request.build_opener(*handlers)
        self.requests = 0
        self.blocked = 0

    def _headers(self, language: str = "en-US") -> dict[str, str]:
        return {
            "User-Agent": self.user_agent or random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": f"{language.replace('_', '-')},en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

    @staticmethod
    def _decode(response) -> str:
        raw = response.read()
        encoding = (response.headers.get("Content-Encoding") or "").lower()
        if "gzip" in encoding:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        elif "deflate" in encoding:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")

    def get(self, url: str, language: str = "en-US") -> str:
        host = urllib.parse.urlparse(url).netloc
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self.throttle.wait(host)
            request = urllib.request.Request(url, headers=self._headers(language))
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    html = self._decode(response)
                self.requests += 1
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (503, 429, 403):
                    self.blocked += 1
                    time.sleep(2 ** attempt * 2.0)
                    continue
                raise NetworkError(f"HTTP {exc.code} for {url}") from exc
            except Exception as exc:  # URLError, socket timeout, proxy refusals
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
                continue

            if len(html) < 8000 and any(m.lower() in html.lower() for m in _BOT_MARKERS):
                self.blocked += 1
                time.sleep(2 ** attempt * 2.5)
                last_error = BlockedError("Amazon served a CAPTCHA page")
                continue
            return html

        if isinstance(last_error, BlockedError):
            raise last_error
        raise NetworkError(f"Could not fetch {url}: {last_error}")

    def get_json(self, url: str, language: str = "en-US"):
        text = self.get(url, language)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise NetworkError(f"Bad JSON from {url}") from exc
