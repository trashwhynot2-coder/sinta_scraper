"""
Parser HTML SINTA.

Semua selector diambil dari markup asli SINTA (Bootstrap 4), mis.:

    <div class="meta-profile">
        <a href="..."><i class="el el-map-marker"></i> Universitas Tarumanagara</a>
        <a href="/departments/profile/476/031015/11901"><i class="el el-child"></i> Profesi - Profesi Dokter</a>
        <a href="..."><i class="el el-user"></i> SINTA ID : 5996301</a>
    </div>
    <ul class="subject-list"> <li><a href="/subjects/detail/45887">Kesehatan masyarakat</a></li> </ul>

    <div class="ar-list-item mb-5">
        <div class="ar-title"><a href="...">Judul Artikel</a></div>
        <div class="ar-meta">
            <a class="ar-quartile">Q3 Journal</a> <a class="ar-pub">Nama Jurnal</a>
            <a>Author Order : 2 of 4</a> <a class="ar-year">2025</a> <a class="ar-cited">3 cited</a>
        </div>
    </div>

Model ditulis sedemikian rupa agar sintaks `|` (alternatif) dapat menangani
perbedaan kecil antar halaman (scopus/wos/garuda/gs/rama).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from bs4 import BeautifulSoup, Tag

_WS = re.compile(r"\s+")


def clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


def _first_text(node: Tag, *selectors: str) -> str:
    for sel in selectors:
        found = node.select_one(sel)
        if found and clean(found.get_text()):
            return clean(found.get_text())
    return ""


def _first_attr(node: Tag, selector: str, attr: str) -> str:
    found = node.select_one(selector)
    return found.get(attr, "").strip() if found and found.get(attr) else ""


def _author_id(href: str) -> str:
    m = re.search(r"/authors/profile/(\d+)", href or "")
    return m.group(1) if m else ""


def _affil_id(href: str) -> str:
    m = re.search(r"/affiliations/profile/(\d+)", href or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Publication:
    title: str = ""
    year: str = ""
    venue: str = ""
    quartile: str = ""
    url: str = ""
    cited: str = ""
    author_order: str = ""
    source: str = ""           # scopus | gs | wos | garuda | rama

    def as_dict(self) -> dict:
        return {
            "judul": self.title,
            "tahun": self.year,
            "jurnal_atau_prosiding": self.venue,
            "kuartil": self.quartile,
            "sitasi": self.cited,
            "urutan_penulis": self.author_order,
            "sumber": self.source,
            "url": self.url,
        }


@dataclass
class AuthorListItem:
    """Hasil parse dari /authors, /affiliations/authors/<id>, /subjects/detail/<id>,
    /departments/profile/... dsb."""
    sinta_id: str = ""
    name: str = ""
    affiliation: str = ""
    affiliation_id: str = ""
    department: str = ""
    subjects: list[str] = field(default_factory=list)
    location: str = ""
    scores: dict[str, str] = field(default_factory=dict)
    hindex: dict[str, str] = field(default_factory=dict)
    profile_url: str = ""


@dataclass
class AuthorProfile:
    sinta_id: str = ""
    name: str = ""
    affiliation: str = ""
    affiliation_id: str = ""
    department: str = ""
    subjects: list[str] = field(default_factory=list)
    scores: dict[str, str] = field(default_factory=dict)
    location: str = ""
    publications: list[Publication] = field(default_factory=list)
    researches: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Author list (dipakai di /authors, /affiliations/authors/<id>, /subjects/detail)
# ---------------------------------------------------------------------------
def parse_author_cards(soup: BeautifulSoup) -> list[AuthorListItem]:
    """Parse kartu penulis dari halaman daftar.

    Dua varian markup didukung:
      A) /subjects/detail, /authors  -> div.list-item ... div.profile-name
      B) /affiliations/authors/<id>  -> div.au-item  ... div.profile-name
    """
    cards = soup.select("div.list-item")
    if not cards:
        cards = soup.select("div.au-item")
    out: list[AuthorListItem] = []

    for card in cards:
        name_link = card.select_one("div.profile-name a[href*='/authors/profile/']")
        if not name_link:
            continue
        item = AuthorListItem()
        item.name = clean(name_link.get_text())
        item.profile_url = name_link.get("href", "")
        item.sinta_id = _author_id(item.profile_url) or clean(
            _first_text(card, "div.profile-id")
        ).replace("SINTA ID", "").replace("ID", "").replace(":", "").strip()

        aff_link = card.select_one(
            "div.profile-affil a[href*='/affiliations/profile/'], "
            "div.affil-name a[href*='/affiliations/profile/']"
        )
        if aff_link:
            item.affiliation = clean(aff_link.get_text())
            item.affiliation_id = _affil_id(aff_link.get("href", ""))
        if not item.affiliation:
            item.affiliation = _first_text(card, "div.affil-name")

        dept_link = card.select_one("div.profile-dept a")
        if dept_link:
            item.department = clean(dept_link.get_text())

        item.subjects = [
            clean(a.get_text()) for a in card.select("ul.subject-list li a")
        ]

        loc = _first_text(card, "div.affil-loc")
        if loc:
            item.location = clean(loc)

        for num in card.select("div.pr-num"):
            txt = clean(num.get_text())
            label = clean(num.find_next_sibling("div").get_text()) if num.find_next_sibling("div") else ""
            if label:
                item.scores[label] = txt

        for span in card.select("div.profile-hindex span"):
            txt = clean(span.get_text())
            if ":" in txt:
                k, v = txt.split(":", 1)
                item.hindex[clean(k)] = clean(v)

        out.append(item)
    return out


def parse_total_records(soup: BeautifulSoup) -> tuple[int, int]:
    """'Page 1 of 459 | Total Records 4.581' -> (page, total_records)"""
    node = soup.select_one("div.pagination-text")
    text = clean(node.get_text()) if node else ""
    page = re.search(r"Page\s+([\d.]+)\s+of\s+([\d.]+)", text)
    total = re.search(r"Total Records\s+([\d.]+)", text)
    to_int = lambda s: int(s.replace(".", "")) if s else 0
    return (to_int(page.group(2)) if page else 1, to_int(total.group(1)) if total else 0)


# ---------------------------------------------------------------------------
# Affiliations
# ---------------------------------------------------------------------------
@dataclass
class Affiliation:
    affiliation_id: str = ""
    name: str = ""
    abbreviation: str = ""
    location: str = ""
    code: str = ""
    score_3yr: str = ""
    score_overall: str = ""
    authors_count: str = ""


def parse_affiliation_cards(soup: BeautifulSoup) -> list[Affiliation]:
    out: list[Affiliation] = []
    for card in soup.select("div.list-item"):
        link = card.select_one("div.affil-name a[href*='/affiliations/profile/']")
        if not link:
            continue
        aff = Affiliation()
        aff.name = clean(link.get_text())
        aff.affiliation_id = _affil_id(link.get("href", ""))
        aff.abbreviation = _first_text(card, "div.affil-abbrev").lstrip("-").strip()
        aff.location = _first_text(card, "div.affil-loc")
        pid = _first_text(card, "div.profile-id")
        m = re.search(r"ID\s*:\s*(\d+)\s*\|\s*CODE\s*:\s*(\S+)", pid)
        if m:
            aff.affiliation_id = aff.affiliation_id or m.group(1)
            aff.code = m.group(2)
        nums = [clean(n.get_text()) for n in card.select("div.pr-num")]
        aff.score_3yr = nums[0] if nums else ""
        aff.score_overall = nums[1] if len(nums) > 1 else ""
        stat = card.select_one("div.stat-prev")
        if stat:
            mt = re.search(r"([\d.,]+)\s*Authors", clean(stat.get_text()))
            aff.authors_count = mt.group(1) if mt else ""
        out.append(aff)
    return out


def parse_affiliation_location(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Dari halaman profil afiliasi: (nama, lokasi, singkatan)."""
    name = _first_text(soup, "div.univ-name h3")
    loc = _first_text(soup, "div.meta-profile a.affil-loc", "div.meta-profile")
    abbrev = _first_text(soup, "span.affil-abbrev").lstrip("-").strip()
    return name, clean(loc), abbrev


