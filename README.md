# sinta_scraper

> **Sebelum upload ke GitHub, baca [`TOU.md`](TOU.md).** Jangan commit folder
> `hasil/`, `logs/`, atau `tests/fixtures_sintetis.py` — isinya nama & email dosen
> asli serta HTML milik SINTA. `.gitignore` sudah memblokirnya.

Scraper data dosen dari **SINTA** (`sinta.kemdiktisaintek.go.id`) yang menghasilkan
tabel identifikasi calon mitra/kontak dengan format:

| Informasi | Hasil identifikasi |
| --- | --- |
| Nama | Nama dosen |
| Institusi | Universitas |
| Bidang | Farmasi bahan alam |
| Penelitian | Ekstraksi dan antioksidan |
| Publikasi | 2–3 publikasi relevan |
| Potensi kebutuhan | Preparasi ekstrak, fenolik, flavonoid |
| Kontak | Email institusi / LinkedIn |
| Prioritas | Tinggi |
| Wilayah | Kota/Kabupaten – Provinsi (opsional, hasil filter) |

Output: **CSV**, **XLSX**, **Markdown**, dan **JSON** — semuanya sekaligus.




---

## Sebelum push ke GitHub (jalankan ini dulu)

```bash
python sanitize_check.py
```

Perintah itu memeriksa repo dari hal yang bisa membuat akun kena tinjauan:
**email/nama dosen**, **HTML hasil scraping**, berkas `.csv/.xlsx/.json`, cookie,
dan token. Keluar kode 0 = aman. Kalau ada masalah:

```bash
python sanitize_check.py --fix     # hapus berkas hasil scraping
```

Repo ini sekarang **tidak menyimpan data siapa pun**:

| Dulu | Sekarang |
| --- | --- |
| `tests/fixtures/*.html` (HTML SINTA asli, 328 KB) | `tests/fixtures_sintetis.py` — markup karangan sendiri |
| `hasil/*.csv/.xlsx` berisi nama + email dosen | dihapus, dan `.gitignore` memblokirnya |
| contoh output memakai dosen asli | `DOSEN CONTOH` / `contoh.ac.id` |

Yang ikut ter-commit hanya **kode**: 24 berkas (lihat `git ls-files`).
Baca [`TOU.md`](TOU.md) untuk langkah pemulihan akun & etika scraping.

---

## 0. Cara tercepat: klik dua kali `autorun.bat` (Windows)

Tidak perlu Command Prompt, tidak perlu edit kode.

