"""
Uji autorun TANPA internet.

Menyalakan server SINTA tiruan (tests/fake_sinta_server.py) di 127.0.0.1,
menulis autorun_config.ini sementara, menjalankan `python autorun.py`,
lalu memeriksa hasilnya.

Jalankan:  python -m tests.test_autorun
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "autorun_config.ini"
TMP_CONFIG = ROOT / "hasil" / "uji_autorun_config.ini"
PREFIX = "hasil/uji_autorun"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_sinta_server import Handler  # noqa: E402

TEST_INI = """[seed]
subject_ids = 6518
affiliation_ids =
author_ids =
search_terms =
pages = 2

[filter]
region = JABODETABEK
limit = 0

[output]
views = scopus,googlescholar
pub_limit = 3
prefix = {prefix}

[jaringan]
delay = 0
relay = false
cache = false
selenium_fallback = false
""".format(prefix=PREFIX)


def main() -> int:
    ok = True

    def check(label: str, cond: bool, extra: str = "") -> None:
        nonlocal ok
        ok &= cond
        print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))

    port = 8899
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)
    print(f"Server tiruan jalan di http://127.0.0.1:{port}")

    backup = None
    try:
        if CONFIG.exists():
            backup = CONFIG.read_text(encoding="utf-8")
        (ROOT / "hasil").mkdir(exist_ok=True)
        CONFIG.write_text(TEST_INI, encoding="utf-8")

        env = os.environ.copy()
        env["SINTA_BASE_URL"] = f"http://127.0.0.1:{port}"
        env["PYTHONIOENCODING"] = "utf-8"

        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "autorun.py"), "--no-open"],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
        )
        dur = time.time() - t0
        out = proc.stdout + proc.stderr

        check("autorun.py selesai tanpa error", proc.returncode == 0,
              f"exit={proc.returncode}, {dur:.1f}s")
        check("config terbaca (seed subjek 6518)", "subjek      : 6518" in out)
        check("filter wilayah dilaporkan", "wilayah     : JABODETABEK" in out)
        check("dependency dicek tanpa install ulang",
              "Dependency belum lengkap" not in out)
        check("ringkasan BERHASIL dicetak", "BERHASIL" in out)

        csv_path = (ROOT / PREFIX).with_suffix(".csv")
        xlsx_path = (ROOT / PREFIX).with_suffix(".xlsx")
        json_path = (ROOT / PREFIX).with_suffix(".json")
        check("CSV dibuat", csv_path.exists(), str(csv_path))
        check("XLSX dibuat", xlsx_path.exists())
        check("JSON dibuat", json_path.exists())

        import csv as csvmod
        with csv_path.open(encoding="utf-8-sig") as fh:
            rows = list(csvmod.DictReader(fh))
        check("2 dosen lolos filter JABODETABEK", len(rows) == 2, f"{len(rows)} baris")
        names = {r["Nama"] for r in rows}
        check("UI & Tarumanagara masuk", names == {"RINA FITRIANI", "SITI AMINAH"},
              str(names))
        check("Unpad (Sumedang) & ITB (Bandung) tersaring",
              "BUDI SANTOSO" not in names and "AGUS PRASETYO" not in names)
        check("kolom sesuai format",
              {"Nama", "Institusi", "Bidang", "Penelitian", "Publikasi",
               "Potensi kebutuhan", "Kontak Email", "Prioritas"} <= set(rows[0]),
              f"{len(rows[0])} kolom")
        check("email institusi terisi",
              rows[0]["Kontak Email"].endswith((".ac.id", ".contoh.id", "ac.id")),
              rows[0]["Kontak Email"])
        check("prioritas terisi", rows[0]["Prioritas"] in ("Tinggi", "Sedang", "Rendah"),
              rows[0]["Prioritas"])
        check("publikasi tanpa duplikat",
              len(set(rows[0]["Publikasi"].split(" || "))) ==
              len(rows[0]["Publikasi"].split(" || ")))
        check("log autorun tersimpan", any((ROOT / "logs").glob("autorun_*.log")))
        check("ETA ditampilkan", "ETA" in out, "fase 1 & 2")
        check("perkiraan durasi ditampilkan", "perkiraan" in out)
        check("laju fase 2 dilaporkan", "dosen/detik" in out)
        check("thread paralel dipakai", "thread" in out)
        check("fase 1 tidak melewati halaman terakhir", "hal 3/" not in out,
              "mock hanya 2 halaman")
        check("fase 1 ditutup dengan ringkasan", "fase 1 selesai" in out)
        check("filter lokasi punya progress", "STEP 1b" in out and "lokasi 1/" in out)
        check("filter lokasi punya ETA", "perkiraan cek lokasi" in out)

        # --- mode kampus: tanpa menyapu subjek sama sekali -----------------
        CONFIG.write_text(TEST_INI.replace(
            "subject_ids = 6518", "subject_ids =\nmode = kampus"), encoding="utf-8")
        proc2 = subprocess.run(
            [sys.executable, str(ROOT / "autorun.py"), "--no-open"],
            cwd=str(ROOT), env=env, capture_output=True, text=True)
        out2 = proc2.stdout + proc2.stderr
        check("mode kampus jalan", proc2.returncode == 0, f"exit={proc2.returncode}")
        check("kampus disaring duluan", "mode kampus: memindai daftar institusi" in out2)
        check("kampus non-Jabodetabek tidak dibuka",
              "Institut Teknologi Bandung" not in out2.split("dibuka")[0],
              "")
        check("mode kampus menghasilkan baris", "BERHASIL" in out2)

    finally:
        server.shutdown()
        server.server_close()
        if backup is not None:
            CONFIG.write_text(backup, encoding="utf-8")
        elif CONFIG.exists():
            CONFIG.unlink()
        if TMP_CONFIG.exists():
            TMP_CONFIG.unlink()

    print("\n" + ("SEMUA TES AUTORUN LULUS ✔" if ok else "ADA TES AUTORUN GAGAL ✘"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
