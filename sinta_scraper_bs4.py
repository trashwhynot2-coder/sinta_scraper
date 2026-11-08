#!/usr/bin/env python3
# =============================================================================
# sinta_scraper_bs4.py — scraper SINTA versi SATU FILE (BeautifulSoup)
#
# Gaya mengikuti scrape_all_topics_optimized.py:
#   * CONFIG di atas, tinggal edit
#   * CSV ditulis INKREMENTAL (aman dibuka kapan saja, anti-crash)
#   * XLSX di-rebuild berkala dari CSV
#   * finalize() dipanggil juga saat crash -> progres tidak hilang
#   * StepTimer: tahu langkah mana yang lambat (bukan menebak)
#   * kalau selector tidak cocok -> dump HTML ke debug_*.html
#
# Beda dengan referensi: SINTA itu server-rendered, jadi cukup
# requests + BeautifulSoup (jauh lebih cepat & hemat RAM daripada Selenium).
# Selenium hanya dipakai sebagai fallback kalau kena 403 WAF.
#
# Pemakaian:
#   pip install -r requirements.txt
#   python sinta_scraper_bs4.py                  # pakai CONFIG di bawah
#   python sinta_scraper_bs4.py --subject 45887 --pages 3 --region JABODETABEK
#   python sinta_scraper_bs4.py --author 5996301
#   python sinta_scraper_bs4.py --affiliation 430 --pages 4
#   python sinta_scraper_bs4.py --relay          # kalau kena 403
# =============================================================================

import csv
import json
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# =============================================================================
# CONFIG
# =============================================================================

# Bisa ditimpa environment variable (dipakai tes lokal tanpa internet)
BASE_URL = os.environ.get("SINTA_BASE_URL", "https://sinta.kemdiktisaintek.go.id")
RELAY_HOST = os.environ.get(
    "SINTA_RELAY_HOST", "sinta-kemdiktisaintek-go-id.translate.goog")

# --- SEED: dari mana daftar dosen diambil (boleh kombinasikan beberapa) ------
SUBJECT_IDS = ["45887"]        # /subjects/detail/<id>   contoh: 45887
# "all" = sapu SEMUA halaman daftar (subjek 45823 = 136 halaman / 1.355 dosen)
SUBJECT_PAGES = 2              # angka atau "all"; 1 halaman = ~10 dosen
AFFILIATION_IDS = []           # /affiliations/profile/<id>  contoh: 430 (UI)
AFFILIATION_PAGES = 3          # angka atau "all"
AUTHOR_IDS = []                # /authors/profile/<id>   contoh: 5996301
SEARCH_TERMS = []              # /authors?q=<nama>
SEARCH_PAGES = 2               # angka atau "all"

# --- MODE SUMBER -------------------------------------------------------------
# "subjek" = ambil dari subject_ids (default): semua halaman subjek disapu,
#            lalu disaring wilayah. SINTA tidak punya filter wilayah, jadi
#            inilah harga untuk mencakup satu topik.
# "kampus" = ambil dari daftar institusi lebih dulu: hanya kampus di wilayah
#            target yang dibuka, dan SEMUA dosennya otomatis in-region.
#            Sekali scan (hasil di-cache), lalu bisa dipakai berkali-kali.
# "auto"   = "kampus" kalau subject_ids kosong, kalau tidak "subjek".
SOURCE_MODE = "auto"

# Halaman daftar institusi yang discan untuk mode kampus (0 = semua 558 hal).
AFFILIATION_SCAN_PAGES = 0
MAX_CAMPUSES = 0               # 0 = semua kampus yang lolos filter

# --- MODE DUA FASE (hemat) --------------------------------------------------
# True : FASE 1 sapu daftar (murah, 10 dosen/halaman) -> cek lokasi -> FASE 2
#        hanya buka profil dosen yang lolos filter, sebanyak MAX_AUTHORS.
# False: perilaku lama (profil dibuka untuk semua kandidat yang lolos filter).
TWO_PHASE = True

# --- FILTER WILAYAH ---------------------------------------------------------
# "JABODETABEK" | "DKI" | "BODETABEK" | "JABAR" | ["DKI","BODETABEK"] | [] = semua
REGIONS = ["JABODETABEK"]
STRICT_JABODETABEK = True      # True: kota harus cocok + provinsi dijaga

# --- SUMBER PUBLIKASI -------------------------------------------------------
VIEWS = ["scopus", "googlescholar"]   # scopus, googlescholar, garuda, wos, rama, researches
PUB_PAGES = 1                  # halaman publikasi per sumber (10 pub/halaman)
PUB_LIMIT = 3                  # 2-3 publikasi relevan yang dilaporkan

# --- TEMPLATE KEBUTUHAN (yang mengisi kolom Bidang/Penelitian/Potensi) ------
PROFILE = {
    "bidang": "Farmasi bahan alam",
    "penelitian": "Ekstraksi dan antioksidan",
    "potensi_kebutuhan": (
        "Preparasi ekstrak, fenolik, flavonoid (skrining fitokimia, kadar fenolik "
        "& flavonoid total, uji antioksidan DPPH/ABTS/FRAP, standarisasi ekstrak)"
    ),
    "kata_kunci": [
        "farmasi", "pharmacy", "pharmaceutical", "farmakognosi", "fitokimia",
        "phytochem", "bahan alam", "natural product", "ekstrak", "extract",
        "ekstraksi", "extraction", "antioksidan", "antioxidant", "fenolik",
        "phenolic", "flavonoid", "alkaloid", "tanin", "terpenoid", "herbal",
        "jamu", "obat tradisional", "simplisia", "dpph", "abts", "frap",
        "fitomedisin", "makroalga", "mikroalga", "rumput laut", "seaweed",
        "immunomodulator", "biokimia", "biologi molekuler",
    ],
    "min_tinggi": 4,   # jumlah kata kunci cocok -> Prioritas Tinggi
    "min_sedang": 1,
}

# --- BATAS & PERFORMA -------------------------------------------------------
MAX_AUTHORS = 0                # 0 = semua; >0 untuk uji cepat
SAVE_EVERY = 25                # rebuild XLSX tiap N dosen
WORKERS = 3                    # thread paralel fase 2 (1 = berurutan)
DELAY = 1.2                    # jeda antar request (detik) — sopan ke server
TIMEOUT = 30
RETRIES = 4
CACHE_DIR = ".cache_sinta"     # "" = matikan cache
VERBOSE = False                # log detail per dosen
TIME_DEBUG = True              # cetak rincian waktu per dosen
USE_RELAY = False              # True = lewat *.translate.goog (kalau 403)
USE_SELENIUM_FALLBACK = True   # kalau 403 terus -> coba browser headless
HEADLESS = True
BLOCK_IMAGES = True

# --- OUTPUT -----------------------------------------------------------------
# Kosong = dibuat otomatis dari seed + wilayah, mis.
#   hasil/sinta_subjek45823_JABODETABEK.csv
# Ini mencegah hasil run lama terlihat seolah hasil run baru.
OUTPUT_CSV = ""
OUTPUT_XLSX = ""
OUTPUT_JSON = ""

