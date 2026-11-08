"""
Klasifikasi wilayah (provinsi/kota) dari string lokasi afiliasi SINTA.

SINTA menampilkan lokasi institusi dalam format:
    "KOTA ADM. JAKARTA BARAT - DKI JAKARTA, ID"
    "KAB. BOGOR - JAWA BARAT, ID"
    "KOTA SURABAYA - JAWA TIMUR, ID"

Modul ini memecah string tersebut lalu memetakan kota/kabupaten ke
preset wilayah (JABODETABEK, JABAR, dsb).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Preset wilayah
# ---------------------------------------------------------------------------
# Setiap preset berisi daftar *kota/kabupaten* (bukan hanya provinsi) supaya
# JABODETABEK tidak otomatis menarik seluruh Jawa Barat.
REGION_PRESETS: dict[str, set[str]] = {
    # Jakarta + Bodetabek (Bogor, Depok, Tangerang, Bekasi)
    "JABODETABEK": {
        "JAKARTA",  # semua "KOTA ADM. JAKARTA ..."
        "BOGOR",
        "DEPOK",
        "TANGERANG",
        "BEKASI",
    },
    # Inti DKI saja
    "DKI": {"JAKARTA"},
    # Bodetabek tanpa Jakarta
    "BODETABEK": {"BOGOR", "DEPOK", "TANGERANG", "BEKASI"},
    "JABAR": {
        "BANDUNG", "BOGOR", "DEPOK", "BEKASI", "TANGERANG", "CIREBON",
        "SUKABUMI", "TASIKMALAYA", "GARUT", "CIANJUR", "SUBANG",
        "PURWAKARTA", "KARAWANG", "INDRAMAYU", "MAJALENGKA", "SUMEDANG",
        "CIAMIS", "PANGANDARAN", "KUNINGAN", "BANJAR", "CILEGON", "SERANG",
    },
}

# Penjaga provinsi: kota hanya dihitung masuk preset bila provinsinya cocok.
# Mencegah "KOTA TANGERANG SELATAN" (Banten) dianggap bagian Jawa Barat.
REGION_PROVINCES: dict[str, set[str]] = {
    "JABODETABEK": {"DKI JAKARTA", "JAWA BARAT", "BANTEN"},
    "DKI": {"DKI JAKARTA"},
    "BODETABEK": {"JAWA BARAT", "BANTEN"},
    "JABAR": {"JAWA BARAT"},
    "INDONESIA": set(),  # semua
}

JABODETABEK_STRICT_NOTE = (
    "Preset JABODETABEK mencakup DKI Jakarta, Kota/Kab. Bogor, Kota/Kab. "
    "Depok, Kota/Kab. Tangerang (termasuk Tangsel) dan Kota/Kab. Bekasi."
)

_PREFIX = re.compile(
    r"^(KOTA ADM\.?|KOTAMADYA|KABUPATEN|KAB\.?|KOTA)\s+", re.I
)


def normalize(text: str) -> str:
    """Uppercase, buang aksen & spasi ganda."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


@dataclass
class Location:
    raw: str = ""
    city: str = ""       # mis. "JAKARTA BARAT", "BOGOR"
    city_full: str = ""  # mis. "KOTA ADM. JAKARTA BARAT"
    province: str = ""   # mis. "DKI JAKARTA"
    regions: set[str] = field(default_factory=set)

    @property
    def in_jabodetabek(self) -> bool:
        return "JABODETABEK" in self.regions or "DKI" in self.regions

    def as_dict(self) -> dict:
        return {
            "lokasi_raw": self.raw,
            "kota": self.city_full or self.city,
            "provinsi": self.province,
            "wilayah": ",".join(sorted(self.regions)),
            "is_jabodetabek": self.in_jabodetabek,
        }


def parse_location(raw: str) -> Location:
    """'KOTA ADM. JAKARTA BARAT - DKI JAKARTA, ID' -> Location(...)"""
    loc = Location(raw=raw or "")
    txt = normalize(raw)
    if not txt:
        return loc

    txt = re.sub(r",\s*ID$", "", txt)          # buang akhiran ", ID"
    parts = [p.strip() for p in txt.split(" - ") if p.strip()]
    city_full = parts[0] if parts else ""
    province = parts[1] if len(parts) > 1 else ""

    city = _PREFIX.sub("", city_full).strip()
    loc.city, loc.city_full, loc.province = city, city_full, province

    tokens = set(city.replace(".", " ").split())
    regions: set[str] = set()
    for name, cities in REGION_PRESETS.items():
        prov_guard = REGION_PROVINCES.get(name, set())
        if prov_guard and province and province not in prov_guard:
            continue  # kota bernama sama tapi provinsi berbeda -> lewati
        if any(c == city or c in tokens for c in cities):
            regions.add(name)
    loc.regions = regions
    return loc


def matches_regions(loc: Location, wanted: Iterable[str]) -> bool:
    """True bila lokasi masuk salah satu preset yang diminta."""
    wanted = {w.strip().upper() for w in wanted if w and w.strip()}
    if not wanted or "INDONESIA" in wanted or "ALL" in wanted:
        return True
    return bool(loc.regions & wanted)
