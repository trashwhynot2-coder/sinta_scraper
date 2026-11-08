#!/usr/bin/env python3
"""
autorun.py — orkestrator untuk autorun.bat (klik dua kali di Windows).

Alur:
  1. baca autorun_config.ini
  2. cek dependency -> kalau kurang, otomatis `pip install -r requirements.txt`
  3. jalankan sinta_scraper_bs4.py dengan argumen dari config
  4. tulis log ke logs/autorun_<tanggal>.log dan ringkasan
  5. tampilkan hasilnya (buka XLSX otomatis di Windows)

Semua pesan dibuat awam-friendly: kalau 403 -> disarankan relay=true, dst.
Bisa dijalankan juga di Linux/macOS: python autorun.py
"""
from __future__ import annotations

import configparser
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "autorun_config.ini"
SCRAPER = ROOT / "sinta_scraper_bs4.py"
REQUIREMENTS = ROOT / "requirements.txt"
LOGS = ROOT / "logs"

# paket -> nama modul yang di-import
NEEDED = {
    "requests": "requests",
    "beautifulsoup4": "bs4",
    "lxml": "lxml",
    "pandas": "pandas",
    "openpyxl": "openpyxl",
}

DEFAULTS = {
    "seed": {
        "url": "",
        "mode": "auto",
        "subject_ids": "6518",
        "affiliation_ids": "",
        "author_ids": "",
        "search_terms": "",
        "pages": "2",
    },
    "filter": {"region": "JABODETABEK", "limit": "0"},
    "output": {
        "views": "scopus,googlescholar",
        "pub_limit": "3",
        "prefix": "hasil/dosen_jabodetabek",
    },
    "jaringan": {
        "delay": "1.5",
        "workers": "3",
        "relay": "false",
        "cache": "true",
        "selenium_fallback": "true",
    },
}


