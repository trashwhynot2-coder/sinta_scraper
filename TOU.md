# Sebelum mempublikasikan repo ini (WAJIB DIBACA)

Repo ini adalah alat scraping. Kalau di-upload apa adanya, ada tiga hal yang
bisa membuat repo (atau akun) kena tinjauan — dan satu di antaranya melanggar
GitHub Terms of Service:

## 1. Yang PALING berisiko: ini melanggar GitHub ToS

GitHub melarang **scraping otomatis saat mengakses GitHub** (bukan scraping
situs lain), tetapi yang juga dilarang adalah **mempublikasikan data pribadi
orang lain** dan **membagikan konten pihak ketiga yang bukan hak Anda**.

Yang bermasalah di repo ini:

| Isi | Masalah |
| --- | --- |
| `hasil/*.csv`, `*.xlsx`, `*.json` | **Nama + email dosen asli** = data pribadi. Email di sini masih **dugaan** (pola nama@domain), jadi bisa salah orang. Ini persis kategori yang dilaporkan sebagai doxxing/PII. |
| `tests/fixtures/*.html` | HTML utuh milik SINTA (Kemdiktisaintek). Bukan karya Anda; mendistribusikan ulang = masalah hak cipta. |
| `logs/` | Berisi daftar nama yang diproses. |

**Sudah ditambahkan `.gitignore`** yang memblokir semuanya (terverifikasi:
0 berkas sensitif lolos). Tapi `.gitignore` hanya bekerja untuk commit BARU —
kalau data itu sudah pernah ter-push, ia tetap ada di riwayat Git.

## 2. Kalau akun sudah terlanjur suspended

1. Jangan buat akun baru untuk meng-upload ulang hal yang sama (bisa dianggap
   circumvention dan memperberat).
2. Ajukan banding lewat https://support.github.com/contact — jelaskan singkat,
   jujur, dan tunjukkan itikad: "saya sudah menghapus data pribadi & HTML pihak
   ketiga, ini repo yang sudah dibersihkan".
3. Kalau repo dipulihkan: **hapus riwayatnya**, bukan hanya commit terakhir:

```bash
# opsi A: mulai repo baru tanpa riwayat lama
rm -rf .git
git init && git add . && git commit -m "SINTA scraper (tanpa data pribadi)"
git remote add origin <repo-baru> && git push -f origin main

# opsi B: bersihkan riwayat yang sudah terlanjur
# (butuh git-filter-repo; tulis ulang seluruh sejarah)
git filter-repo --path hasil --path logs --path tests/fixtures --invert-paths
```

## 3. Etika & aturan SINTA sendiri

* Hanya halaman **publik**, tanpa login, tanpa menembus proteksi.
* Hormati kecepatan: `delay` ≥ 1 detik, `workers` ≤ 3. Jangan sapu 337 ribu
  dosen dalam sekali jalan.
* Email di kolom "Kontak" adalah **dugaan**, bukan data terverifikasi. Untuk
  outreach, verifikasi dulu — dan pertimbangkan UU PDP (UU 27/2022): data dosen
  yang dikumpulkan untuk kontak komersial tanpa dasar pemrosesan bisa bermasalah.
* Jangan jual/bagikan dataset hasil scraping.

## 4. Cara aman mempublikasikan

Yang layak di-publish hanyalah **kodenya**:

```bash
# pastikan bersih
git status --ignored --short | grep -E "hasil|fixtures|logs" || echo "bersih"

# publikasikan: scraper/ tests/*.py *.md *.bat *.ini.example requirements.txt
```

Sertakan contoh data **palsu** (sudah ada: `tests/fake_sinta_server.py` memakai
dosen fiktif), bukan hasil scraping asli. Kalau butuh contoh keluaran, buat 1–2
baris karangan sendiri.

## 5. Perbaikan yang sudah dilakukan

* `.gitignore` menyaring `hasil/`, `logs/`, `*.csv`, `*.xlsx`, `*.json`,
  `tests/fixtures/*.html`, `.cache_sinta/`, `debug/`, `autorun_config.ini`.
* Data hasil scraping dipisahkan ke `hasil/` supaya mudah dibuang.
* Test berjalan tanpa menyentuh server SINTA (mock lokal), jadi repo tidak
  butuh HTML atau data asli untuk dibuktikan bekerja.