CSV_FIELDS = [
    "Nama", "Institusi", "Bidang", "Penelitian", "Publikasi",
    "Potensi kebutuhan", "Kontak Email", "Status Email", "Kontak LinkedIn",
    "Kontak Google Scholar", "Prioritas", "Skor Prioritas", "Wilayah",
    "Kota/Kabupaten", "Provinsi", "Program Studi", "Subjek SINTA", "SINTA ID",
    "SINTA Score 3Yr", "H-index", "Kata Kunci Cocok", "Jumlah Publikasi",
    "Sinopsis Riset SINTA", "URL Profil",
]

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

# Selector SINTA (diverifikasi terhadap markup asli)
SEL_CARD = "div.list-item"                    # /subjects/detail, /authors, /affiliations
SEL_CARD_ALT = "div.au-item"                  # /affiliations/authors/<id>
SEL_NAME = "div.profile-name a[href*='/authors/profile/']"
SEL_AFFIL = "div.profile-affil a, div.affil-name a"
SEL_DEPT = "div.profile-dept a"
SEL_SUBJECTS = "ul.subject-list li a"
SEL_LOCATION = "div.affil-loc"
SEL_PAGINATION = "div.pagination-text"
SEL_PROFILE_H3 = "div.content-box h3, h3"
SEL_META_PROFILE = "div.meta-profile"
SEL_PUB_ITEM = "div.ar-list-item"
SEL_PUB_TITLE = "div.ar-title a"
SEL_PUB_META = "div.ar-meta"

_SELENIUM_OK = None


def _has_selenium():
    """Cek sekali saja: selenium terpasang atau tidak."""
    global _SELENIUM_OK
    if _SELENIUM_OK is None:
        try:
            import selenium  # noqa: F401
            _SELENIUM_OK = True
        except ImportError:
            _SELENIUM_OK = False
    return _SELENIUM_OK


SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_cache_warned = False

# =============================================================================
# UTIL TEKS
# =============================================================================

_WS = re.compile(r"\s+")


def clean(text):
    if not text:
        return ""
    return _WS.sub(" ", str(text).replace("\xa0", " ")).strip()


def to_number(text):
    """'1.281' -> 1281 ; '3,5' -> 3.5 ; '' -> 0"""
    if not text:
        return 0.0
    t = re.sub(r"[^\d,.]", "", str(text))
    if not t:
        return 0.0
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def fmt_eta(seconds):
    """432 -> '7m12s' ; 3725 -> '1j02m' ; None -> '--'."""
    if seconds is None or seconds != seconds or seconds < 0:
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, sec = divmod(seconds, 60)
    if m < 60:
        return f"{m}m{sec:02d}s"
    h, m = divmod(m, 60)
    return f"{h}j{m:02d}m"


def eta_from(elapsed, done, total):
    """Perkiraan sisa waktu berdasarkan laju sejauh ini."""
    if done <= 0 or total <= done:
        return 0 if total <= done else None
    return (elapsed / done) * (total - done)


def is_all(spec):
    return str(spec).strip().lower() in ("all", "semua", "0", "*", "max")


def page_list(spec, total_pages=None):
    """Daftar halaman yang akan diambil.

    "all"  -> berhenti tepat di total_pages (mis. 136), bukan 136+N.
    2      -> [1, 2]
    """
    if is_all(spec):
        return list(range(1, (total_pages or 1) + 1))
    try:
        return list(range(1, int(spec) + 1))
    except (TypeError, ValueError):
        return [1, 2]


def page_range(spec, total_pages=None):
    """2 -> range(1,3);  "all" -> range(1, total+1)."""
    if is_all(spec):
        return range(1, (total_pages or 100000) + 1)
    try:
        return range(1, int(spec) + 1)
    except (TypeError, ValueError):
        return range(1, 3)


def parse_sinta_url(url):
    """Urai URL SINTA yang di-paste user -> (jenis, id, page).

    Menerima juga link relay translate.goog.
    Contoh:
      /subjects/detail/45823?page=1        -> ("subject", "45823", 1)
      /affiliations/profile/430            -> ("affiliation", "430", 1)
      /affiliations/authors/476?page=3     -> ("affiliation", "476", 3)
      /authors/profile/5996301             -> ("author", "5996301", 1)
      /authors?q=farmasi                   -> ("search", "farmasi", 1)
    """
    from urllib.parse import unquote, urlparse, parse_qs

    u = urlparse(url.strip())
    path = unquote(u.path)
    qs = parse_qs(u.query)
    page = int(qs.get("page", ["1"])[0]) if qs.get("page", ["1"])[0].isdigit() else 1

    m = re.search(r"/subjects/detail/(\d+)", path)
    if m:
        return "subject", m.group(1), page
    m = re.search(r"/affiliations/profile/(\d+)", path)
    if m:
        return "affiliation", m.group(1), page
    m = re.search(r"/affiliations/authors/(\d+)", path)
    if m:
        return "affiliation", m.group(1), page
    m = re.search(r"/authors/profile/(\d+)", path)
    if m:
        return "author", m.group(1), page
    if "/authors" in path and qs.get("q"):
        return "search", qs["q"][0], page
    return None


def output_tag():
    """Nama file otomatis yang mencerminkan seed + wilayah."""
    parts = []
    if SUBJECT_IDS:
        parts.append("subjek" + "-".join(str(x) for x in SUBJECT_IDS[:3]))
    if AFFILIATION_IDS:
        parts.append("kampus" + "-".join(str(x) for x in AFFILIATION_IDS[:3]))
    if AUTHOR_IDS:
        parts.append("dosen" + "-".join(str(x) for x in AUTHOR_IDS[:3]))
    if SEARCH_TERMS:
        parts.append("cari_" + slug("-".join(SEARCH_TERMS[:2])))
    tag = "_".join(parts) or "sinta"
    reg = REGIONS[0] if len(REGIONS) == 1 else ("+".join(REGIONS) if REGIONS else "SEMUA")
    return f"{tag}_{slug(reg).upper()}"


def slug(text):
    """Untuk nama file debug."""
    return re.sub(r"[^a-z0-9]+", "_", clean(text).lower()).strip("_")[:60] or "page"


# =============================================================================
# WILAYAH: parse "KOTA ADM. JAKARTA BARAT - DKI JAKARTA, ID"
# =============================================================================

_PREFIX = re.compile(r"^(KOTA ADM\.?|KOTAMADYA|KABUPATEN|KAB\.?|KOTA)\s+", re.I)

REGION_PRESETS = {
    "JABODETABEK": {"JAKARTA", "BOGOR", "DEPOK", "TANGERANG", "BEKASI"},
    "DKI": {"JAKARTA"},
    "BODETABEK": {"BOGOR", "DEPOK", "TANGERANG", "BEKASI"},
    "JABAR": {
        "BANDUNG", "BOGOR", "DEPOK", "BEKASI", "TANGERANG", "CIREBON",
        "SUKABUMI", "TASIKMALAYA", "GARUT", "CIANJUR", "SUBANG", "PURWAKARTA",
        "KARAWANG", "INDRAMAYU", "MAJALENGKA", "SUMEDANG", "CIAMIS",
        "PANGANDARAN", "KUNINGAN", "BANJAR", "CILEGON", "SERANG",
    },
}

# penjaga provinsi: kota hanya dihitung bila provinsinya cocok
REGION_PROVINCES = {
    "JABODETABEK": {"DKI JAKARTA", "JAWA BARAT", "BANTEN"},
    "DKI": {"DKI JAKARTA"},
    "BODETABEK": {"JAWA BARAT", "BANTEN"},
    "JABAR": {"JAWA BARAT"},
}


