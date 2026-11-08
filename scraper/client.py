"""
HTTP client untuk SINTA (sinta.kemdiktisaintek.go.id).

Fitur:
  * retry + exponential backoff
  * rate limiting (sopan terhadap server)
  * cache HTML ke disk (hemat request saat eksperimen / re-run)
  * opsi relay `*.translate.goog` untuk mesin yang diblokir WAF SINTA
    (mis. VPS/cloud/datacenter). Dijalankan dari ISP Indonesia biasanya
    tidak perlu relay.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("sinta.http")

BASE = "https://sinta.kemdiktisaintek.go.id"
RELAY_HOST = "sinta-kemdiktisaintek-go-id.translate.goog"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}


class BlockedError(RuntimeError):
    """SINTA mengembalikan 403/429 (WAF)."""


class SintaClient:
    def __init__(
        self,
        delay: float = 1.0,
        timeout: int = 30,
        retries: int = 3,
        cache_dir: Optional[str] = ".cache_sinta",
        use_relay: bool = False,
        cookies_file: Optional[str] = None,
    ) -> None:
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.retries = retries
        self.use_relay = use_relay
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        if use_relay:
            self.session.headers["Referer"] = "https://translate.google.com/"
        if cookies_file and Path(cookies_file).exists():
            self._load_cookies(cookies_file)
        self._last_request = 0.0

    # ------------------------------------------------------------------ http
    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else "/" + path
        if not self.use_relay:
            return BASE + path
        sep = "&" if "?" in path else "?"
        return f"https://{RELAY_HOST}{path}{sep}_x_tr_sl=id&_x_tr_tl=en&_x_tr_hl=en"

    def _cache_path(self, url: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        key = hashlib.sha1(url.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key}.html"

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.3))
        self._last_request = time.monotonic()

    def get_soup(self, path: str, use_cache: bool = True) -> BeautifulSoup:
        url = self._url(path)
        cpath = self._cache_path(url)
        if use_cache and cpath and cpath.exists():
            return BeautifulSoup(cpath.read_text(encoding="utf-8"), "lxml")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:  # jaringan
                last_exc = exc
                log.warning("network error %s (attempt %s/%s)", exc, attempt, self.retries)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                text = resp.text
                if cpath:
                    cpath.write_text(text, encoding="utf-8")
                return BeautifulSoup(text, "lxml")

            if resp.status_code in (403, 429, 503):
                last_exc = BlockedError(f"HTTP {resp.status_code} untuk {url}")
                log.warning(
                    "HTTP %s (WAF) attempt %s/%s – %ss",
                    resp.status_code, attempt, self.retries, 2 ** attempt,
                )
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 404:
                log.info("404 %s", url)
                return BeautifulSoup("<html></html>", "lxml")

            last_exc = RuntimeError(f"HTTP {resp.status_code} untuk {url}")
            time.sleep(2 ** attempt)

        raise BlockedError(
            "Gagal mengambil halaman SINTA. Bila berjalan di VPS/cloud, IP Anda "
            "kemungkinan diblokir WAF SINTA -> jalankan dengan --relay, atau "
            f"jalankan dari jaringan lokal (telkomsel/indihome). Terakhir: {last_exc}"
        )

    # --------------------------------------------------------------- cookies
    def _load_cookies(self, path: str) -> None:
        """Format Netscape (hasil ekstensi 'Get cookies.txt')."""
        n = 0
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                self.session.cookies.set(parts[5], parts[6], domain=parts[0])
                n += 1
        log.info("memuat %s cookie dari %s", n, path)
