"""
Uji parser & pipeline memakai HTML SINTETIS (tests/fixtures_sintetis.py).

Repo ini sengaja TIDAK menyimpan HTML milik SINTA maupun data dosen asli.
Markup sintetis meniru struktur SINTA dan sudah cocok dengan selektor parser.

Jalankan:  python -m tests.test_offline
"""
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from scraper import enrich, parsers
from scraper.regions import matches_regions, parse_location
from tests import fixtures_sintetis as fxs


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def check(label: str, cond: bool, extra: str = "") -> bool:
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
    return cond


def main() -> int:
    ok = True

    # 1. Profil dosen
    print("\n1) Profil dosen (fixture sintetis)")
    prof = parsers.parse_author_profile(soup(fxs.PROFIL_DOSEN), "scopus")
    ok &= check("nama", prof.name == "DOSEN CONTOH", prof.name)
    ok &= check("institusi", prof.affiliation == "Universitas Contoh Nusantara", prof.affiliation)
    ok &= check("sinta_id", prof.sinta_id == "9000001", prof.sinta_id)
    ok &= check("program studi", "Farmasi" in prof.department, prof.department)
    ok &= check("subjek SINTA", len(prof.subjects) == 2, str(prof.subjects))
    ok &= check("SINTA Score 3Yr", prof.scores.get("SINTA Score 3Yr") == "700", str(prof.scores))
    ok &= check("publikasi terbaca", len(prof.publications) == 2, str(len(prof.publications)))
    if prof.publications:
        p = prof.publications[0]
        ok &= check("judul publikasi", bool(p.title), p.title[:40])
        ok &= check("tahun publikasi", p.year.isdigit(), p.year)
        ok &= check("jurnal terbaca", "Jurnal" in p.venue, p.venue)
        ok &= check("urutan penulis", "Author Order" in p.author_order, p.author_order)

    # 2. Daftar dosen + paginasi
    print("\n2) Daftar dosen & paginasi")
    items = parsers.parse_author_cards(soup(fxs.daftar_dosen(total_pages=3, page=1)))
    ok &= check("10 kartu dosen", len(items) == 10, str(len(items)))
    ok &= check("institusi terbaca", all(i.affiliation for i in items), items[0].affiliation)
    ok &= check("subjek terbaca", any(i.subjects for i in items))
    ok &= check("H-index terbaca", any(i.hindex for i in items), str(items[0].hindex))
    total_pages, total_records = parsers.parse_total_records(soup(fxs.daftar_dosen(3, 1)))
    ok &= check("total halaman", total_pages == 3, str(total_pages))
    ok &= check("total records", total_records == 30, str(total_records))

    # 3. Lokasi institusi
    print("\n3) Lokasi institusi")
    name, loc, _ = parsers.parse_affiliation_location(soup(fxs.profil_institusi()))
    ok &= check("nama institusi", name == "Universitas Contoh Nusantara", name)
    parsed = parse_location(loc)
    ok &= check("kota terparse", parsed.city == "JAKARTA PUSAT", str(parsed.as_dict()))
    ok &= check("terdeteksi JABODETABEK", parsed.in_jabodetabek)
    ok &= check("provinsi", parsed.province == "DKI JAKARTA", parsed.province)

    # 4. Filter wilayah
    print("\n4) Filter JABODETABEK")
    affs = parsers.parse_affiliation_cards(soup(fxs.daftar_institusi()))
    ok &= check("kartu afiliasi terparse", len(affs) == 7, str(len(affs)))
    jbd = [a.name for a in affs
           if matches_regions(parse_location(a.location), ["JABODETABEK"])]
    ok &= check("4 kampus Jabodetabek", len(jbd) == 4, ", ".join(jbd))
    ok &= check("Bogor & Tangsel ikut", "Institut Contoh Bogor" in jbd and
                "Universitas Contoh Tangerang" in jbd)
    ok &= check("Bandung, Sleman, Surabaya ditolak",
                not any(x in jbd for x in ("Bandung", "Yogyakarta", "Surabaya")), ", ".join(jbd))

    # 5. Google Scholar
    print("\n5) Publikasi Google Scholar")
    gs = parsers.parse_publications(soup(fxs.publikasi_google_scholar(10)), "googlescholar")
    ok &= check("10 publikasi", len(gs) == 10, str(len(gs)))
    ok &= check("venue GS terisi", any(p.venue for p in gs))

    # 6. Enrichment
    print("\n6) Enrichment & prioritas")
    cfg = enrich.load_profile("farmasi_bahan_alam")
    m = enrich.build_match(["Farmasi", "Antioksidan ekstrak daun", "flavonoid", "DPPH", "fenolik"],
                           cfg, is_jabodetabek=True, pub_count=4, score_3yr=800)
    ok &= check("kata kunci cocok", len(m.hits) >= 4, str(m.hits))
    ok &= check("prioritas Tinggi", m.prioritas == "Tinggi", f"skor {m.skor}")
    m2 = enrich.build_match(["ilmu hukum tata negara"], cfg)
    ok &= check("non-relevan -> Rendah", m2.prioritas == "Rendah" and not m2.hits)
    email = enrich.guess_email("Dosen Contoh", enrich.guess_domain("Universitas Contoh Nusantara"))
    ok &= check("domain tak dikenal -> email kosong", email == "", email or "(kosong)")

    # 7. Baris output lengkap
    print("\n7) Simulasi baris output")
    sheets = [x for x in [prof.affiliation, prof.department] + prof.subjects
              + [p.title for p in prof.publications]]
    m3 = enrich.build_match(sheets, cfg, is_jabodetabek=parsed.in_jabodetabek,
                            pub_count=len(prof.publications))
    pubs = enrich.rank_publications(prof.publications, cfg, limit=3)
    row = {
        "nama": prof.name,
        "institusi": prof.affiliation,
        "bidang": m3.bidang,
        "penelitian": m3.penelitian,
        "publikasi": [f"{p.title} ({p.year})" for p in pubs],
        "potensi_kebutuhan": m3.potensi,
        "prioritas": m3.prioritas,
        "wilayah": ",".join(sorted(parsed.regions)),
    }
    print(json.dumps(row, indent=2, ensure_ascii=False))

    print("\n" + ("SEMUA TES LULUS ✔" if ok else "ADA TES GAGAL ✘"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