def parse_location(raw):
    """-> dict(raw, kota, provinsi, wilayah:set, is_jabodetabek)"""
    info = {"raw": raw or "", "kota": "", "provinsi": "", "wilayah": set()}
    txt = clean(raw).upper()
    if not txt:
        return info
    txt = unicodedata.normalize("NFKD", txt)
    txt = re.sub(r",\s*ID$", "", txt)
    parts = [p.strip() for p in txt.split(" - ") if p.strip()]
    city_full = parts[0] if parts else ""
    province = parts[1] if len(parts) > 1 else ""
    city = _PREFIX.sub("", city_full).strip()
    tokens = set(city.replace(".", " ").split())

    regions = set()
    for name, cities in REGION_PRESETS.items():
        guard = REGION_PROVINCES.get(name, set())
        if guard and province and province not in guard:
            continue
        if any(c == city or c in tokens for c in cities):
            regions.add(name)

    info.update({"kota": city_full or city, "provinsi": province, "wilayah": regions})
    return info


def location_matches(loc, wanted):
    wanted = {w.strip().upper() for w in (wanted or []) if w and w.strip()}
    if not wanted or "INDONESIA" in wanted or "ALL" in wanted:
        return True
    return bool(loc["wilayah"] & wanted)


# =============================================================================
# HTTP: retry + cache + relay + selenium fallback + dump HTML
# =============================================================================

def _cache_path(path):
    if not CACHE_DIR:
        return None
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")[:120]
    return Path(CACHE_DIR) / f"{key}.html"


def _build_url(path, relay=None):
    relay = USE_RELAY if relay is None else relay
    path = path if path.startswith("/") else "/" + path
    if not relay:
        return BASE_URL + path
    sep = "&" if "?" in path else "?"
    return f"https://{RELAY_HOST}{path}{sep}_x_tr_sl=id&_x_tr_tl=en&_x_tr_hl=en"