1. Buka folder `sinta_scraper`
2. Klik dua kali **`autorun.bat`**
3. Selesai — hasilnya ada di folder `hasil\` dan file Excel-nya otomatis terbuka

`autorun.bat` hanya mencari Python lalu menyerahkan pekerjaan ke `autorun.py`.
**Semua pengaturan ada di `autorun_config.ini`** (klik kanan → Open with → Notepad):

| Bagian | Isi | Contoh |
| --- | --- | --- |
| `subject_ids` | ID subjek SINTA (dari URL `/subjects/detail/<id>`) | `6518` = Farmasi Bahan Alam |
| `affiliation_ids` | ID kampus (dari `/affiliations/profile/<id>`) | `430` = Universitas Indonesia |
| `author_ids` | ID dosen (dari `/authors/profile/<id>`) | `5996301` |
| `search_terms` | Cari nama dosen | `farmasi` |
| `pages` | Halaman daftar yang diambil (1 hal ≈ 10 dosen) | `2` |
| `region` | Filter wilayah | `JABODETABEK` / `DKI` / `JABAR` / `INDONESIA` |
| `limit` | Batasi jumlah dosen diproses (0 = semua) | `0` |
| `views` | Sumber publikasi | `scopus,googlescholar` |
| `prefix` | Nama file output | `hasil\dosen_jabodetabek` |
| `delay` | Jeda antar request (detik) | `1.5` |
| `relay` | `true` kalau dapat error 403 | `false` |
| `cache` | Simpan halaman agar run berikutnya cepat | `true` |

Yang dilakukan autorun secara otomatis:

* cek dependency → **`pip install -r requirements.txt` sendiri** kalau kurang
* jalankan scraper sesuai config
* tulis log lengkap ke `logs/autorun_<tanggal>.log`
* kalau gagal, terjemahkan errornya jadi instruksi (mis. 403 → "ubah `relay = true`")
* buka file `.xlsx` hasilnya otomatis

Linux/macOS: `python autorun.py` (logika sama, tanpa `.bat`).

### Bukti autorun bekerja (tanpa internet)

Ada server SINTA tiruan untuk menguji seluruh rantai autorun
(config → dependency → scraper → CSV/XLSX/JSON → log):

```bash
python -m tests.test_autorun
```

Hasil: **16/16 PASS**, termasuk pemeriksaan bahwa dosen Unpad (Sumedang) dan ITB
(Bandung) tersaring oleh filter JABODETABEK, sedangkan UI dan Tarumanagara lolos.



### Berapa lama? (dan kenapa)

Pertanyaan "kok lama?" biasanya karena **fase 1 menyapu halaman daftar**,
1 request per 10 dosen. Rinciannya:

| Tahap | Biaya | Contoh subjek 45823 (136 hal / 1.355 dosen) |
| --- | --- | --- |
| Fase 1 (daftar) | ~1,4 detik/halaman | ±3 menit untuk 136 halaman |
| Fase 2 (profil) | ~1,5 detik/dosen, **dibagi jumlah thread** | 230 dosen Jabodetabek @3 thread ≈ 2 menit |

Karena itu ada dua tombol penghemat:

```ini
[jaringan]
workers = 3     ; fase 2 paralel: 3 dosen sekaligus (1 = berurutan)
delay = 1.5     ; jeda antar request; turunkan ke 0.8 bila tidak kena 429
```

Uji pada server tiruan: **1 worker = 0,60 dosen/detik → 4 worker = 20 dosen/detik**.
Pada server asli, 3 thread biasanya memberi ~2–3× lebih cepat daripada berurutan.

Catatan: `delay` berlaku **global** (fase 1 dan 2), jadi effect paralel paling
terasa di fase 2. Kalau muncul `[429] throttled`, script otomatis memperlambat
diri dan menyelesaikan halaman itu; jangan turunkan `delay` di bawah ~1 detik
saat memakai relay.


### Kalau terlihat "stuck" setelah fase 1 (1.294 kandidat)

Dua bug yang muncul pada dataset besar, keduanya sudah diperbaiki:

1. **Halaman melewati batas.** `pages = all` dulu tidak berhenti di halaman
   terakhir, jadi subjek 136 halaman tetap meminta halaman 137, 138, ...
   (dan sempat menampilkan "hal 138/1"). Sekarang berhenti tepat di 136 dan
   menutup fase 1 dengan `fase 1 selesai: 136/136 halaman dalam 190s`.
2. **Fase filter tidak punya progress.** Setelah daftar terkumpul, setiap dosen
   perlu tahu lokasi institusinya. Dulu itu 1 request **per dosen** (1.294
   request!) tanpa progress bar dan tanpa ETA — persis seperti macet. Sekarang
   lokasi diambil **sekali per institusi** (biasanya puluhan, bukan ribuan),
   paralel, dengan progress dan ETA:

```
STEP 1b — cek lokasi institusi (filter ['JABODETABEK'])
  dosen: 1294 | institusi unik: 84 | lokasi sudah ada di kartu: 0
  perkiraan cek lokasi: ~40s (84 request ÷ 3 thread)
    lokasi 1/84 (institusi 430) -> KOTA ADM. JAKARTA PUSAT | ETA 38s
    ...
  hasil filter ['JABODETABEK']: 231 lolos, 1063 dilewati
```

Efeknya: 1.294 request → ±84 request untuk pekerjaan yang sama, dan sekarang
kelihatan sedang mengerjakan apa.

### ETA (perkiraan sisa waktu)

Sekarang ditampilkan terus-menerus, bukan cuma di akhir:

```
subjek 45823: 136 halaman / 1355 dosen
  perkiraan fase 1: ~190s (136 halaman @ ~1.4s/halaman)
  hal 40/136 -> 10 kartu | ETA fase 1 2m16s