# ---------------------------------------------------------------------------
# Author profile
# ---------------------------------------------------------------------------
def parse_author_profile(soup: BeautifulSoup, source: str = "scopus") -> AuthorProfile:
    prof = AuthorProfile()
    h3 = soup.select_one("div.content-box h3") or soup.select_one("h3")
    prof.name = clean(h3.get_text()) if h3 else ""

    meta = soup.select_one("div.meta-profile")
    if meta:
        for a in meta.select("a"):
            icon = a.select_one("i")
            icon_cls = " ".join(icon.get("class", [])) if icon else ""
            text = clean(a.get_text())
            if "el-map-marker" in icon_cls:
                prof.affiliation = text
                prof.affiliation_id = _affil_id(a.get("href", ""))
            elif "el-child" in icon_cls:
                prof.department = text
            elif "el-user" in icon_cls:
                m = re.search(r"(\d+)", text)
                prof.sinta_id = m.group(1) if m else ""

    prof.subjects = [
        clean(a.get_text()) for a in soup.select("div.profile-subject ul.subject-list li a")
    ]

    for num in soup.select("div.stat-profile div.pr-num"):
        label_el = num.find_next_sibling("div", class_="pr-txt")
        if label_el:
            prof.scores[clean(label_el.get_text())] = clean(num.get_text())

    prof.location = _first_text(soup, "div.meta-profile a.affil-loc", "span.affil-loc")

    prof.publications = parse_publications(soup, source)
    prof.researches = [
        clean(a.get_text()) for a in soup.select("div.ar-title a")
    ] if source == "researches" else []
    return prof