def _fetch_selenium(path):
    """Fallback terakhir: browser sungguhan (gaya referensi)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if BLOCK_IMAGES:
        opts.add_experimental_option(
            "prefs", {"profile.managed_default_content_settings.images": 2}
        )
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(_build_url(path))
        time.sleep(2)
        return driver.page_source
    finally:
        driver.quit()


def throttle_up(factor=1.6, ceiling=6.0):
    """Naikkan DELAY global saat server membalas 429 (adaptif, tidak agresif)."""
    global DELAY
    DELAY = min(ceiling, max(DELAY, 1.0) * factor)


def dump_html(path, html, tag="debug"):
    """Simpan HTML saat parsing gagal, supaya selector bisa diperbaiki."""
    Path("debug").mkdir(exist_ok=True)
    out = Path("debug") / f"{tag}_{slug(path)}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  -> HTML mentah disimpan: {out}  (cari selector yang benar di sini)")
    return out


def get_soup(path, use_cache=True, tag="debug"):
    global USE_RELAY, _cache_warned
    cache_file = _cache_path(path)
    if use_cache and cache_file and cache_file.exists():
        return BeautifulSoup(cache_file.read_text(encoding="utf-8"), "lxml")

    url = _build_url(path)
    last_error = None
    for attempt in range(1, RETRIES + 1):
        if attempt > 1 or DELAY:
            time.sleep(DELAY + random.uniform(0, 0.25))
        try:
            resp = SESSION.get(url, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            print(f"  [jaringan] {exc} (percobaan {attempt}/{RETRIES})")
            time.sleep(2 ** attempt)
            continue

        if resp.status_code == 200:
            if cache_file:
                cache_file.write_text(resp.text, encoding="utf-8")
            return BeautifulSoup(resp.text, "lxml")

        if resp.status_code == 404:
            return BeautifulSoup("<html></html>", "lxml")

        if resp.status_code in (403, 429, 503):
            last_error = f"HTTP {resp.status_code}"

            # 429 = terlalu cepat (throttle relay/WAF) -> perlambat secara adaptif
            if resp.status_code == 429:
                throttle_up()
                retry_after = resp.headers.get("Retry-After", "")
                wait = int(retry_after) if retry_after.isdigit() else min(90, 8 * attempt)
                wait = max(wait, 5)
                print(f"  [429] throttled -> jeda {wait}s lalu coba lagi "
                      f"({attempt}/{RETRIES}) | DELAY sekarang {DELAY:.1f}s")
                time.sleep(wait)
                continue

            # 403 = WAF menolak IP -> auto-switch ke relay sekali saja
            if not USE_RELAY and not _cache_warned:
                print("  [403] WAF SINTA menolak IP ini -> coba relay *.translate.goog")
                USE_RELAY = _cache_warned = True
                url = _build_url(path)
                continue
            time.sleep(2 ** attempt)
            continue

        last_error = f"HTTP {resp.status_code}"
        time.sleep(2 ** attempt)

    # jalur terakhir: selenium (hanya kalau benar-benar terpasang)
    if USE_SELENIUM_FALLBACK and _has_selenium():
        print(f"  [fallback] mencoba Selenium untuk {path} ...")
        try:
            html = _fetch_selenium(path)
            if cache_file:
                cache_file.write_text(html, encoding="utf-8")
            return BeautifulSoup(html, "lxml")
        except Exception as exc:
            raise RuntimeError(
                f"Gagal mengambil {path}: {last_error}. Selenium juga gagal ({exc}).\n"
                "Jalankan dari jaringan lokal Indonesia, atau pakai --relay, "
                "atau `pip install selenium` untuk fallback browser."
            )
        except ImportError:
            pass  # selenium tidak terpasang -> lanjut ke pesan error di bawah

    hint = "" if _has_selenium() else " (opsional: `pip install selenium` untuk fallback browser)"
    raise RuntimeError(f"Gagal mengambil {path}: {last_error}.{hint}")


# =============================================================================
# PARSER (BeautifulSoup)
# =============================================================================

def parse_cards(html_soup, source_path=""):
    """Kartu dosen dari /subjects/detail, /authors, /affiliations/authors/<id>."""
    cards = html_soup.select(SEL_CARD) or html_soup.select(SEL_CARD_ALT)
    items = []
    for card in cards:
        name_a = card.select_one(SEL_NAME)
        if not name_a:
            continue
        href = name_a.get("href", "")
        sinta_id = ""
        m = re.search(r"/authors/profile/(\d+)", href)
        if m:
            sinta_id = m.group(1)

        affil_a = card.select_one(SEL_AFFIL)
        affil_name = clean(affil_a.get_text()) if affil_a else ""
        affil_id = ""
        if affil_a:
            m = re.search(r"/affiliations/profile/(\d+)", affil_a.get("href", ""))
            affil_id = m.group(1) if m else ""

        dept_a = card.select_one(SEL_DEPT)

        scores = {}
        for num in card.select("div.pr-num"):
            sib = num.find_next_sibling("div")
            if sib:
                scores[clean(sib.get_text())] = clean(num.get_text())

        hindex = {}
        for span in card.select("div.profile-hindex span"):
            txt = clean(span.get_text())
            if ":" in txt:
                k, v = txt.split(":", 1)
                hindex[clean(k)] = clean(v)

        items.append({
            "sinta_id": sinta_id,
            "nama": clean(name_a.get_text()),
            "institusi": affil_name,
            "institusi_id": affil_id,
            "program_studi": clean(dept_a.get_text()) if dept_a else "",
            "subjek": [clean(a.get_text()) for a in card.select(SEL_SUBJECTS)],
            "lokasi": clean(card.select_one(SEL_LOCATION).get_text())
            if card.select_one(SEL_LOCATION) else "",
            "skor": scores,
            "hindex": hindex,
        })

    if cards and not items:
        dump_html(source_path, str(html_soup), tag="parse_cards_kosong")
    return items


def parse_total_pages(html_soup):
    node = html_soup.select_one(SEL_PAGINATION)
    if not node:
        return 1, 0
    text = clean(node.get_text())
    mp = re.search(r"Page\s+[\d.]+\s+of\s+([\d.]+)", text)
    mt = re.search(r"Total Records\s+([\d.]+)", text)
    as_int = lambda s: int(s.replace(".", "")) if s else 0
    return (as_int(mp.group(1)) if mp else 1, as_int(mt.group(1)) if mt else 0)


def parse_affiliation_location(html_soup):
    name = clean((html_soup.select_one("div.univ-name h3") or {}).get_text()
                 if html_soup.select_one("div.univ-name h3") else "")
    node = html_soup.select_one("div.meta-profile a.affil-loc") or \
        html_soup.select_one("span.affil-loc")
    return name, clean(node.get_text()) if node else ""


def parse_profile(html_soup, source_path="", view="scopus"):
    """-> dict profil + list publikasi."""
    h3 = html_soup.select_one(SEL_PROFILE_H3)
    prof = {
        "nama": clean(h3.get_text()) if h3 else "",
        "institusi": "", "institusi_id": "", "program_studi": "", "sinta_id": "",
        "subjek": [], "skor": {}, "lokasi": "", "publikasi": [], "riset": [],
    }

    meta = html_soup.select_one(SEL_META_PROFILE)
    if meta:
        for a in meta.select("a"):
            icon = a.select_one("i")
            icon_cls = " ".join(icon.get("class", [])) if icon else ""
            text = clean(a.get_text())
            if "el-map-marker" in icon_cls:
                prof["institusi"] = text
                m = re.search(r"/affiliations/profile/(\d+)", a.get("href", ""))
                prof["institusi_id"] = m.group(1) if m else ""
            elif "el-child" in icon_cls:
                prof["program_studi"] = text
            elif "el-user" in icon_cls:
                m = re.search(r"(\d+)", text)
                prof["sinta_id"] = m.group(1) if m else ""

    prof["subjek"] = [clean(a.get_text())
                      for a in html_soup.select("div.profile-subject " + SEL_SUBJECTS)]

    for num in html_soup.select("div.stat-profile div.pr-num"):
        sib = num.find_next_sibling("div", class_="pr-txt")
        if sib:
            prof["skor"][clean(sib.get_text())] = clean(num.get_text())

    # publikasi
    for item in html_soup.select(SEL_PUB_ITEM):
        title_a = item.select_one(SEL_PUB_TITLE)
        if not title_a:
            continue
        year_a = item.select_one("a.ar-year")
        venue_a = item.select_one("a.ar-pub")
        quart_a = item.select_one("a.ar-quartile")
        cited_a = item.select_one("a.ar-cited")
        meta_div = item.select_one(SEL_PUB_META)
        meta_txt = clean(meta_div.get_text()) if meta_div else ""

        venue = clean(venue_a.get_text()) if venue_a else ""
        if not venue:  # Google Scholar: "Authors : ... Jurnal 6 (1), 407-416, 2026"
            for a in item.select(SEL_PUB_META + " a"):
                txt = clean(a.get_text())
                if re.search(r"\d{4}$", txt) and "," in txt:
                    venue = txt
                    break

        prof["publikasi"].append({
            "judul": clean(title_a.get_text()),
            "tahun": re.sub(r"\D", "", clean(year_a.get_text())) if year_a else "",
            "venue": venue,
            "kuartil": clean(quart_a.get_text()) if quart_a else "",
            "sitasi": clean(cited_a.get_text()) if cited_a else "",
            "sumber": view,
            "url": title_a.get("href", ""),
        })

    if view == "researches":
        prof["riset"] = [clean(a.get_text())
                         for a in html_soup.select(SEL_PUB_TITLE)]

    if not prof["nama"] and not prof["publikasi"]:
        dump_html(source_path, str(html_soup), tag="parse_profile_kosong")
    return prof


# =============================================================================
# ENRICHMENT: kata kunci -> Bidang/Penelitian/Potensi/Prioritas/Kontak
# =============================================================================

AFFILIATION_DOMAINS = {
    "universitas indonesia": "ui.ac.id",
    "institut pertanian bogor": "ipb.ac.id",
    "universitas negeri jakarta": "unj.ac.id",
    "uin syarif hidayatullah jakarta": "uinjkt.ac.id",
    "universitas bina nusantara": "binus.ac.id",
    "universitas gunadarma": "gunadarma.ac.id",
    "universitas tarumanagara": "tarumanagara.ac.id",
    "universitas trisakti": "trisakti.ac.id",
    "universitas yarsi": "yarsi.ac.id",
    "universitas katolik indonesia atma jaya": "atmajaya.ac.id",
    "universitas muhammadiyah prof. dr. hamka": "uhamka.ac.id",
    "universitas muhammadiyah jakarta": "umj.ac.id",
    "universitas mercu buana": "mercubuana.ac.id",
    "universitas esa unggul": "esaunggul.ac.id",
    "universitas pancasila": "univpancasila.ac.id",
    "universitas pembangunan nasional veteran jakarta": "upnvj.ac.id",
    "universitas islam negeri jakarta": "uinjkt.ac.id",
}


def match_keywords(texts):
    blob = clean(" | ".join(t for t in texts if t)).lower()
    return [kw for kw in PROFILE["kata_kunci"] if clean(kw).lower() in blob]


def build_match(texts, is_jabodetabek=False, pub_count=0, score_3yr=0.0, hindex=0):
    hits = match_keywords(texts)
    base = 55 if len(hits) >= PROFILE["min_tinggi"] else (
        35 if len(hits) >= PROFILE["min_sedang"] else 10)
    if is_jabodetabek:
        base += 10
    base += min(pub_count, 10) * 2
    base += min(hindex, 15)
    if score_3yr >= 500:
        base += 10
    elif score_3yr >= 100:
        base += 5
    skor = max(0, min(100, base))
    prioritas = "Tinggi" if skor >= 70 else ("Sedang" if skor >= 45 else "Rendah")
    return {"hits": hits, "skor": skor, "prioritas": prioritas}


def rank_publications(pubs, limit):
    """Kata kunci di judul > tahun terbaru."""
    def key(p):
        hit = 1 if match_keywords([p.get("judul", "")]) else 0
        try:
            year = int(p.get("tahun") or 0)
        except ValueError:
            year = 0
        return (-hit, -year)
    return sorted(pubs, key=key)[:limit]


def _key(text):
    """'Universitas Muhammadiyah Prof Dr Hamka' -> 'universitasmuhammadiyahprofdrhamka'
    (abaikan titik/spasi/koma supaya 'Prof. Dr.' tetap cocok)."""
    return re.sub(r"[^a-z0-9]", "", clean(text).lower())


def guess_domain(institusi):
    a = _key(institusi)
    if not a:
        return ""
    for name, dom in AFFILIATION_DOMAINS.items():
        k = _key(name)
        if k and (k in a or a in k):
            return dom
    return ""


def guess_email(nama, domain):
    if not domain:
        return ""
    parts = [p for p in re.split(r"[^A-Za-z]+", clean(nama).lower()) if len(p) > 1]
    if not parts:
        return ""
    local = parts[0] if len(parts) == 1 else f"{parts[0]}.{parts[-1]}"
    return f"{local}@{domain}"


def linkedin_url(nama, institusi):
    from urllib.parse import quote_plus
    return ("https://www.linkedin.com/search/results/people/?keywords="
            + quote_plus(f"{nama} {institusi}".strip()))


def scholar_url(nama):
    from urllib.parse import quote_plus
    return ("https://scholar.google.com/citations?view_op=search_authors&mauthors="
            + quote_plus(nama))


# =============================================================================
# TIMER (gaya referensi)
# =============================================================================

class StepTimer:
    def __init__(self):
        self._last = time.time()
        self.marks = []

    def mark(self, label):
        now = time.time()
        self.marks.append((label, now - self._last))
        self._last = now

    def report(self, n):
        if not TIME_DEBUG:
            return
        parts = " | ".join(f"{label}={dt:.2f}s" for label, dt in self.marks)
        total = sum(dt for _, dt in self.marks)
        print(f"[timing] #{n}: {parts} | total={total:.2f}s")


def log(*args):
    if VERBOSE:
        print(*args)

# =============================================================================
# STEP 1 — KUMPULKAN KANDIDAT
# =============================================================================


FAILED_PAGES = []


def collect_campus_candidates():
    """Mode KAMPUS: sapu daftar institusi -> saring wilayah SEKALI ->
    buka daftar dosen hanya untuk kampus yang lolos.

    Semua dosen yang terkumpul otomatis berada di wilayah target, jadi tidak
    ada request lokasi per dosen dan tidak ada halaman subjek yang terbuang.
    """
    regions = [r.upper() for r in (REGIONS or ["INDONESIA"])]
    print(f"  mode kampus: memindai daftar institusi (wilayah {regions})")

    kept_campuses, scanned = [], 0
    t0 = time.time()
    total_pages = None
    page = 1
    while True:
        if AFFILIATION_SCAN_PAGES and page > AFFILIATION_SCAN_PAGES:
            break
        path = f"/affiliations?page={page}"
        try:
            soup = get_soup(path)
        except Exception as exc:
            print(f"    !! halaman institusi {page} gagal: {str(exc)[:80]}")
            FAILED_PAGES.append(path)
            page += 1
            continue

        cards = soup.select("div.list-item")
        if not cards:
            break
        for card in cards:
            link = card.select_one("div.affil-name a[href*='/affiliations/profile/']")
            loc_node = card.select_one("div.affil-loc")
            if not link:
                continue
            scanned += 1
            loc = parse_location(clean(loc_node.get_text()) if loc_node else "")
            if location_matches(loc, regions):
                aid = re.search(r"/affiliations/profile/(\d+)", link.get("href", ""))
                if aid:
                    name = clean(link.get_text())
                    AFFIL_LOCATION_CACHE[aid.group(1)] = loc["raw"]
                    kept_campuses.append((aid.group(1), name, loc))

        mp = re.search(r"Page\s+[\d.]+\s+of\s+([\d.]+)", clean(soup.select_one(SEL_PAGINATION).get_text())
                       if soup.select_one(SEL_PAGINATION) else "")
        total_pages = int(mp.group(1).replace(".", "")) if mp else page
        eta = eta_from(time.time() - t0, page, AFFILIATION_SCAN_PAGES or total_pages)
        print(f"    institusi hal {page}/{AFFILIATION_SCAN_PAGES or total_pages}"
              f" -> {len(kept_campuses)} kampus cocok | ETA {fmt_eta(eta)}")
        if page >= total_pages:
            break
        page += 1

    print(f"  {scanned} institusi dipindai -> {len(kept_campuses)} di {regions}")
    if not kept_campuses:
        return []

    # kurasi: kampus teratas saja kalau dibatasi
    if MAX_CAMPUSES:
        kept_campuses = kept_campuses[:MAX_CAMPUSES]
        print(f"  dibatasi {MAX_CAMPUSES} kampus pertama")

    candidates, seen = [], set()
    for i, (aid, name, loc) in enumerate(kept_campuses, 1):
        print(f"    [{i}/{len(kept_campuses)}] {name} — {loc['kota']}")
        aff_total = None
        for pageno in page_range(AFFILIATION_PAGES, aff_total):
            if aff_total and pageno > aff_total:
                break
            path = f"/affiliations/authors/{aid}?page={pageno}&sort=1"
            try:
                soup = get_soup(path)
            except Exception:
                FAILED_PAGES.append(path)
                continue
            items = parse_cards(soup, path)
            if not items:
                break
            for it in items:
                if it["sinta_id"] and it["sinta_id"] not in seen:
                    seen.add(it["sinta_id"])
                    it["institusi"] = it["institusi"] or name
                    it["institusi_id"] = it["institusi_id"] or aid
                    it["lokasi"] = it["lokasi"] or loc["raw"]
                    candidates.append(it)
    return candidates


def collect_candidates():
    """Sapu daftar dosen. Halaman yang gagal TIDAK menghentikan proses --
    dicatat di FAILED_PAGES dan dilewati (cache membuat rerun melanjutkan
    dari halaman yang belum terambil)."""
    if str(SOURCE_MODE).lower().startswith("kampus"):
        return collect_campus_candidates()

    candidates = []
    seen = set()

    def safe_soup(path):
        try:
            return get_soup(path)
        except Exception as exc:
            FAILED_PAGES.append(path)
            print(f"    !! dilewati {path}: {str(exc)[:110]}")
            return None

    def add(item):
        if item["sinta_id"] and item["sinta_id"] not in seen:
            seen.add(item["sinta_id"])
            candidates.append(item)

    for sid in SUBJECT_IDS:
        total_pages = None
        t_seed = time.time()
        pages_done = 0
        # halaman 1 dulu: dari situ total_pages diketahui -> tidak pernah
        # melewati halaman terakhir (dulu bisa lanjut ke 137, 138, ...)
        page_iter = None if is_all(SUBJECT_PAGES) else page_list(SUBJECT_PAGES)
        page = 1
        while True:
            if page_iter is not None and page not in page_iter:
                break
            path = f"/subjects/detail/{sid}?page={page}&sort=1"
            soup = safe_soup(path)
            if soup is None:
                continue
            items = parse_cards(soup, path)
            total_pages, total_records = parse_total_pages(soup)
            if page == 1:
                print(f"  subjek {sid}: {total_pages} halaman / {total_records} dosen")
                print(f"    perkiraan fase 1: ~{total_pages * (DELAY + 0.35):.0f}s "
                      f"({total_pages} halaman @ ~{DELAY + 0.35:.1f}s/halaman)")
            pages_done += 1
            eta = eta_from(time.time() - t_seed, pages_done, total_pages or pages_done)
            print(f"    hal {page}/{total_pages} -> {len(items)} kartu"
                  f" | ETA fase 1 {fmt_eta(eta)}")
            if not items:
                if total_pages and page < total_pages:
                    FAILED_PAGES.append(path)   # bukan halaman terakhir -> gagal
                else:
                    break
            for it in items:
                add(it)
            page += 1
            if total_pages and page > total_pages:
                print(f"    fase 1 selesai: {total_pages}/{total_pages} halaman "
                      f"dalam {time.time() - t_seed:.0f}s")
                break

    for aid in AFFILIATION_IDS:
        aff_soup = safe_soup(f"/affiliations/profile/{aid}")
        aff_name, aff_loc = parse_affiliation_location(aff_soup) if aff_soup else ("", "")
        print(f"  institusi {aid}: {aff_name} | {aff_loc}")
        aff_total = None
        for page in page_range(AFFILIATION_PAGES, aff_total):
            if aff_total and page > aff_total:
                break
            path = f"/affiliations/authors/{aid}?page={page}&sort=1"
            soup = safe_soup(path)
            if soup is None:
                continue
            items = parse_cards(soup, path)
            print(f"    institusi {aid} hal {page} -> {len(items)} kartu")
            if not items:
                continue
            for it in items:
                it["institusi"] = it["institusi"] or aff_name
                it["institusi_id"] = it["institusi_id"] or aid
                it["lokasi"] = it["lokasi"] or aff_loc
                add(it)

    for kw in SEARCH_TERMS:
        for page in page_range(SEARCH_PAGES):
            path = f"/authors?page={page}&q={kw}&sort=1"
            soup = safe_soup(path)
            if soup is None:
                continue
            items = parse_cards(soup, path)
            print(f"  cari '{kw}' hal {page} -> {len(items)} kartu")
            if not items:
                continue
            for it in items:
                add(it)

    for author_id in AUTHOR_IDS:
        path = f"/authors/profile/{author_id}"
        prof = parse_profile(get_soup(path), path)
        add({
            "sinta_id": prof["sinta_id"] or author_id,
            "nama": prof["nama"],
            "institusi": prof["institusi"],
            "institusi_id": prof["institusi_id"],
            "program_studi": prof["program_studi"],
            "subjek": prof["subjek"],
            "lokasi": prof["lokasi"],
            "skor": prof["skor"],
            "hindex": {},
        })

    return candidates


def resolve_location(cand):
    """Kartu daftar kadang tanpa lokasi -> buka profil institusi (sekali per ID)."""
    loc = parse_location(cand.get("lokasi", ""))
    if loc["raw"] or not cand.get("institusi_id"):
        return loc
    cached = AFFIL_LOCATION_CACHE.get(cand["institusi_id"])
    if cached is None:
        try:
            _, text = parse_affiliation_location(
                get_soup(f"/affiliations/profile/{cand['institusi_id']}"))
        except Exception as exc:
            print(f"    !! lokasi {cand['institusi_id']} gagal: {str(exc)[:80]}")
            AFFIL_LOCATION_CACHE[cand["institusi_id"]] = ""   # jangan ulangi terus
            return parse_location("")
        cached = text
        AFFIL_LOCATION_CACHE[cand["institusi_id"]] = cached
    return parse_location(cached)


AFFIL_LOCATION_CACHE = {}


def filter_by_region(candidates, regions):
    """Saring kandidat berdasarkan wilayah institusi.

    Optimasi penting: lokasi hanya diambil SEKALI PER INSTITUSI (bukan per
    dosen). Dulu 1.294 dosen = 1.294 request tanpa progress bar -> terlihat
    macet. Sekarang jumlah request = jumlah institusi unik, dijalankan
    paralel, dengan progress + ETA.
    """
    from concurrent.futures import ThreadPoolExecutor

    # kelompokkan: institusi_id -> daftar kandidat
    by_affil, unknown = {}, []
    for c in candidates:
        if parse_location(c.get("lokasi", ""))["raw"]:
            unknown.append(c)          # lokasi sudah ada di kartu, tanpa request
            continue
        aid = c.get("institusi_id")
        if aid:
            by_affil.setdefault(aid, []).append(c)
        else:
            unknown.append(c)

    affil_ids = list(by_affil)
    print(f"  dosen: {len(candidates)} | institusi unik: {len(affil_ids)} "
          f"| lokasi sudah ada di kartu: {len(unknown)}")
    if affil_ids:
        est = len(affil_ids) * (DELAY + 0.35) / max(1, WORKERS)
        print(f"  perkiraan cek lokasi: ~{fmt_eta(est)} "
              f"({len(affil_ids)} request ÷ {WORKERS} thread)")

    # ambil lokasi per institusi (paralel, dengan penghitung progres)
    todo = [a for a in affil_ids if a not in AFFIL_LOCATION_CACHE]
    if todo:
        done = [0]
        lock2 = threading.Lock()
        t_start = time.time()

        def grab(aid):
            try:
                _, text = parse_affiliation_location(
                    get_soup(f"/affiliations/profile/{aid}"))
            except Exception:
                text = ""
            with lock2:
                done[0] += 1
                n = done[0]
                eta = eta_from(time.time() - t_start, n, len(todo))
                print(f"    lokasi {n}/{len(todo)} (institusi {aid}) "
                      f"-> {parse_location(text)['kota'] or '?'} | ETA {fmt_eta(eta)}")
            return aid, text

        with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as pool:
            for aid, text in pool.map(grab, todo):
                AFFIL_LOCATION_CACHE[aid] = text

    kept, dropped, unknown_region = [], 0, 0
    for c in unknown + [c for aid in affil_ids for c in by_affil[aid]]:
        if c.get("institusi_id") and not parse_location(c.get("lokasi", ""))["raw"]:
            text = AFFIL_LOCATION_CACHE.get(c["institusi_id"], "")
            loc = parse_location(text)
            if not text:
                unknown_region += 1
        else:
            loc = parse_location(c.get("lokasi", ""))
        if location_matches(loc, regions):
            kept.append(c)
        else:
            dropped += 1
    print(f"  hasil filter {regions}: {len(kept)} lolos, {dropped} dilewati"
          + (f", {unknown_region} lokasi tak diketahui (dibuang)" if unknown_region else ""))
    return kept

# =============================================================================
# STEP 2 — PROFIL + PUBLIKASI + ENRICHMENT
# =============================================================================


def fetch_profile(sinta_id):
    merged = None
    for view in VIEWS:
        for page in range(1, PUB_PAGES + 1):
            path = f"/authors/profile/{sinta_id}?view={view}"
            if page > 1:
                path += f"&page={page}"
            prof = parse_profile(get_soup(path), path, view=view)
            if not prof["nama"] and not prof["publikasi"]:
                break
            if merged is None:
                merged = prof
            else:
                merged["publikasi"].extend(prof["publikasi"])
                merged["subjek"] = list(dict.fromkeys(
                    merged["subjek"] + prof["subjek"]))
                merged["riset"] = merged["riset"] or prof["riset"]
            if not prof["publikasi"]:
                break

    # buang duplikat antar sumber (judul+tahun sama, mis. scopus & GS)
    if merged:
        seen, uniq = set(), []
        for item in merged.get("publikasi", []):
            key = (_key(item.get("judul", "")), item.get("tahun", ""))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(item)
        merged["publikasi"] = uniq
    return merged or {}


def build_row(cand, timer):
    prof = fetch_profile(cand["sinta_id"])
    timer.mark("profil+publikasi")

    loc = resolve_location(cand)
    timer.mark("lokasi")

    nama = prof.get("nama") or cand["nama"]
    institusi = prof.get("institusi") or cand["institusi"]
    subjek = prof.get("subjek") or cand.get("subjek", [])
    pubs = prof.get("publikasi", [])

    hits = match_keywords([nama, institusi, prof.get("program_studi", "")]
                          + subjek + prof.get("riset", [])
                          + [p["judul"] for p in pubs])
    skor_3yr = to_number(
        cand.get("skor", {}).get("SINTA Score 3Yr")
        or prof.get("skor", {}).get("SINTA Score 3Yr"))
    hindex = 0
    for k, v in (cand.get("hindex") or {}).items():
        if any(t in k.lower() for t in ("scopus", "gs", "google")):
            hindex = int(to_number(v))

    m = build_match(
        [nama, institusi, prof.get("program_studi", "")] + subjek
        + prof.get("riset", []) + [p["judul"] for p in pubs],
        is_jabodetabek="JABODETABEK" in loc["wilayah"],
        pub_count=len(pubs), score_3yr=skor_3yr, hindex=hindex,
    )
    top_pubs = rank_publications(pubs, PUB_LIMIT)
    domain = guess_domain(institusi)
    email = guess_email(nama, domain)
    timer.mark("enrichment")

    return {
        "Nama": nama,
        "Institusi": institusi,
        "Bidang": PROFILE["bidang"],
        "Penelitian": PROFILE["penelitian"],
        "Publikasi": " || ".join(
            f"{p['judul']} ({p['tahun']})" + (f" - {p['venue']}" if p["venue"] else "")
            for p in top_pubs),
        "Potensi kebutuhan": PROFILE["potensi_kebutuhan"],
        "Kontak Email": email,
        "Status Email": ("dugaan (pola nama@domain institusi) - verifikasi manual"
                         if email else "belum ada - domain institusi belum dipetakan"),
        "Kontak LinkedIn": linkedin_url(nama, institusi),
        "Kontak Google Scholar": scholar_url(nama),
        "Prioritas": m["prioritas"],
        "Skor Prioritas": m["skor"],
        "Wilayah": ",".join(sorted(loc["wilayah"])),
        "Kota/Kabupaten": loc["kota"],
        "Provinsi": loc["provinsi"],
        "Program Studi": prof.get("program_studi") or cand.get("program_studi", ""),
        "Subjek SINTA": "; ".join(subjek),
        "SINTA ID": cand["sinta_id"],
        "SINTA Score 3Yr": int(skor_3yr),
        "H-index": hindex,
        "Kata Kunci Cocok": "; ".join(m["hits"]),
        "Jumlah Publikasi": len(pubs),
        "Sinopsis Riset SINTA": "; ".join(prof.get("riset", [])[:5]),
        "URL Profil": f"{BASE_URL}/authors/profile/{cand['sinta_id']}",
        "_is_jabodetabek": "JABODETABEK" in loc["wilayah"],
    }


# =============================================================================
# OUTPUT: CSV inkremental + XLSX berkala (pola referensi)
# =============================================================================

import threading

all_rows = []
csv_file = None
csv_writer = None
_csv_lock = threading.Lock()


def open_output():
    global csv_file, csv_writer
    Path(OUTPUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    csv_file = open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig")
    csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, restval="")
    csv_writer.writeheader()
    csv_file.flush()


def append_row(row):
    # dipanggil dari beberapa thread -> kunci agar CSV tidak rusak
    with _csv_lock:
        all_rows.append(row)
        csv_writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
        csv_file.flush()


def finalize():
    """CSV = sumber kebenaran (crash-safe). XLSX/JSON dibangun ulang dari CSV."""
    if csv_file:
        csv_file.flush()
    try:
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", sep=",")
        try:
            df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
        except Exception:
            pass
        df.to_excel(OUTPUT_XLSX, index=False)
        Path(OUTPUT_JSON).write_text(
            json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"Tidak bisa membangun {OUTPUT_XLSX} ({exc}) -- "
              f"progres tetap aman di {OUTPUT_CSV}")


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scraper SINTA satu file (BeautifulSoup)")
    p.add_argument("--subject", action="append", default=[])
    p.add_argument("--affiliation", action="append", default=[])
    p.add_argument("--author", action="append", default=[])
    p.add_argument("--search", action="append", default=[])
    p.add_argument("--url", action="append", default=[], metavar="URL",
                   help="tempel URL SINTA apa saja (subjects/affiliations/authors)")
    p.add_argument("--pages", default="", metavar="N|all",
                   help="halaman daftar per seed: angka, atau 'all' untuk semua halaman")
    p.add_argument("--mode", choices=["auto", "subjek", "kampus"], default="",
                   help="sumber kandidat: subjek (default) atau kampus (Jabodetabek dulu)")
    p.add_argument("--max-campuses", type=int, default=0,
                   help="mode kampus: batasi jumlah kampus")
    p.add_argument("--full", action="store_true",
                   help="fase 2 untuk SEMUA kandidat lolos filter (abaikan limit)")
    p.add_argument("--region", action="append", default=[],
                   help="JABODETABEK | DKI | BODETABEK | JABAR | INDONESIA")
    p.add_argument("--views", default="", help="scopus,googlescholar,...")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default="", help="prefix output, mis. hasil/ui")
    p.add_argument("--relay", action="store_true")
    p.add_argument("--workers", type=int, default=0,
                   help="thread paralel fase 2 (default dari CONFIG)")
    p.add_argument("--delay", type=float, default=0.0,
                   help="jeda antar request (detik); 0 = pakai CONFIG")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def apply_args(a):
    global SUBJECT_IDS, AFFILIATION_IDS, AUTHOR_IDS, SEARCH_TERMS
    global SUBJECT_PAGES, AFFILIATION_PAGES, SEARCH_PAGES, REGIONS
    global VIEWS, MAX_AUTHORS, USE_RELAY, CACHE_DIR, VERBOSE, DELAY, TWO_PHASE
    global WORKERS, SOURCE_MODE, AFFILIATION_SCAN_PAGES, MAX_CAMPUSES
    global OUTPUT_CSV, OUTPUT_XLSX, OUTPUT_JSON

    # URL yang di-paste (mis. dari address bar) -> seed
    for raw in a.url or []:
        parsed = parse_sinta_url(raw)
        if not parsed:
            print(f"[peringatan] URL tidak dikenali: {raw}")
            continue
        kind, value, page = parsed
        if kind == "subject" and value not in SUBJECT_IDS:
            SUBJECT_IDS = SUBJECT_IDS + [value] if a.subject else [value]
        elif kind == "affiliation" and value not in AFFILIATION_IDS:
            AFFILIATION_IDS = AFFILIATION_IDS + [value] if a.affiliation else [value]
        elif kind == "author" and value not in AUTHOR_IDS:
            AUTHOR_IDS = AUTHOR_IDS + [value] if a.author else [value]
        elif kind == "search" and value not in SEARCH_TERMS:
            SEARCH_TERMS = SEARCH_TERMS + [value] if a.search else [value]
        print(f"[url] {kind} = {value} (mulai halaman {page})")

    if a.subject:
        SUBJECT_IDS = a.subject
    if a.affiliation:
        AFFILIATION_IDS = a.affiliation
    if a.author:
        AUTHOR_IDS = a.author
    if a.search:
        SEARCH_TERMS = a.search
    if a.pages:
        SUBJECT_PAGES = AFFILIATION_PAGES = SEARCH_PAGES = a.pages
    if a.region:
        REGIONS = a.region
    if a.views:
        VIEWS = [v.strip() for v in a.views.split(",") if v.strip()]
    if a.limit:
        MAX_AUTHORS = a.limit
    if a.full:
        TWO_PHASE = False
    if a.workers:
        WORKERS = a.workers
    if a.max_campuses:
        MAX_CAMPUSES = a.max_campuses
    if a.mode:
        SOURCE_MODE = a.mode
    elif str(SOURCE_MODE).lower() == "auto":
        SOURCE_MODE = "subjek" if SUBJECT_IDS else "kampus"
    if a.relay:
        USE_RELAY = True
    if a.delay:
        DELAY = a.delay
    if a.no_cache:
        CACHE_DIR = ""
    if a.verbose:
        VERBOSE = True
    # nama file: eksplisit (--out) atau otomatis dari seed+wilayah
    prefix = a.out if a.out else f"hasil/sinta_{output_tag()}"
    OUTPUT_CSV = prefix + ".csv"
    OUTPUT_XLSX = prefix + ".xlsx"
    OUTPUT_JSON = prefix + ".json"


def main():
    global USE_SELENIUM_FALLBACK

    args = parse_args()
    apply_args(args)

    # autorun.py bisa mematikan fallback browser lewat environment variable
    if os.environ.get("SINTA_SELENIUM_FALLBACK") == "0":
        USE_SELENIUM_FALLBACK = False

    print("=" * 70)
    print("SINTA SCRAPER (BeautifulSoup, satu file)")
    print(f"  seed     : subjek={SUBJECT_IDS} institusi={AFFILIATION_IDS} "
          f"author={AUTHOR_IDS} cari={SEARCH_TERMS}")
    print(f"  wilayah  : {REGIONS or 'SEMUA'}")
    print(f"  publikasi: {VIEWS} ({PUB_PAGES} hal, tampil {PUB_LIMIT})")
    print(f"  output   : {OUTPUT_CSV} -> {OUTPUT_XLSX}")
    print("=" * 70)

    open_output()
    started = time.time()

    try:
        print("\nSTEP 1 — mengumpulkan kandidat dosen (fase 1: daftar saja)")
        candidates = collect_candidates()
        print(f"  total kandidat unik: {len(candidates)}")

        if REGIONS and "INDONESIA" not in [r.upper() for r in REGIONS]:
            print(f"\nSTEP 1b — cek lokasi institusi (filter {REGIONS})")
            candidates = filter_by_region(candidates, REGIONS)

        # Di mode dua fase, MAX_AUTHORS membatasi dosen yang PROFILNYA dibuka
        # (fase 2), bukan jumlah kartu yang discan di fase 1 -- inilah yang
        # membuat "1.355 dosen / 136 halaman" bisa dijelajahi dengan wajar.
        if MAX_AUTHORS and not TWO_PHASE:
            candidates = candidates[:MAX_AUTHORS]

        if not candidates:
            print("\nTidak ada dosen lolos filter.")
            print("Coba: pages = all, region = INDONESIA, atau tambah subject_ids.")
            finalize()
            return 0

        target = candidates[:MAX_AUTHORS] if (MAX_AUTHORS and TWO_PHASE) else candidates
        if len(target) < len(candidates):
            print(f"  fase 2 dibatasi {len(target)} dosen dari {len(candidates)} "
                  f"kandidat lolos (limit={MAX_AUTHORS})")

        est_per = 1.6  # detik per dosen (1 request profil; 2 kalau views >1)
        est = len(target) * est_per / max(1, WORKERS)
        print(f"\nSTEP 2 — buka profil + publikasi ({len(target)} dosen, "
              f"{WORKERS} thread)")
        print(f"  perkiraan: ~{fmt_eta(est)} "
              f"({est_per:.1f}s/dosen ÷ {WORKERS} thread)")
        candidates = target
        t2 = time.time()
        done = 0
        lock = threading.Lock()

        def work(cand):
            timer = StepTimer()
            row = build_row(cand, timer)
            return row, timer

        total_n = len(candidates)
        if WORKERS <= 1:
            for i, cand in enumerate(candidates, 1):
                print(f"  [{i}/{total_n}] {cand['nama']} ({cand['institusi']})")
                try:
                    row, timer = work(cand)
                    append_row(row)
                    eta = eta_from(time.time() - t2, i, total_n)
                    print(f"        -> {row['Prioritas']:6s} skor {row['Skor Prioritas']:3d}"
                          f" | {row['Kota/Kabupaten']} | {row['Jumlah Publikasi']} pub"
                          f" | ETA {fmt_eta(eta)}")
                except Exception as exc:
                    print(f"        !! gagal: {exc}")
                timer.report(i)
                if i % SAVE_EVERY == 0:
                    finalize()
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures = {pool.submit(work, c): c for c in candidates}
                for fut in as_completed(futures):
                    cand = futures[fut]
                    with lock:
                        done += 1
                        n = done
                    try:
                        row, timer = fut.result()
                        append_row(row)
                        eta = eta_from(time.time() - t2, n, total_n)
                        print(f"  [{n}/{total_n}] {row['Nama'][:28]:30s}"
                              f" -> {row['Prioritas']:6s} skor {row['Skor Prioritas']:3d}"
                              f" | {row['Kota/Kabupaten']} | {row['Jumlah Publikasi']} pub"
                              f" | ETA {fmt_eta(eta)}")
                        timer.report(n)
                    except Exception as exc:
                        eta = eta_from(time.time() - t2, n, total_n)
                        print(f"  [{n}/{total_n}] {cand['nama']} !! gagal: "
                              f"{str(exc)[:80]} | ETA {fmt_eta(eta)}")
                    if n % SAVE_EVERY == 0:
                        with _csv_lock:
                            finalize()
        speed = len(all_rows) / max(0.1, time.time() - t2)
        print(f"  fase 2: {len(all_rows)} dosen, {speed:.2f} dosen/detik")

        finalize()
        dur = time.time() - started
        tinggi = sum(1 for r in all_rows if r["Prioritas"] == "Tinggi")
        if FAILED_PAGES:
            print(f"\n[catatan] {len(FAILED_PAGES)} halaman gagal diambil "
                  f"(biasanya 429). Jalankan lagi: halaman yang sudah ada di "
                  f"cache tidak diulang, jadi progres melanjutkan.")
        print(f"\nSELESAI: {len(all_rows)} dosen dalam {dur:.1f}s "
              f"({tinggi} prioritas Tinggi)")
        print(f"  CSV : {OUTPUT_CSV}")
        print(f"  XLSX: {OUTPUT_XLSX}")
        print(f"  JSON: {OUTPUT_JSON}")
        return 0

    except Exception:
        finalize()
        print(f"\nCrash, tapi {len(all_rows)} baris sudah tersimpan di {OUTPUT_CSV}")
        raise
    finally:
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    sys.exit(main())
