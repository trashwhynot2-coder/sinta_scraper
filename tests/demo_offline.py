"""
Demo OFFLINE: menjalankan pipeline lengkap memakai HTML yang sudah tersimpan
di tests/fixtures (tanpa request ke SINTA).

Berguna untuk:
  * memastikan instalasi benar sebelum scraping live
  * melihat bentuk file output (CSV / XLSX / MD / JSON)

Jalankan:  python -m tests.demo_offline
"""
from __future__ import annotations

import logging
from pathlib import Path

from bs4 import BeautifulSoup

from scraper import enrich, export
from scraper.flow import SintaScraper
from tests import fixtures_sintetis as fxs

OUT = Path("hasil")

# peta path SINTA -> HTML sintetis (bukan hasil scraping)
ROUTES = {
    "/authors/profile/9000001?view=scopus": fxs.PROFIL_DOSEN,
    "/authors/profile/9000001": fxs.PROFIL_DOSEN,
    "/authors/profile/9000001?view=googlescholar": fxs.publikasi_google_scholar(10),
    "/authors/profile/9000002?view=scopus": fxs.PROFIL_DOSEN_2,
    "/authors/profile/9000002": fxs.PROFIL_DOSEN_2,
    "/subjects/detail/6518?page=1&sort=1": fxs.daftar_dosen(3, 1),
    "/subjects/detail/6518?page=2&sort=1": fxs.daftar_dosen(3, 2),
    "/affiliations/authors/999?page=1&sort=1": fxs.daftar_dosen_institusi(10),
    "/affiliations/profile/999": fxs.profil_institusi(),
    "/affiliations?page=1": fxs.daftar_institusi(),
}


class FixtureClient:
    """Pengganti SintaClient yang membaca HTML sintetis."""

    def get_soup(self, path: str, use_cache: bool = True) -> BeautifulSoup:
        html = ROUTES.get(path)
        if html is None:
            return BeautifulSoup("<html></html>", "lxml")
        return BeautifulSoup(html, "lxml")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    cfg = enrich.load_profile("farmasi_bahan_alam")
    scraper = SintaScraper(FixtureClient(), cfg)

    rows = scraper.run(
        seeds={
            "author_ids": ["9000001", "9000002"],
            "subject_ids": ["6518"],
            "subject_pages": 2,
            "affiliation_ids": ["999"],
            "affiliation_pages": 1,
        },
        regions=["JABODETABEK"],     # semua fixture memang Jakarta/Bogor
        views=["scopus", "googlescholar"],
        max_pages=1,
        pub_limit=3,
        workers=2,
    )
    rows.sort(key=lambda r: -r.get("skor_prioritas", 0))

    OUT.mkdir(exist_ok=True)
    csv_path = export.write_csv(rows, OUT / "demo_dosen.csv")
    xlsx_path = export.write_xlsx(rows, OUT / "demo_dosen.xlsx")
    md_path = export.write_markdown(rows, OUT / "demo_dosen.md")

    print(f"\n{len(rows)} dosen -> {csv_path}, {xlsx_path}, {md_path}")
    for r in rows[:5]:
        print(f"  {r['prioritas']:7s} skor {r['skor_prioritas']:3d}  "
              f"{r['nama'][:28]:30s} {r['institusi'][:34]:36s} {r['kota']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
