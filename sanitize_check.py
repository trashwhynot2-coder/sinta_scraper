#!/usr/bin/env python3
"""
sanitize_check.py — penjaga sebelum `git push`.

Memeriksa apakah repo berisi hal yang bisa membuat akun GitHub kena tinjauan:

  1. Data pribadi  : alamat email, nama+nim/NIDN, file hasil scraping
  2. Konten pihak ketiga : HTML hasil scraping (bukan karya Anda)
  3. Rahasia       : cookies sesi, token

Cara pakai:
    python sanitize_check.py          # periksa, keluar kode 1 kalau ada masalah
    python sanitize_check.py --fix    # hapus file hasil scraping otomatis

Pasang sebagai pre-push hook (opsional, sekali saja):
    cp sanitize_check.py .git/hooks/pre-push && chmod +x .git/hooks/pre-push
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- pola berisiko ---------------------------------------------------------
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NIK_NIDN = re.compile(r"\b(NIDN|NIP|NIK)\b\s*[:=]?\s*\d{8,}")
SCRAPED_HTML = re.compile(
    r'class="(ar-list-item|list-item profile-side|profile-name|subject-list|'
    r'meta-profile|affil-loc|pr-num)"'
)
SINTA_DATA_COLS = re.compile(r"Nama[;,].*Institusi|Prioritas[;,].*Skor Prioritas")
# cookie sungguhan: header Netscape atau nilai token panjang
COOKIE = re.compile(
    r"(Netscape HTTP Cookie File"
    r"|(?:sessionid|csrftoken|XSRF-TOKEN)\s*[=:]\s*[A-Za-z0-9._%+/=-]{16,})",
    re.I,
)
TOKEN = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})")

# --- berkas yang memang boleh ada -----------------------------------------
ALLOW_EXT = {
    ".py", ".md", ".txt", ".bat", ".ini", ".example", ".json", ".cfg",
    ".toml", ".yml", ".yaml", ".gitignore",
}
# JSON yang boleh: template profil (bukan hasil scraping)
ALLOW_JSON = {"profiles/farmasi_bahan_alam.json"}

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
# berkas output yang, kalau ada, langsung dianggap "hasil scraping"
DATA_EXT = {".csv", ".xlsx", ".xls", ".html", ".htm"}
# pengecualian: contoh keluaran sintetis
ALLOW_DATA = {"hasil/demo_dosen.csv", "hasil/demo_dosen.xlsx"}


def tracked_files() -> list[Path]:
    """Ambil daftar file yang akan ikut ter-commit."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        files = [ROOT / line for line in out.splitlines() if line.strip()]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # bukan repo git -> telusuri folder
    files = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str]) -> int:
    do_fix = "--fix" in argv
    problems: list[tuple[str, str, str]] = []   # (file, jenis, detail)
    files = tracked_files()
    print(f"Memeriksa {len(files)} berkas...\n")

    for path in files:
        name = rel(path)
        suffix = path.suffix.lower()

        # 1. berkas data hasil scraping
        if suffix in DATA_EXT and name not in ALLOW_DATA:
            problems.append((name, "DATA", f"berkas {suffix} hasil scraping/PII"))
            if do_fix:
                try:
                    path.unlink()
                    print(f"  [hapus] {name}")
                except OSError as exc:
                    print(f"  [gagal hapus] {name}: {exc}")
            continue

        if suffix == ".json" and name not in ALLOW_JSON:
            problems.append((name, "DATA", "berkas JSON (kemungkinan hasil scraping)"))
            if do_fix:
                path.unlink(missing_ok=True)
                print(f"  [hapus] {name}")
            continue

        if suffix and suffix not in ALLOW_EXT:
            continue

        # 2. pindai isi
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        hits = EMAIL.findall(text)
        # abaikan email contoh/dokumentasi
        hits = [h for h in hits
                if not re.search(r"(example|contoh|test|user@|@x\.|@.*\.contoh\.)", h, re.I)]
        if hits:
            problems.append((name, "EMAIL", ", ".join(hits[:3])))
        nid = NIK_NIDN.findall(text)
        if nid:
            problems.append((name, "NIK/NIDN", str(nid[:1])))
        # markup hasil scraping: hanya relevan untuk berkas dokumen/teks,
        # dan harus banyak (bukan sekadar selektor di dalam kode Python)
        if suffix in {".md", ".txt", ".html", ".htm"}:
            if len(SCRAPED_HTML.findall(text)) >= 3:
                problems.append((name, "HTML", "markup SINTA hasil scraping"))
        if SINTA_DATA_COLS.search(text) and suffix not in {".py", ".md"}:
            problems.append((name, "DATA", "kolom data dosen"))
        if COOKIE.search(text) and suffix not in {".py", ".md", ".bat", ".example"}:
            problems.append((name, "COOKIE", "cookie sesi"))
        tok = TOKEN.findall(text)
        if tok:
            problems.append((name, "TOKEN", "token GitHub/AWS"))

    # --- laporkan ----------------------------------------------------------
    if not problems:
        print("BERSIH ✔  Tidak ada data pribadi, HTML pihak ketiga, atau rahasia.\n")
        print("Langkah berikutnya:")
        print("  git init && git add . && git status --short")
        print("  git commit -m 'SINTA scraper (tanpa data pribadi)'")
        return 0

    print("DITEMUKAN MASALAH:\n")
    for name, kind, detail in problems:
        print(f"  [{kind:9s}] {name}")
        if detail:
            print(f"              -> {detail}")
    print(f"\n{len(problems)} masalah.")
    if do_fix:
        print("Berkas data sudah dihapus. Jalankan ulang untuk memverifikasi:")
        print("  python sanitize_check.py")
    else:
        print("Jalankan `python sanitize_check.py --fix` untuk menghapus berkas")
        print("hasil scraping, lalu periksa ulang.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
