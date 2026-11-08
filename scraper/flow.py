"""
Orkestrasi scraping:
  1. Kumpulkan kandidat dosen (via subject / affiliation / author search / ID)
  2. Filter wilayah (mis. JABODETABEK)
  3. Buka profil tiap dosen -> publikasi (paralel, sopan)
  4. Enrichment (kata kunci, potensi kebutuhan, prioritas, kontak)
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from . import enrich, parsers
from .client import SintaClient
from .regions import Location, matches_regions, parse_location

log = logging.getLogger("sinta.flow")


@dataclass
class Candidate:
    sinta_id: str
    name: str
    affiliation: str = ""
    affiliation_id: str = ""
    department: str = ""
    subjects: list[str] = field(default_factory=list)
    location: Location = field(default_factory=Location)
    scores: dict[str, str] = field(default_factory=dict)
    hindex: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(text: str) -> float:
    """'1.281' -> 1281.0 ; '3,5' -> 3.5"""
    if not text:
        return 0.0
    t = re.sub(r"[^\d,.]", "", text)
    if not t:
        return 0.0
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _get_score(scores: dict, *keys: str) -> float:
    for k in keys:
        for sk, sv in scores.items():
            if k.lower() in sk.lower():
                return _num(sv)
    return 0.0


class SintaScraper:
    def __init__(self, client: SintaClient, profile_cfg: dict):
        self.client = client
        self.cfg = profile_cfg
        self._location_memo: dict[str, Location] = {}

    # ------------------------------------------------------------- locations
    def affiliation_location(self, affiliation_id: str, location_hint: str = "") -> Location:
        """Lokasi afiliasi: pakai hint dari kartu (bila ada) atau buka profil afiliasi."""
        if location_hint:
            return parse_location(location_hint)
        if not affiliation_id:
            return Location()
        if affiliation_id in self._location_memo:
            return self._location_memo[affiliation_id]
        soup = self.client.get_soup(f"/affiliations/profile/{affiliation_id}")
        _, loc_text, _ = parsers.parse_affiliation_location(soup)
        loc = parse_location(loc_text)
        self._location_memo[affiliation_id] = loc
        return loc

    # ------------------------------------------------------------- collectors
    def candidates_from_subject(
        self, subject_id: str, pages: int = 3, sort: int = 1, q: str = ""
    ) -> list[Candidate]:
        out: list[Candidate] = []
        for page in range(1, pages + 1):
            soup = self.client.get_soup(
                f"/subjects/detail/{subject_id}?page={page}&sort={sort}"
                + (f"&q={q}" if q else "")
            )
            items = parsers.parse_author_cards(soup)
            log.info("subject %s page %s -> %s dosen", subject_id, page, len(items))
            if not items:
                break
            for it in items:
                out.append(self._to_candidate(it))
        return out

    def candidates_from_affiliation(
        self, affiliation_id: str, pages: int = 5, sort: int = 1
    ) -> list[Candidate]:
        aff_name, aff_loc, _ = parsers.parse_affiliation_location(
            self.client.get_soup(f"/affiliations/profile/{affiliation_id}")
        )
        location = parse_location(aff_loc)
        out: list[Candidate] = []
        for page in range(1, pages + 1):
            soup = self.client.get_soup(
                f"/affiliations/authors/{affiliation_id}?page={page}&sort={sort}"
            )
            items = parsers.parse_author_cards(soup)
            log.info("affiliation %s page %s -> %s dosen", affiliation_id, page, len(items))
            if not items:
                break
            for it in items:
                cand = self._to_candidate(it)
                cand.affiliation = cand.affiliation or aff_name
                cand.affiliation_id = cand.affiliation_id or affiliation_id
                cand.location = location
                out.append(cand)
        return out

    def candidates_from_search(self, keyword: str, pages: int = 3, sort: int = 1) -> list[Candidate]:
        out: list[Candidate] = []
        for page in range(1, pages + 1):
            soup = self.client.get_soup(f"/authors?page={page}&q={keyword}&sort={sort}")
            items = parsers.parse_author_cards(soup)
            log.info("search '%s' page %s -> %s dosen", keyword, page, len(items))
            if not items:
                break
            out.extend(self._to_candidate(it) for it in items)
        return out

    def candidates_from_affiliations(self, pages: int = 5) -> list[dict]:
        """Daftar afiliasi (untuk dipindai lokasinya lalu dipakai sebagai seed)."""
        out: list[dict] = []
        for page in range(1, pages + 1):
            soup = self.client.get_soup(f"/affiliations?page={page}")
            affs = parsers.parse_affiliation_cards(soup)
            if not affs:
                break
            for a in affs:
                loc = parse_location(a.location)
                out.append(
                    {
                        "id": a.affiliation_id,
                        "name": a.name,
                        "location": loc.as_dict(),
                        "authors": a.authors_count,
                    }
                )
        return out

    # -------------------------------------------------------------- profiles
    def profile(self, sinta_id: str, views: Iterable[str], max_pages: int = 1) -> parsers.AuthorProfile:
        views = list(views) or ["scopus"]
        merged: Optional[parsers.AuthorProfile] = None
        for view in views:
            for page in range(1, max_pages + 1):
                path = f"/authors/profile/{sinta_id}?view={view}"
                if page > 1:
                    path += f"&page={page}"
                soup = self.client.get_soup(path)
                prof = parsers.parse_author_profile(soup, source=view)
                if not prof.name and not prof.publications:
                    continue
                if merged is None:
                    merged = prof
                else:
                    merged.publications.extend(prof.publications)
                    merged.subjects = list(dict.fromkeys(merged.subjects + prof.subjects))
                    if not merged.researches:
                        merged.researches = prof.researches
                # berhenti paginasi bila halaman kosong
                if not prof.publications:
                    break
        return merged or parsers.AuthorProfile(sinta_id=sinta_id)

    # --------------------------------------------------------------- internal
    def _to_candidate(self, item: parsers.AuthorListItem) -> Candidate:
        return Candidate(
            sinta_id=item.sinta_id,
            name=item.name,
            affiliation=item.affiliation,
            affiliation_id=item.affiliation_id,
            department=item.department,
            subjects=item.subjects,
            location=parse_location(item.location),
            scores=item.scores,
            hindex=item.hindex,
        )

    # ------------------------------------------------------------------ main
    def run(
        self,
        seeds: dict,
        regions: Iterable[str],
        views: Iterable[str],
        max_pages: int = 1,
        pub_limit: int = 3,
        workers: int = 3,
        limit: Optional[int] = None,
    ) -> list[dict]:
        wanted = list(regions)
        candidates = self._collect(seeds)
        log.info("kandidat terkumpul: %s", len(candidates))

        # dedupe by sinta_id
        uniq: dict[str, Candidate] = {}
        for c in candidates:
            if c.sinta_id and c.sinta_id not in uniq:
                uniq[c.sinta_id] = c
        candidates = list(uniq.values())

        # filter wilayah
        if wanted and "INDONESIA" not in wanted and "ALL" not in wanted:
            kept = []
            for c in candidates:
                if not c.location.raw and c.affiliation_id:
                    c.location = self.affiliation_location(c.affiliation_id)
                if matches_regions(c.location, wanted):
                    kept.append(c)
            log.info("setelah filter wilayah %s: %s dosen", wanted, len(kept))
            candidates = kept

        if limit:
            candidates = candidates[:limit]

        rows: list[dict] = []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(self._build_row, c, views, max_pages, pub_limit): c
                for c in candidates
            }
            for i, fut in enumerate(as_completed(futures), 1):
                c = futures[fut]
                try:
                    rows.append(fut.result())
                    log.info("[%s/%s] %s", i, len(futures), c.name)
                except Exception as exc:  # lanjut walau satu gagal
                    log.warning("gagal memproses %s (%s): %s", c.name, c.sinta_id, exc)
        return rows

    def _collect(self, seeds: dict) -> list[Candidate]:
        cands: list[Candidate] = []
        for sid in seeds.get("author_ids", []):
            soup = self.client.get_soup(f"/authors/profile/{sid}")
            prof = parsers.parse_author_profile(soup)
            cands.append(
                Candidate(
                    sinta_id=prof.sinta_id or sid,
                    name=prof.name,
                    affiliation=prof.affiliation,
                    affiliation_id=prof.affiliation_id,
                    department=prof.department,
                    subjects=prof.subjects,
                    location=parse_location(prof.location),
                    scores=prof.scores,
                )
            )
        for sid in seeds.get("subject_ids", []):
            cands += self.candidates_from_subject(
                sid, pages=seeds.get("subject_pages", 2)
            )
        for aid in seeds.get("affiliation_ids", []):
            cands += self.candidates_from_affiliation(
                aid, pages=seeds.get("affiliation_pages", 3)
            )
        for kw in seeds.get("keywords", []):
            cands += self.candidates_from_search(kw, pages=seeds.get("search_pages", 2))
        return cands

    def _build_row(
        self,
        cand: Candidate,
        views: Iterable[str],
        max_pages: int,
        pub_limit: int,
    ) -> dict:
        prof = self.profile(cand.sinta_id, views, max_pages=max_pages)
        location = cand.location
        if not location.raw and cand.affiliation_id:
            location = self.affiliation_location(cand.affiliation_id)

        texts = [prof.name, prof.affiliation, prof.department] + prof.subjects + prof.researches
        texts += [p.title for p in prof.publications]

        score_3yr = _get_score({**cand.scores, **prof.scores}, "SINTA Score 3Yr", "3Yr")
        hindex = 0
        for k, v in cand.hindex.items():
            if "scopus" in k.lower() or "gs" in k.lower() or "google" in k.lower():
                hindex = int(_num(v))
        m = enrich.build_match(
            texts,
            self.cfg,
            is_jabodetabek=location.in_jabodetabek,
            pub_count=len(prof.publications),
            score_3yr=score_3yr,
            hindex=hindex,
        )
        pubs = enrich.rank_publications(prof.publications, self.cfg, limit=pub_limit)

        domain = enrich.guess_domain(prof.affiliation or cand.affiliation)
        email_guess = enrich.guess_email(prof.name or cand.name, domain)

        return {
            "sinta_id": cand.sinta_id or prof.sinta_id,
            "nama": prof.name or cand.name,
            "institusi": prof.affiliation or cand.affiliation,
            "institusi_id": prof.affiliation_id or cand.affiliation_id,
            "program_studi": prof.department or cand.department,
            "bidang": m.bidang,
            "penelitian": m.penelitian,
            "publikasi": [
                f"{p.title} ({p.year})" + (f" - {p.venue}" if p.venue else "")
                for p in pubs
            ],
            "potensi_kebutuhan": m.potensi,
            "kontak_email": email_guess,
            "kontak_email_status": (
                "dugaan (pola nama@domain institusi) - verifikasi manual"
                if email_guess
                else "belum ada - domain institusi belum dipetakan"
            ),
            "kontak_scholar": enrich.google_scholar_search_url(prof.name or cand.name),
            "kontak_linkedin": enrich.linkedin_search_url(
                prof.name or cand.name, prof.affiliation or cand.affiliation
            ),
            "prioritas": m.prioritas,
            "skor_prioritas": m.skor,
            "wilayah": ",".join(sorted(location.regions)),
            "kota": location.city_full or location.city,
            "provinsi": location.province,
            "is_jabodetabek": location.in_jabodetabek,
            "subjek_sinta": "; ".join(prof.subjects or cand.subjects),
            "sinopsis_penelitian_sinta": "; ".join(prof.researches[:5]),
            "sinta_score_3yr": _get_score({**cand.scores, **prof.scores}, "SINTA Score 3Yr", "3Yr"),
            "h_index": hindex,
            "jumlah_publikasi_terbaca": len(prof.publications),
            "kata_kunci_cocok": "; ".join(m.hits),
            "profil_url": f"https://sinta.kemdiktisaintek.go.id/authors/profile/{cand.sinta_id}",
        }
