#!/usr/bin/env python3
"""
sinta_scraper – CLI

Contoh pemakaian
================
1) Satu dosen (ID dari URL profil SINTA):
   python -m scraper.cli --author 5996301 --profile farmasi_bahan_alam

2) Semua dosen pada sebuah subjek, dibatasi JABODETABEK, 5 halaman subjek:
   python -m scraper.cli --subject 45887 --subject-pages 5 \
       --region JABODETABEK --profile farmasi_bahan_alam --out hasil/dosen

3) Semua dosen di satu kampus:
   python -m scraper.cli --affiliation 430 --affiliation-pages 10 \
       --region JABODETABEK

4) Cari nama dosen:
   python -m scraper.cli --search "farmasi" --search-pages 3 --region JABODETABEK

5) Hanya memetakan kampus mana yang masuk JABODETABEK (tanpa buka profil dosen):
   python -m scraper.cli --map-affiliations --affiliation-pages 5

Dijalankan dari VPS/cloud dan kena 403? tambahkan --relay.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import enrich, export
from .client import SintaClient
from .flow import SintaScraper
from .regions import JABODETABEK_STRICT_NOTE, REGION_PRESETS

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sinta-scraper",
        description="Scraper data dosen SINTA (sinta.kemdiktisaintek.go.id)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # seed
    g = p.add_argument_group("Sumber data (seed) – bisa dikombinasikan")
    g.add_argument("--author", action="append", default=[], metavar="SINTA_ID",
                   help="ID dosen, mis. 5996301 (dari /authors/profile/<id>)")
    g.add_argument("--subject", action="append", default=[], metavar="SUBJECT_ID",
                   help="ID subjek, mis. 45887 (dari /subjects/detail/<id>)")
    g.add_argument("--subject-pages", type=int, default=2,
                   help="jumlah halaman daftar subjek yang diambil (default 2)")
    g.add_argument("--affiliation", action="append", default=[], metavar="AFFIL_ID",
                   help="ID institusi, mis. 476 (Universitas Tarumanagara)")
    g.add_argument("--affiliation-pages", type=int, default=3,
                   help="jumlah halaman daftar dosen institusi (default 3)")
    g.add_argument("--search", action="append", default=[], metavar="KATA_KUNCI",
                   help="pencarian nama dosen di /authors?q=")
    g.add_argument("--search-pages", type=int, default=2,
                   help="jumlah halaman hasil pencarian (default 2)")

    # filter & enrichment
    f = p.add_argument_group("Filter & enrichment")
    f.add_argument("--region", action="append", default=[], metavar="NAMA",
                   help="filter wilayah: JABODETABEK | DKI | BODETABEK | JABAR | INDONESIA "
                        "(bisa lebih dari satu)")
    f.add_argument("--profile", default="farmasi_bahan_alam",
                   help="template kebutuhan: farmasi_bahan_alam | generic | path JSON "
                        "(default farmasi_bahan_alam)")
    f.add_argument("--views", default="scopus,googlescholar",
                   help="sumber publikasi: scopus,googlescholar,garuda,wos,rama,researches "
                        "(default scopus,googlescholar)")
    f.add_argument("--pub-pages", type=int, default=1,
                   help="jumlah halaman publikasi per sumber (default 1)")
    f.add_argument("--pub-limit", type=int, default=3,
                   help="jumlah publikasi relevan yang ditampilkan (default 3)")
    f.add_argument("--limit", type=int, default=0,
                   help="batasi jumlah dosen yang diproses (0 = semua)")

    # output
    o = p.add_argument_group("Output")
    o.add_argument("--out", default="hasil/dosen_sinta",
                   help="prefix file output (default hasil/dosen_sinta)")
    o.add_argument("--format", default="csv,xlsx,md,json",
                   help="csv,xlsx,md,json (default semuanya)")
    o.add_argument("--map-affiliations", action="store_true",
                   help="hanya cetak/mapping lokasi afiliasi, tanpa buka profil dosen")

    # jaringan
    n = p.add_argument_group("Jaringan & etika scraping")
    n.add_argument("--delay", type=float, default=1.0,
                   help="jeda antar request dalam detik (default 1.0)")
    n.add_argument("--workers", type=int, default=3,
                   help="jumlah thread paralel (default 3, jangan terlalu besar)")
    n.add_argument("--timeout", type=int, default=30, help="timeout request (detik)")
    n.add_argument("--retries", type=int, default=3, help="jumlah percobaan ulang")
    n.add_argument("--cache-dir", default=".cache_sinta",
                   help="folder cache HTML (default .cache_sinta)")
    n.add_argument("--no-cache", action="store_true", help="matikan cache")
    n.add_argument("--relay", action="store_true",
                   help="akses via relay *.translate.goog bila IP diblokir WAF SINTA")
    n.add_argument("--cookies", default=None,
                   help="file cookies Netscape (opsional)")
    n.add_argument("--verbose", "-v", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FORMAT,
    )
    log = logging.getLogger("sinta")

    if args.region:
        for r in args.region:
            if r.upper() not in REGION_PRESETS and r.upper() != "INDONESIA":
                log.warning("Wilayah '%s' tidak dikenal (pilihan: %s, INDONESIA)",
                            r, ", ".join(REGION_PRESETS))
        if any(r.upper() == "JABODETABEK" for r in args.region):
            log.info(JABODETABEK_STRICT_NOTE)

    cfg = enrich.load_profile(args.profile)
    client = SintaClient(
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        cache_dir=None if args.no_cache else args.cache_dir,
        use_relay=args.relay,
        cookies_file=args.cookies,
    )
    scraper = SintaScraper(client, cfg)

    # mode khusus: mapping afiliasi
    if args.map_affiliations:
        affs = scraper.candidates_from_affiliations(pages=args.affiliation_pages)
        wanted = [r.upper() for r in args.region] or ["JABODETABEK"]
        from .regions import matches_regions, parse_location
        picked = [a for a in affs if matches_regions(parse_location(a["location"]["lokasi_raw"]), wanted)]
        out = Path(args.out).with_suffix(".affiliations.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(picked, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{len(picked)} / {len(affs)} afiliasi cocok dengan {wanted} -> {out}")
        for a in picked[:40]:
            print(f"  {a['id']:>6}  {a['name'][:52]:54s} {a['location']['lokasi_raw']}")
        return 0

    if not any([args.author, args.subject, args.affiliation, args.search]):
        print("Tidak ada sumber data. Contoh: python -m scraper.cli --author 5996301\n"
              "Gunakan -h untuk bantuan lengkap.", file=sys.stderr)
        return 2

    seeds = {
        "author_ids": args.author,
        "subject_ids": args.subject,
        "subject_pages": args.subject_pages,
        "affiliation_ids": args.affiliation,
        "affiliation_pages": args.affiliation_pages,
        "keywords": args.search,
        "search_pages": args.search_pages,
    }
    views = [v for v in (args.views or "").split(",") if v.strip()]

    try:
        rows = scraper.run(
            seeds,
            regions=[r.upper() for r in args.region],
            views=views,
            max_pages=args.pub_pages,
            pub_limit=args.pub_limit,
            workers=args.workers,
            limit=args.limit or None,
        )
    except Exception as exc:
        log.error("%s", exc)
        return 1

    if not rows:
        log.warning("Tidak ada data. Coba longgarkan filter wilayah atau tambah halaman.")
        return 0

    # urutkan: prioritas skor desc, lalu Jabodetabek
    rows.sort(key=lambda r: (-r.get("skor_prioritas", 0), not r.get("is_jabodetabek", False)))

    base = Path(args.out)
    fmts = {f.strip().lower() for f in args.format.split(",") if f.strip()}
    written: list[Path] = []
    if "csv" in fmts:
        written.append(export.write_csv(rows, base.with_suffix(".csv")))
    if "json" in fmts:
        base.with_suffix("").parent.mkdir(parents=True, exist_ok=True)
        jpath = base.with_suffix(".json")
        jpath.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(jpath)
    if "xlsx" in fmts:
        written.append(export.write_xlsx(rows, base.with_suffix(".xlsx")))
    if "md" in fmts:
        written.append(export.write_markdown(rows, base.with_suffix(".md")))

    print(f"\n{len(rows)} dosen diproses. File output:")
    for p in written:
        print(f"  - {p}")
    top = rows[0]
    print(f"\nPrioritas tertinggi: {top['nama']} ({top['institusi']}) "
          f"skor {top['skor_prioritas']} [{top['prioritas']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