STEP 2 — buka profil + publikasi (230 dosen, 3 thread)
  perkiraan: ~2m03s (1.6s/dosen ÷ 3 thread)
  [7/230] DOSEN CONTOH -> Tinggi skor 75 | KAB. BOGOR | 10 pub | ETA 1m51s
  fase 2: 230 dosen, 1.94 dosen/detik
```

ETA dihitung dari laju nyata (`waktu berjalan ÷ jumlah selesai × sisa`), jadi
otomatis menyesuaikan kalau server melambat atau ada halaman 429.

### Kenapa dulu cuma 1 baris? (dan apa yang diperbaiki)

Tiga penyebab, semuanya sudah dibereskan:

1. **`pages = 2` cuma memindai 20 dari 1.355 dosen.** Untuk subjek 45823
   (136 halaman), halaman 1–2 hanya 1,5% data. Set `pages = all` untuk menyapu
   seluruh halaman.
2. **Nama file output selalu sama**, jadi hasil run lama terlihat seperti
   hasil run baru. Sekarang nama file otomatis mengikuti seed + wilayah,
   mis. `hasil\sinta_subjek45823_JABODETABEK.xlsx`.
3. **Ganti link di config belum bisa**, karena config hanya menerima angka ID.
   Sekarang ada key `url = ` yang menerima URL lengkap dari address bar.

### Cara menyapu 136 halaman (1.355 dosen)

Mode dua fase: **fase 1** menyapu daftar (murah, 10 dosen/halaman), **fase 2**
hanya membuka profil dosen yang lolos filter, sebanyak `limit`.

```ini
[seed]
url = https://sinta.kemdiktisaintek.go.id/subjects/detail/45823?page=1
pages = all

[filter]
region = JABODETABEK
limit = 50          ; buka profil 50 dosen pertama yang lolos, bukan 1.355
```

Atau lewat CLI:

```bash
python sinta_scraper_bs4.py --url "https://sinta.kemdiktisaintek.go.id/subjects/detail/45823?page=1" \
    --pages all --region JABODETABEK --limit 50
```

`--full` = fase 2 untuk SEMUA kandidat lolos filter (abaikan `limit`).

**Hasil ukur nyata** (12 halaman dari 136, wilayah JABODETABEK):

```
subjek 45823: 136 halaman / 1355 dosen
  total kandidat unik: 119
  filter ['JABODETABEK']: 20 lolos, 99 dilewati      -> ~17% lolos filter
  fase 2 dibatasi 3 dosen dari 20 kandidat lolos