def parse_publications(soup: BeautifulSoup, source: str = "scopus") -> list[Publication]:
    out: list[Publication] = []
    for item in soup.select("div.ar-list-item"):
        pub = Publication(source=source)
        title_a = item.select_one("div.ar-title a")
        if not title_a:
            continue
        pub.title = clean(title_a.get_text())
        pub.url = title_a.get("href", "")
        pub.year = clean(re.sub(r"\D", "", _first_text(item, "a.ar-year")) or "")
        pub.venue = _first_text(item, "a.ar-pub")
        pub.quartile = _first_text(item, "a.ar-quartile")
        pub.cited = _first_text(item, "a.ar-cited")
        meta_text = clean(item.select_one("div.ar-meta").get_text()) if item.select_one("div.ar-meta") else ""
        m = re.search(r"Author Order\s*:\s*(\d+)\s*of\s*(\d+)", meta_text)
        if m:
            pub.author_order = m.group(0)
        if not pub.venue:  # Google Scholar: "Authors : ... | Jurnal 6 (1), 407-416, 2026"
            for a in item.select("div.ar-meta a"):
                txt = clean(a.get_text())
                if re.search(r"\d{4}$", txt) and "," in txt:
                    pub.venue = txt
                    break
        out.append(pub)
    return out


# ---------------------------------------------------------------------------
# Views / URL builders
# ---------------------------------------------------------------------------
AUTHOR_VIEWS = ("scopus", "googlescholar", "garuda", "wos", "rama", "researches")

VIEW_LABEL = {
    "scopus": "Scopus",
    "googlescholar": "Google Scholar",
    "garuda": "Garuda",
    "wos": "Web of Science",
    "rama": "RAMA",
    "researches": "Researches",
}


def publications_for(items: Iterable[str]) -> list[str]:
    """Normalisasi argumen view -> daftar view yang valid."""
    out: list[str] = []
    for v in items:
        v = v.strip().lower()
        alias = {
            "gs": "googlescholar",
            "google": "googlescholar",
            "scholar": "googlescholar",
            "googlescholar": "googlescholar",
            "wos": "wos",
            "scopus": "scopus",
            "garuda": "garuda",
            "rama": "rama",
            "penelitian": "researches",
            "researches": "researches",
        }.get(v)
        if alias and alias not in out:
            out.append(alias)
    return out
