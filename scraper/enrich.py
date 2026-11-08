"""
Enrichment: pencocokan kata kunci, template "Bidang/Penelitian/Potensi kebutuhan",
skor prioritas, dan heuristik kontak.

Semua teks hasil scraping dinormalisasi lalu dicocokkan dengan daftar kata kunci
per template. Template bisa ditambah/diubah di PROFILES di bawah, atau dari file
JSON via --profile-file.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Template kebutuhan (silakan edit / tambah)
# ---------------------------------------------------------------------------
PROFILES: dict[str, dict] = {
    "farmasi_bahan_alam": {
        "bidang": "Farmasi bahan alam / Fitokimia",
        "penelitian": "Ekstraksi dan antioksidan",
        "potensi_kebutuhan": (
            "Preparasi ekstrak (maserasi/soxhlet/UAE/MAE), skrining fitokimia, "
            "penetapan kadar fenolik & flavonoid total, uji aktivitas antioksidan "
            "(DPPH/ABTS/FRAP), standarisasi ekstrak, dan analisis HPLC/LC-MS"
        ),
        "kata_kunci": [
            "farmasi", "pharmacy", "pharmaceutical", "farmakognosi",
            "fitokimia", "phytochem", "bahan alam", "natural product",
            "ekstrak", "extract", "ekstraksi", "extraction",
            "antioksidan", "antioxidant", "fenolik", "phenolic",
            "flavonoid", "flavonol", "alkaloid", "tanin", "terpenoid",
            "herbal", "herbal medicine", "jamu", "obat tradisionil",
            "simplisia", "DPPH", "ABTS", "FRAP", "fitomedisin",
            "makroalga", "microalga", "mikroalga", "rumput laut", "seaweed",
            "skimmi", "zeta", "prostaglandin", "immunomodulator",
            "kosmetik bahan alam", "biologi molekuler", "biokimia",
        ],
        "min_prioritas_tinggi": 4,   # jumlah hit kata kunci -> Tinggi
        "min_prioritas_sedang": 1,
    },
    "generic": {
        "bidang": "",
        "penelitian": "",
        "potensi_kebutuhan": "",
        "kata_kunci": [],
        "min_prioritas_tinggi": 99,
        "min_prioritas_sedang": 99,
    },
}

# Domain email institusi untuk *petunjuk* kontak (bukan email lengkap).
# Perluas sesuai kebutuhan; gunakan --contact untuk verifikasi domain via
# Google Scholar ("Verified email at ...").
AFFILIATION_DOMAINS: dict[str, str] = {
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
    "universitas budi luhur": "budiluhur.ac.id",
    "universitas bakrie": "bakrie.ac.id",
    "universitas pancasila": "univpancasila.ac.id",
    "universitas pembangunan nasional veteran jakarta": "upnvj.ac.id",
    "universitas islam negeri jakarta": "uinjkt.ac.id",
}

_WS = re.compile(r"\s+")


def norm(text: str) -> str:
    return _WS.sub(" ", (text or "").lower()).strip()


@dataclass
class Match:
    hits: list[str] = field(default_factory=list)
    bidang: str = ""
    penelitian: str = ""
    potensi: str = ""
    prioritas: str = "Rendah"
    skor: int = 0

    @property
    def relevan(self) -> bool:
        return bool(self.hits)


def load_profile(name_or_path: str) -> dict:
    if name_or_path in PROFILES:
        return PROFILES[name_or_path]
    path = Path(name_or_path)
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
        return {**PROFILES["generic"], **cfg}
    raise ValueError(
        f"Template '{name_or_path}' tidak dikenal. Pilihan: {', '.join(PROFILES)} "
        "atau path ke file JSON."
    )


def match_keywords(texts: Iterable[str], cfg: dict) -> list[str]:
    blob = norm(" | ".join(t for t in texts if t))
    hits: list[str] = []
    for kw in cfg.get("kata_kunci", []):
        if norm(kw) and norm(kw) in blob:
            hits.append(kw)
    return hits


def build_match(
    texts: Iterable[str],
    cfg: dict,
    *,
    is_jabodetabek: bool = False,
    pub_count: int = 0,
    score_3yr: float = 0.0,
    hindex: int = 0,
) -> Match:
    """Hitung kecocokan + skor prioritas 0-100."""
    hits = match_keywords(texts, cfg)
    m = Match(hits=hits)
    m.bidang = cfg.get("bidang", "")
    m.penelitian = cfg.get("penelitian", "")
    m.potensi = cfg.get("potensi_kebutuhan", "")

    # Prioritas dasar dari jumlah kata kunci yang cocok
    n = len(hits)
    if n >= cfg.get("min_prioritas_tinggi", 4):
        base = 55
    elif n >= cfg.get("min_prioritas_sedang", 1):
        base = 35
    else:
        base = 10

    # Bonus indikator produktivitas & wilayah
    if is_jabodetabek:
        base += 10
    base += min(pub_count, 10) * 2          # maks +20
    base += min(hindex, 15)                 # maks +15
    if score_3yr >= 500:
        base += 10
    elif score_3yr >= 100:
        base += 5

    m.skor = max(0, min(100, base))
    if m.skor >= 70:
        m.prioritas = "Tinggi"
    elif m.skor >= 45:
        m.prioritas = "Sedang"
    else:
        m.prioritas = "Rendah"
    return m


def rank_publications(pubs: list, cfg: dict, limit: int = 3) -> list:
    """Pilih 2-3 publikasi paling relevan (kata kunci > tahun terbaru)."""
    def key(p):
        title = getattr(p, "title", "") or ""
        hit = 1 if match_keywords([title], cfg) else 0
        try:
            year = int(getattr(p, "year", 0) or 0)
        except ValueError:
            year = 0
        return (-hit, -year)

    return sorted(pubs, key=key)[:limit]


def guess_domain(affiliation: str) -> str:
    a = norm(affiliation)
    for name, dom in AFFILIATION_DOMAINS.items():
        if name in a or a in name:
            return dom
    return ""


def guess_email(name: str, domain: str) -> str:
    """Dugaan alamat email (BELUM terverifikasi) – pakai hanya sebagai petunjuk."""
    if not domain:
        return ""
    parts = [p for p in re.split(r"[^A-Za-z]+", name.lower()) if len(p) > 1]
    if not parts:
        return ""
    if len(parts) == 1:
        local = parts[0]
    else:
        local = f"{parts[0]}.{parts[-1]}"
    return f"{local}@{domain}"


def linkedin_search_url(name: str, affiliation: str = "") -> str:
    from urllib.parse import quote_plus
    q = quote_plus(f"{name} {affiliation}".strip())
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"


def google_scholar_search_url(name: str) -> str:
    from urllib.parse import quote_plus
    return f"https://scholar.google.com/citations?view_op=search_authors&mauthors={quote_plus(name)}"