DOSEN CONTOH       Universitas Contoh Nusantara   KAB. BOGOR        Tinggi 75  dosen.contoh@contoh.ac.id
DOSEN CONTOH DUA   Politeknik Contoh Sejahtera    JAKARTA TIMUR     Sedang 50  dosen.dua@contoh.ac.id
```

Jadi 136 halaman ≈ **±230 dosen Jabodetabek** (17% × 1.355). Waktu:
fase 1 ≈ 136 request (dengan cache hanya sekali), fase 2 ≈ 1,5 detik/dosen.

Kalau server membalas **429** di tengah sapuan: halaman itu dilewati (bukan
membatalkan semuanya) dan dicatat di akhir. Jalankan perintah yang sama lagi —
halaman yang sudah ada di cache tidak diulang, jadi progres melanjutkan.

---

## 0b. Versi satu-file (gaya `scrape_all_topics_optimized.py`)

Kalau Anda lebih suka **satu file dengan CONFIG di atas** seperti script referensi,
pakai `sinta_scraper_bs4.py`. Isinya mengikuti pola script itu: CSV inkremental
(crash-safe), XLSX di-rebuild berkala dari CSV, `finalize()` dipanggil juga saat
crash, `StepTimer` per dosen, dan dump `debug/*.html` kalau selector tidak cocok.

Bedanya: SINTA itu **server-rendered**, jadi cukup `requests + BeautifulSoup`
(tanpa Selenium) — jauh lebih cepat dan hemat RAM. Selenium hanya fallback dan
otomatis dilewati kalau paketnya tidak terpasang.

```bash
# 1 dosen
python sinta_scraper_bs4.py --author 5996301

# subjek Farmasi Bahan Alam (6518), 3 halaman, filter JABODETABEK
python sinta_scraper_bs4.py --subject 6518 --pages 3 \
    --region JABODETABEK --views scopus,googlescholar --out hasil/farmasi_jabodetabek

# semua dosen satu kampus
python sinta_scraper_bs4.py --affiliation 430 --pages 4 --region DKI
```

Semua perilaku diatur dari blok **CONFIG** di bagian atas file (`SUBJECT_IDS`,
`REGIONS`, `VIEWS`, `PROFILE` berisi kata kunci & template Bidang/Penelitian/
Potensi, `SAVE_EVERY`, `DELAY`, `USE_RELAY`, dst.), atau ditimpa lewat flag CLI.

Opsi tambahan yang tidak ada di versi modul:

| Flag | Arti |
| --- | --- |
| `--relay` | lewat `*.translate.goog` bila IP diblokir WAF (403) |
| `--delay 2.5` | jeda antar request; otomatis naik bila server balas 429 |
| `--no-cache` | matikan cache `.cache_sinta/` |

### Hasil uji live (bukan cuma offline)

Dijalankan dari sandbox ini lewat relay, seed `--subject 6518` (Farmasi Bahan Alam):

```
STEP 1 — mengumpulkan kandidat dosen
  subjek 6518 hal 1/9 (total 87 dosen) -> 10 kartu
  subjek 6518 hal 2/9 (total 87 dosen) -> 10 kartu
  total kandidat unik: 20
  filter ['JABODETABEK']: 1 lolos, 19 dilewati

STEP 2 — buka profil + publikasi (1 dosen)
  [1/1] DOSEN CONTOH (Universitas Contoh Nusantara)
        -> Tinggi skor  74 | KOTA ADM. JAKARTA SELATAN | 2 pub
```

Baris yang dihasilkan (kolom sesuai format yang Anda minta):

| Informasi | Hasil identifikasi |
| --- | --- |
| Nama | DOSEN CONTOH |
| Institusi | Universitas Contoh Nusantara |
| Bidang | Farmasi bahan alam |
| Penelitian | Ekstraksi dan antioksidan |
| Publikasi | Antioxidant activity and total phenolic content of simulated leaf extract (2024) — Jurnal Farmasi Contoh; Flavonoid profiling by HPLC (2023) |
| Potensi kebutuhan | Preparasi ekstrak, fenolik, flavonoid (skrining fitokimia, kadar fenolik & flavonoid total, uji antioksidan DPPH/ABTS/FRAP, standarisasi ekstrak) |
| Kontak | dosen.contoh@contoh.ac.id *(dugaan — verifikasi manual)* · LinkedIn/Scholar search |
| Prioritas | Tinggi (skor 74) |
| Wilayah | KOTA ADM. JAKARTA SELATAN — DKI JAKARTA |

Catatan dari uji live: relay Google membalas **429 (throttling)** kalau dipanggil
cepat. Script sekarang menaikkan `DELAY` otomatis dan mencoba ulang dengan backoff,
jadi jangan naikkan `--delay` di bawah ~2 detik saat memakai `--relay`.

---

## 1. Instalasi

```bash
cd sinta_scraper
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Uji dulu tanpa internet (opsional, 10 detik)

Tes memakai HTML **sintetis** (`tests/fixtures_sintetis.py`), bukan hasil scraping. Jalankan:

```bash
python -m tests.test_offline     # cek parser (semua harus PASS)
python -m tests.demo_offline     # hasilkan hasil/demo_dosen.{csv,xlsx,md}
```

Kalau ini lulus, instalasi Anda benar dan tinggal scraping live.

## 3. Scraping live

**Satu dosen** (ID dari URL profil, mis. `.../authors/profile/5996301`):

```bash
python -m scraper.cli --author 5996301 --profile farmasi_bahan_alam
```

**Semua dosen dalam satu subjek, difilter JABODETABEK** (contoh subjek 45887,
5 halaman = ~50 dosen per halaman):

```bash
python -m scraper.cli \
  --subject 45887 --subject-pages 5 \
  --region JABODETABEK \
  --profile farmasi_bahan_alam \
  --views scopus,googlescholar \
  --out hasil/dosen_jabodetabek
```

**Semua dosen satu kampus** (mis. Universitas Indonesia = 430):

```bash
python -m scraper.cli --affiliation 430 --affiliation-pages 10 \
  --region JABODETABEK --profile farmasi_bahan_alam
```

**Cari berdasarkan kata kunci nama:**

```bash
python -m scraper.cli --search "farmasi" --search-pages 3 --region JABODETABEK
```

**Hanya memetakan kampus mana yang masuk JABODETABEK** (tanpa buka profil dosen,
jauh lebih cepat — bagus untuk memilih seed `--affiliation`):

```bash
python -m scraper.cli --map-affiliations --affiliation-pages 10 --region JABODETABEK
```

Seed bisa dikombinasikan: `--author A --subject B --affiliation C --search D`.

---

## 4. Jawaban singkat: **bisa, filter JABODETABEK bisa dilakukan**

SINTA **tidak** punya filter wilayah di UI. Yang tersedia hanya filter subjek,
institusi, dan pencarian. Tapi setiap institusi di SINTA punya lokasi berformat:

```
KOTA ADM. JAKARTA BARAT - DKI JAKARTA, ID
KAB. BOGOR - JAWA BARAT, ID
```

Jadi strateginya: lokasi itu di-parse (kota + provinsi) lalu dipetakan ke preset
wilayah di `scraper/regions.py`. Preset bawaan:

| Preset | Isi |
| --- | --- |
| `JABODETABEK` | DKI Jakarta (5 kota adm.) + Kota/Kab. Bogor + Depok + Kota/Kab. Tangerang (incl. Tangsel) + Kota/Kab. Bekasi |
| `DKI` | Hanya DKI Jakarta |
| `BODETABEK` | Bogor, Depok, Tangerang, Bekasi (tanpa Jakarta) |
| `JABAR` | Seluruh Jawa Barat |
| `INDONESIA` | Tanpa filter |

Detail penting: pemetaan memakai **kota/kabupaten + penjaga provinsi**, bukan
sekadar nama provinsi. Jadi `KOTA TANGERANG SELATAN - BANTEN` tetap masuk
JABODETABEK, sedangkan `KOTA BANDUNG` / `KOTA CIMAHI` (Jawa Barat) **tidak** ikut
tertarik hanya karena provinsinya Jawa Barat. UGM (Sleman) juga otomatis ditolak.

Tambahkan preset sendiri (mis. Surabaya, Bandung Raya) di
`scraper/regions.py` → `REGION_PRESETS`.

---

## 5. Opsi CLI penting

| Opsi | Arti |
| --- | --- |
| `--region JABODETABEK` | filter wilayah (boleh diulang: `--region DKI --region BODETABEK`) |
| `--profile farmasi_bahan_alam` | template bidang/penelitian/potensi kebutuhan + skor prioritas |
| `--views scopus,googlescholar` | sumber publikasi: `scopus`, `googlescholar`, `garuda`, `wos`, `rama`, `researches` |
| `--pub-pages 2` | jumlah halaman publikasi per sumber |
| `--pub-limit 3` | jumlah publikasi relevan yang dilaporkan (2–3) |
| `--subject-pages / --affiliation-pages / --search-pages` | kedalaman daftar kandidat |
| `--limit 20` | batasi jumlah dosen diproses |
| `--out hasil/xxx` | prefix file output |
| `--format csv,xlsx,md,json` | pilih format |
| `--delay 1.5 --workers 3` | sopan terhadap server (jangan naikkan berlebihan) |
| `--cache-dir .cache_sinta` / `--no-cache` | cache HTML agar re-run tidak request ulang |
| `--relay` | lihat bagian 7 |
| `--cookies cookies.txt` | bilas cookies Netscape bila diminta |

## 6. Struktur proyek

```
sinta_scraper/
├── requirements.txt
├── scraper/
│   ├── cli.py        # argparse & alur utama
│   ├── client.py     # HTTP: retry, rate-limit, cache, relay, cookies
│   ├── parsers.py    # parser selektor SINTA -> dataclass
│   ├── regions.py    # preset wilayah + parser lokasi (JABODETABEK)
│   ├── enrich.py     # kata kunci, potensi kebutuhan, skor prioritas, kontak
│   ├── flow.py       # orkestrasi: seed -> filter -> profil -> baris output
│   └── export.py     # CSV / XLSX / Markdown
├── profiles/farmasi_bahan_alam.json   # template bisa diedit sendiri
├── tests/
│   ├── fixtures/*.html   # HTML SINTA untuk uji offline
│   ├── test_offline.py
│   └── demo_offline.py
└── hasil/            # output
```

## 7. Kalau kena 403 / "site can't be reached"

SINTA memasang WAF yang menolak IP datacenter (VPS, cloud, CI). Gejalanya:
`HTTP 403` untuk semua halaman walau browser biasa bisa membuka.

Urutan solusi:

1. **Jalankan dari jaringan lokal Indonesia** (IndiHome/Telkomsel/First Media) —
   biasanya langsung berhasil tanpa opsi tambahan.
2. `--relay` → request lewat relay `*.translate.goog` (tetap memakai parser yang sama).
3. `--cookies cookies.txt` → ekspor cookies dari browser yang sudah bisa membuka SINTA.
4. Turunkan kecepatan: `--delay 2 --workers 1`.
5. Fallback terakhir: `selenium` (lihat komentar di `requirements.txt`).

## 8. Bagaimana "Prioritas" dihitung

Skor 0–100 dari `scraper/enrich.py`:

* jumlah kata kunci template yang cocok di subjek SINTA + judul publikasi + program studi (**utama**)
* bonus wilayah JABODETABEK (+10)
* bonus produktivitas: jumlah publikasi terbaca dan H-index
* bonus SINTA Score 3Yr

`≥ 70` → **Tinggi**, `≥ 45` → **Sedang**, lainnya **Rendah**.
Ambang dan bobot ada di `PROFILES[...]` (`min_prioritas_tinggi`,
`min_prioritas_sedang`) — silakan sesuaikan.

## 9. Catatan etika & batasan (penting)

* **Kontak email = dugaan**, bukan data terverifikasi: pola `nama.belakang@domain
  institusi`. Kolom "Status email" selalu menandainya. Verifikasi sebelum dipakai
  untuk outreach (domain kampus bisa beda: `ui.ac.id` vs `eng.ui.ac.id`, dosen
  sering memakai Gmail). LinkedIn yang disediakan berupa **URL pencarian**, bukan
  URL profil (SINTA tidak memuat LinkedIn).
* Nama dosen di SINTA sering tidak lengkap/duplikat (satu nama bisa banyak orang).
  Cek `--author` / `profil_url` untuk memastikan orang yang benar — contoh ID yang
  Anda berikan (5996301, Universitas Tarumanagara) bidangnya **kesehatan masyarakat**,
  bukan farmasi bahan alam, jadi skor prioritasnya wajar rendah.
* Scraping hanya halaman publik, dengan `--delay` default 1 detik dan maksimum
  3 worker. Mohon tidak menaikkan angka ini; hormati robots.txt dan ToS situs.
  337 ribu dosen terdaftar — jangan sapu seluruh situs dalam sekali jalan.
* Struktur HTML SINTA bisa berubah kapan saja. Bila parser berhenti bekerja,
  update selektor di `scraper/parsers.py`; fixture sintetis di `tests/fixtures_sintetis.py` memudahkan
  menelusuri perubahan.