# ---------------------------------------------------------------- utilitas
class Tee:
    """Tulis ke layar DAN ke file log."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
        self.fh.write(text)
        self.fh.flush()

    def close(self) -> None:
        self.fh.close()


def rule(char="=", n=64) -> None:
    print(char * n)


def as_list(value: str) -> list[str]:
    return [v.strip() for v in (value or "").replace("\n", ",").split(",") if v.strip()]


def as_bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "ya", "on")


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    # biarkan nilai berisi ; atau % apa adanya
    cfg = configparser.ConfigParser(interpolation=None)
    for section, values in DEFAULTS.items():
        cfg[section] = values

    if not CONFIG_PATH.exists():
        print(f"[peringatan] {CONFIG_PATH.name} tidak ada -> memakai nilai default.")
        return cfg

    try:
        cfg.read(CONFIG_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        cfg.read(CONFIG_PATH, encoding="latin-1")
    except configparser.Error as exc:
        print(f"[GAGAL] {CONFIG_PATH.name} tidak bisa dibaca: {exc}")
        print("        Biasanya karena ada baris tanpa '='. Perbaiki lalu simpan.")
        raise SystemExit(2)
    return cfg


def missing_packages() -> list[str]:
    missing = []
    for pip_name, module in NEEDED.items():
        if importlib.util.find_spec(module) is None:
            missing.append(pip_name)
    return missing


def pip_install(packages: list[str]) -> bool:
    rule()
    print("Dependency belum lengkap:", ", ".join(packages))
    print("Mencoba install otomatis (butuh internet, sekali saja)...")
    rule()
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    if REQUIREMENTS.exists() and len(packages) == len(NEEDED):
        cmd += ["-r", str(REQUIREMENTS)]
    else:
        cmd += packages
    try:
        result = subprocess.run(cmd, cwd=str(ROOT))
    except OSError as exc:
        print(f"[GAGAL] tidak bisa menjalankan pip: {exc}")
        return False
    if result.returncode != 0:
        print("\n[GAGAL] instalasi otomatis gagal.")
        print("  Coba manual di Command Prompt:")
        print(f'    cd /d "{ROOT}"')
        print("    python -m pip install -r requirements.txt")
        return False
    still = missing_packages()
    if still:
        print(f"[GAGAL] masih belum ada: {', '.join(still)}")
        return False
    print("Dependency terpasang.\n")
    return True


def open_file(path: Path) -> None:
    """Buka hasil otomatis (Windows: Excel/default app)."""
    try:
        if platform.system() == "Windows":
            os.startfile(str(path))  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
        print(f"  Membuka {path.name} ...")
    except Exception as exc:
        print(f"  (tidak bisa membuka otomatis: {exc})")


def count_rows(csv_path: Path) -> int:
    try:
        with csv_path.open(encoding="utf-8-sig") as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except OSError:
        return 0


# ------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    started = time.time()
    LOGS.mkdir(exist_ok=True)
    log_path = LOGS / f"autorun_{datetime.now():%Y%m%d_%H%M%S}.log"
    tee = Tee(log_path)
    sys.stdout = tee  # semua print ikut masuk log

    try:
        rule()
        print("  SINTA SCRAPER - AUTORUN")
        print(f"  waktu  : {datetime.now():%Y-%m-%d %H:%M:%S}")
        print(f"  folder : {ROOT}")
        print(f"  python : {sys.version.split()[0]} ({platform.system()})")
        print(f"  log    : {log_path}")
        rule()

        # 1) config ---------------------------------------------------------
        cfg = load_config()
        urls = as_list(cfg["seed"].get("url", ""))
        mode = (cfg["seed"].get("mode", "auto") or "auto").strip().lower()
        max_campuses = (cfg["seed"].get("max_campuses", "0") or "0").strip()
        subjects = as_list(cfg["seed"]["subject_ids"])
        affiliations = as_list(cfg["seed"]["affiliation_ids"])
        authors = as_list(cfg["seed"]["author_ids"])
        searches = as_list(cfg["seed"]["search_terms"])
        pages = cfg["seed"].get("pages", "2").strip() or "2"
        region = cfg["filter"].get("region", "JABODETABEK").strip()
        limit = cfg["filter"].get("limit", "0").strip() or "0"
        views = cfg["output"].get("views", "scopus").strip() or "scopus"
        pub_limit = cfg["output"].get("pub_limit", "3").strip() or "3"
        prefix = cfg["output"].get("prefix", "hasil/dosen_jabodetabek").strip()
        # config ditulis dengan '\' (gaya Windows) -> Path butuh '/'
        prefix = prefix.replace("\\", "/")
        delay = cfg["jaringan"].get("delay", "1.5").strip() or "1.5"
        workers = cfg["jaringan"].get("workers", "3").strip() or "3"
        relay = as_bool(cfg["jaringan"].get("relay", "false"))
        cache = as_bool(cfg["jaringan"].get("cache", "true"))
        selenium_fb = as_bool(cfg["jaringan"].get("selenium_fallback", "true"))

        # mode kampus tidak butuh subject_ids
        campus_mode = mode == "kampus"
        if not any([urls, subjects, affiliations, authors, searches]) and not campus_mode:
            print("[GAGAL] Di autorun_config.ini belum ada seed yang diisi.")
            print("        Isi minimal salah satu: subject_ids / affiliation_ids /")
            print("        author_ids / search_terms, lalu simpan dan jalankan lagi.")
            return 2

        print("\nRencana scraping:")
        print(f"  mode        : {mode}")
        if urls:
            print(f"  URL         : {', '.join(urls)}")
        if subjects:
            print(f"  subjek      : {', '.join(subjects)}  ({pages} halaman)")
        if affiliations:
            print(f"  institusi   : {', '.join(affiliations)}  ({pages} halaman)")
        if authors:
            print(f"  dosen (ID)  : {', '.join(authors)}")
        if searches:
            print(f"  pencarian   : {', '.join(searches)}  ({pages} halaman)")
        print(f"  wilayah     : {region or 'INDONESIA (semua)'}")
        print(f"  publikasi   : {views} (tampil {pub_limit})")
        print(f"  batas dosen : {'semua' if limit == '0' else limit}")
        print(f"  relay       : {'ya' if relay else 'tidak'} | delay {delay}s | "
              f"cache {'ya' if cache else 'tidak'} | {workers} thread")
        print(f"  output      : {prefix}.csv / .xlsx / .json")

        # 2) dependency -----------------------------------------------------
        missing = missing_packages()
        if missing and not pip_install(missing):
            return 3

        # 3) jalankan scraper ----------------------------------------------
        cmd = [sys.executable, str(SCRAPER)]
        for u in urls:
            cmd += ["--url", u]
        for s in subjects:
            cmd += ["--subject", s]
        for a in affiliations:
            cmd += ["--affiliation", a]
        for a in authors:
            cmd += ["--author", a]
        for s in searches:
            cmd += ["--search", s]
        cmd += ["--pages", pages, "--region", region, "--views", views,
                "--limit", limit, "--delay", delay, "--workers", workers,
                "--out", prefix, "--mode", mode]
        if max_campuses and max_campuses != "0":
            cmd += ["--max-campuses", max_campuses]

        # path di config pakai '/' (portable); di Windows biarkan apa adanya
        cmd += ["--relay"] if relay else []
        cmd += ["--no-cache"] if not cache else []

        env = os.environ.copy()
        env["SINTA_SELENIUM_FALLBACK"] = "1" if selenium_fb else "0"
        env["PYTHONIOENCODING"] = "utf-8"

        if urls and (subjects or affiliations or authors):
            print("\n[catatan] 'url' diisi DAN subject_ids/affiliation_ids juga diisi.")
            print("          Keduanya digabung. Kosongkan subject_ids kalau hanya")
            print("          ingin memakai URL saja.")

        rule()
        print("Mulai scraping... (jangan tutup jendela ini)\n")
        rule()
        result = subprocess.run(cmd, cwd=str(ROOT), env=env)
        code = result.returncode

        # 4) ringkasan ------------------------------------------------------
        rule()
        csv_path = (ROOT / prefix).with_suffix(".csv")
        xlsx_path = (ROOT / prefix).with_suffix(".xlsx")
        rows = count_rows(csv_path)

        if code != 0:
            print(f"SELESAI dengan masalah (kode {code}).")
            print("Cek pesan di atas. Kalau isinya 'Gagal mengambil ... 403':")
            print("  buka autorun_config.ini, ubah  relay = true  lalu jalankan lagi.")
            print(f"Log: {log_path}")
            return code

        if rows == 0:
            print("Scraping berjalan, tapi belum ada dosen yang lolos filter.")
            print("Coba salah satu:")
            print("  - naikkan  pages = 9   di autorun_config.ini")
            print("  - ganti   region = INDONESIA   (tanpa filter wilayah)")
            print("  - pakai   affiliation_ids = 430   (Universitas Indonesia)")
            print(f"Log: {log_path}")
            return 0

        print(f"BERHASIL: {rows} dosen tersimpan.")
        print(f"  CSV  : {csv_path}")
        print(f"  XLSX : {xlsx_path}")
        print(f"  Log  : {log_path}")

        if "--no-open" not in (argv if argv is not None else sys.argv[1:]):
            target = xlsx_path if xlsx_path.exists() else csv_path
            if target.exists():
                open_file(target)

        print(f"\nTotal waktu: {time.time() - started:.1f} detik")
        return 0

    except KeyboardInterrupt:
        print("\nDibatalkan oleh pengguna (Ctrl+C).")
        print("Data yang sudah terkumpul tetap aman di file CSV.")
        return 130
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] {type(exc).__name__}: {exc}")
        print(f"Log: {log_path}")
        return 1
    finally:
        sys.stdout = sys.__stdout__
        tee.close()


if __name__ == "__main__":
    raise SystemExit(main())
