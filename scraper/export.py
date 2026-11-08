"""Ekspor hasil scraping: CSV, XLSX, Markdown (format 'Informasi | Hasil identifikasi')."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

# Urutan kolom CSV/XLSX (mengikuti format yang diminta)
COLUMNS: list[tuple[str, str]] = [
    ("nama", "Nama"),
    ("institusi", "Institusi"),
    ("bidang", "Bidang"),
    ("penelitian", "Penelitian"),
    ("publikasi", "Publikasi"),
    ("potensi_kebutuhan", "Potensi kebutuhan"),
    ("kontak_email", "Kontak - Email institusi"),
    ("kontak_email_status", "Kontak - Status email"),
    ("kontak_scholar", "Kontak - Google Scholar"),
    ("kontak_linkedin", "Kontak - LinkedIn"),
    ("prioritas", "Prioritas"),
    ("skor_prioritas", "Skor prioritas"),
    ("wilayah", "Wilayah"),
    ("kota", "Kota/Kabupaten"),
    ("provinsi", "Provinsi"),
    ("program_studi", "Program studi"),
    ("subjek_sinta", "Subjek SINTA"),
    ("sinta_id", "SINTA ID"),
    ("sinta_score_3yr", "SINTA Score 3Yr"),
    ("h_index", "H-index"),
    ("kata_kunci_cocok", "Kata kunci cocok"),
    ("jumlah_publikasi_terbaca", "Jumlah publikasi terbaca"),
    ("sinopsis_penelitian_sinta", "Sinopsis penelitian (SINTA)"),
    ("profil_url", "URL profil SINTA"),
]


def _cell(row: dict, key: str) -> str:
    val = row.get(key, "")
    if isinstance(val, list):
        return " | ".join(str(v) for v in val)
    return "" if val is None else str(val)


def write_csv(rows: Iterable[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow([label for _, label in COLUMNS])
        for row in rows:
            writer.writerow([_cell(row, key) for key, _ in COLUMNS])
    return path


def write_xlsx(rows: list[dict], path: str | Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Dosen"

    headers = [label for _, label in COLUMNS]
    ws.append(headers)
    for row in rows:
        ws.append([_cell(row, key) for key, _ in COLUMNS])

    head_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    widths = {
        "Nama": 26, "Institusi": 30, "Bidang": 26, "Penelitian": 26,
        "Publikasi": 60, "Potensi kebutuhan": 50, "Prioritas": 10,
        "Kontak - Email institusi": 28, "Kontak - Status email": 34,
        "Subjek SINTA": 34, "URL profil SINTA": 42, "Sinopsis penelitian (SINTA)": 40,
    }
    for idx, label in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = widths.get(label, 16)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)
    return path


def write_markdown(rows: list[dict], path: str | Path, title: str = "Hasil scraping SINTA") -> Path:
    """Tabel 'Informasi | Hasil identifikasi' per dosen (format yang diminta)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]

    for i, row in enumerate(rows, 1):
        pubs = row.get("publikasi") or []
        if isinstance(pubs, str):
            pubs = [p.strip() for p in pubs.split("||") if p.strip()]
        lines += [
            f"## {i}. {row.get('nama', '')}",
            "",
            "| Informasi | Hasil identifikasi |",
            "| --- | --- |",
            f"| Nama | {row.get('nama', '')} |",
            f"| Institusi | {row.get('institusi', '')} |",
            f"| Bidang | {row.get('bidang', '')} |",
            f"| Penelitian | {row.get('penelitian', '')} |",
            f"| Publikasi | {'<br>'.join(f'- {p}' for p in pubs)} |",
            f"| Potensi kebutuhan | {row.get('potensi_kebutuhan', '')} |",
            f"| Kontak | {row.get('kontak_email', '') or '-'}"
            f"{' (dugaan)' if row.get('kontak_email') else ''} · "
            f"[Google Scholar]({row.get('kontak_scholar', '')}) · "
            f"[LinkedIn]({row.get('kontak_linkedin', '')}) |",
            f"| Prioritas | {row.get('prioritas', '')} (skor {row.get('skor_prioritas', '')}) |",
            f"| Wilayah | {row.get('kota', '')} - {row.get('provinsi', '')} "
            f"[{row.get('wilayah', '')}] |",
            f"| Sumber | [Profil SINTA]({row.get('profil_url', '')}) |",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
