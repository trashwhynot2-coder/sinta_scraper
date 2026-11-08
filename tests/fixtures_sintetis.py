"""
Fixture HTML SINTETIS (karangan sendiri, bukan hasil scraping).

Dipakai oleh tests/test_offline.py dan tests/demo_offline.py supaya repo ini
TIDAK perlu menyimpan HTML milik SINTA maupun data dosen asli.

Markup-nya sengaja meniru struktur SINTA (div.list-item, div.ar-list-item,
ul.subject-list, dst.) dan sudah disesuaikan dengan selektor di parser, sehingga
tes tetap menguji parsing yang sebenarnya.
"""

# ---------------------------------------------------------------------------
# Profil dosen (semua fiktif)
# ---------------------------------------------------------------------------
PROFIL_DOSEN = """<!doctype html>
<html lang="id"><head><title>Profil Dosen</title></head><body>
<div class="content"><div class="content-box">

  <h3><a href="#!">DOSEN CONTOH</a> <small><i class="el el-ok-sign text-success ml-2"></i></small></h3>

  <div class="meta-profile">
    <a href="/affiliations/profile/999"><i class="el el-map-marker mr-1"></i> Universitas Contoh Nusantara</a>
    <span class="mr-3 d-none d-sm-block"></span>
    <a href="/departments/profile/999/031015/11901"><i class="el el-child mr-1"></i> S1 - Farmasi</a>
    <span class="mr-3 d-none d-sm-block"></span>
    <a href="#!"><i class="el el-user mr-1"></i> SINTA ID : 9000001</a>
  </div>

  <div class="profile-subject mt-3">
    <ul class="subject-list">
      <li><a href="/subjects/detail/6518">Farmasi bahan alam</a></li>
      <li><a href="/subjects/detail/24108">Kimia Farmasi</a></li>
    </ul>
  </div>

  <div class="stat-profile">
    <div class="pr-num">1.500</div><div class="pr-txt">SINTA Score Overall</div>
    <div class="pr-num">700</div><div class="pr-txt">SINTA Score 3Yr</div>
  </div>

  <div class="ar-list-item mb-5">
    <div class="ar-title">
      <a href="https://example.org/p1">Antioxidant activity and total phenolic content of simulated leaf extract</a>
    </div>
    <div class="ar-meta">
      <a class="ar-quartile" href="#!" style="margin-left: 0px;"><i class="zmdi zmdi-chart-donut"></i> Q3 Journal</a>
      <a href="https://example.org/j1" class="ar-pub"><i class="el el-book"></i>Jurnal Farmasi Contoh</a>
      <br>
      <a href="#!">Author Order : 1 of 3</a> &nbsp;&nbsp;&nbsp;
      <a href="#!">Creator : Dosen C.</a>
    </div>
    <div class="ar-meta">
      <a class="ar-year" href="#!"><i class="zmdi zmdi-calendar"></i> 2024</a>
      <a class="ar-cited" href="#!"><i class="zmdi zmdi-comment-list"></i> 3 cited</a>
    </div>
  </div>

  <div class="ar-list-item mb-5">
    <div class="ar-title">
      <a href="https://example.org/p2">Flavonoid profiling of simulated fruit peel extract by HPLC</a>
    </div>
    <div class="ar-meta">
      <a class="ar-quartile" href="#!" style="margin-left: 0px;"><i class="zmdi zmdi-chart-donut"></i> Q4 Journal</a>
      <a href="https://example.org/j2" class="ar-pub"><i class="el el-book"></i>Jurnal Fitokimia Contoh</a>
      <br>
      <a href="#!">Author Order : 2 of 4</a>
    </div>
    <div class="ar-meta">
      <a class="ar-year" href="#!"><i class="zmdi zmdi-calendar"></i> 2023</a>
      <a class="ar-cited" href="#!"><i class="zmdi zmdi-comment-list"></i> 1 cited</a>
    </div>
  </div>

</div></div></body></html>
"""

# Profil dosen kedua (untuk demo multi-baris)
PROFIL_DOSEN_2 = """<!doctype html>
<html><head><title>Profil Dosen 2</title></head><body>
<div class="content"><div class="content-box">
  <h3><a href="#!">DOSEN CONTOH DUA</a></h3>
  <div class="meta-profile">
    <a href="/affiliations/profile/998"><i class="el el-map-marker mr-1"></i> Politeknik Contoh Sejahtera</a>
    <a href="/departments/profile/998/x/y"><i class="el el-child mr-1"></i> D3 - Farmasi</a>
    <a href="#!"><i class="el el-user mr-1"></i> SINTA ID : 9000002</a>
  </div>
  <div class="profile-subject mt-3"><ul class="subject-list">
    <li><a href="/subjects/detail/6518">Farmasi bahan alam</a></li>
  </ul></div>
  <div class="stat-profile">
    <div class="pr-num">900</div><div class="pr-txt">SINTA Score Overall</div>
    <div class="pr-num">120</div><div class="pr-txt">SINTA Score 3Yr</div>
  </div>
  <div class="ar-list-item mb-5">
    <div class="ar-title"><a href="https://example.org/p1">Ekstraksi dan uji antioksidan ekstrak contoh</a></div>
    <div class="ar-meta">
      <a class="ar-quartile" href="#!"><i class="zmdi"></i> no-Q Journal</a>
      <a class="ar-pub" href="#!"><i class="el el-book"></i>Jurnal Contoh</a>
      <a href="#!">Author Order : 1 of 2</a>
    </div>
    <div class="ar-meta">
      <a class="ar-year" href="#!"><i class="zmdi"></i> 2022</a>
      <a class="ar-cited" href="#!"><i class="zmdi"></i> 0 cited</a>
    </div>
  </div>
</div></div></body></html>
"""

# ---------------------------------------------------------------------------
# Halaman daftar (subjek / institusi / pencarian)
# ---------------------------------------------------------------------------
def _card(sinta_id, nama, institusi, institusi_id, prodi, subjects, skor_3yr, lokasi=""):
    subj = "".join(f'<li><a href="/subjects/detail/1">{s}</a></li>' for s in subjects)
    loc = (f'<div class="affil-loc"><i class="el el-map-marker mr-1"></i>{lokasi}</div>'
           if lokasi else "")
    return f"""
    <div class="list-item row mb-4">
      <div class="col-lg profile-side">
        <div class="row pr-top">
          <div class="col-3"><img src="/public/assets/img/author-small.png" alt="avatar" class="img-thumbnail avatar"></div>
          <div class="col col-sm-8">
            <div class="profile-name"><a href="/authors/profile/{sinta_id}">{nama}</a>
              <i class="el el-ok-sign text-success ml-2"></i></div>
            <div class="profile-affil"><a href="/affiliations/profile/{institusi_id}">
              <i class="el el-map-marker mr-1"></i> {institusi} </a></div>
            <div class="profile-dept"><a href="/departments/profile/{institusi_id}/x/y">
              <i class="el el-child mr-1"></i> {prodi} </a></div>
            <div class="profile-id"><i class="el el-user mr-1"></i> ID : {sinta_id}</div>
            <div class="profile-hindex">
              <span class="profile-id text-warning"><i class="zmdi zmdi-chart-donut mr-1"></i> Scopus H-Index : 5</span>
              <span class="profile-id text-success ml-3"><i class="zmdi zmdi-chart-donut mr-1"></i> GS H-Index : 9</span>
            </div>
          </div>
        </div>
        <div class="pr-bottom row">
          <div class="col-6"><div class="pr-num">{skor_3yr}</div><div class="pr-txt">SINTA Score 3Yr</div></div>
          <div class="col-6"><div class="pr-num">2.000</div><div class="pr-txt">SINTA Score Overall</div></div>
        </div>
        {loc}
      </div>
      <div class="col-lg meta-side">
        <div class="row"><div class="col-md">Subjects<ul class="subject-list">{subj}</ul></div></div>
      </div>
    </div>"""


def daftar_dosen(total_pages=3, page=1, dengan_lokasi=False):
    """Halaman hasil pencarian subjek (10 kartu per halaman)."""
    kartu = "".join(
        _card(
            9000000 + page * 100 + i,
            f"DOSEN CONTOH {page}-{i}",
            "Universitas Contoh Nusantara",
            999,
            "S1 - Farmasi",
            ["Farmasi bahan alam", "Kimia Farmasi"],
            "300",
            "KOTA ADM. JAKARTA PUSAT - DKI JAKARTA, ID" if dengan_lokasi else "",
        )
        for i in range(1, 11)
    )
    return f"""<!doctype html><html><body>
    <div class="content"><div class="content-box">
      <div class="content-list mt-5 pt-4">
        <nav class="mb-4 mt-2"><ul class="pagination justify-content-center">
          <li class="page-item active"><a class="page-link" href="?page={page}">{page}</a></li>
        </ul>
        <div class="text-center pagination-text">
          <small>Page {page} of {total_pages} | Total Records {total_pages * 10}</small>
        </div></nav>
        {kartu}
      </div>
    </div></div></body></html>"""


def profil_institusi(nama="Universitas Contoh Nusantara", lokasi="KOTA ADM. JAKARTA PUSAT - DKI JAKARTA, ID"):
    return f"""<!doctype html><html><body>
    <div class="content"><div class="content-box">
      <div class="univ-name">
        <h3><a href="#!">{nama}</a></h3>
        <div class="meta-profile">
          <span class="affil-abbrev mr-3"><i class="zmdi zmdi-label mr-1"></i> -</span>
          <a href="#!" class="affil-loc"><i class="el el-map-marker mr-1"></i> {lokasi}</a>
          <a href="#!" class="affil-code"><i class="el el-certificate mr-1"></i> ID : 999
            <i class="zmdi zmdi-code ml-2"></i> CODE : 001999</a>
        </div>
      </div>
    </div></div></body></html>"""


def daftar_institusi():
    """Halaman /affiliations: campuran dalam & luar JABODETABEK."""
    data = [
        ("999", "Universitas Contoh Nusantara", "KOTA ADM. JAKARTA PUSAT - DKI JAKARTA, ID"),
        ("998", "Politeknik Contoh Sejahtera", "KOTA ADM. JAKARTA BARAT - DKI JAKARTA, ID"),
        ("997", "Institut Contoh Bogor", "KAB. BOGOR - JAWA BARAT, ID"),
        ("996", "Universitas Contoh Tangerang", "KOTA TANGERANG SELATAN - BANTEN, ID"),
        ("995", "Universitas Contoh Bandung", "KOTA BANDUNG - JAWA BARAT, ID"),
        ("994", "Universitas Contoh Yogyakarta", "KAB. SLEMAN - DAERAH ISTIMEWA YOGYAKARTA, ID"),
        ("993", "Institut Contoh Surabaya", "KOTA SURABAYA - JAWA TIMUR, ID"),
    ]
    kartu = "".join(f"""
      <div class="list-item row mb-4">
        <div class="col-lg-3 profile-side journal-profile"><div class="pr-top text-center">
          <img src="/public/assets/img/author-small.png" alt="avatar" class="img-thumbnail avatar-affil">
        </div></div>
        <div class="col col-lg meta-side"><div class="row"><div class="col-md">
          <div class="affil-name"><a href="/affiliations/profile/{aid}">{nama}
            <i class="el el-ok-sign text-success ml-2"></i></a></div>
          <div class="affil-abbrev"><i class="zmdi zmdi-label mr-1"></i> -</div>
          <div class="affil-loc mt-2"><a href="#!"><i class="el el-map-marker mr-1"></i>{lok}</a></div>
          <div class="profile-id"><i class="el el-certificate mr-1"></i> ID : {aid} | CODE : 001</div>
          <div class="stat-prev mt-2"><span class="num-stat"><i class="el el-group-alt"></i> 100
            <span class="text-stat ml-1">Authors</span></span></div>
        </div></div></div>
      </div>""" for aid, nama, lok in data)
    return f"""<!doctype html><html><body>
    <div class="content"><div class="content-box"><div class="content-list mt-5 pt-4">
      <nav class="mb-4 mt-2"><div class="text-center pagination-text">
        <small>Page 1 of 1 | Total Records {len(data)}</small>
      </div></nav>
      {kartu}
    </div></div></div></body></html>"""


def daftar_dosen_institusi(n=10):
    kartu = "".join(
        _card(9000000 + i, f"DOSEN KAMPUS {i}", "Universitas Contoh Nusantara", 999,
              "S1 - Farmasi", ["Farmasi bahan alam"], "250")
        for i in range(1, n + 1)
    )
    return f"""<!doctype html><html><body>
    <div class="content"><div class="content-box"><div class="content-list mt-5 pt-4">
      <nav class="mb-4 mt-2"><div class="text-center pagination-text">
        <small>Page 1 of 49 | Total Records 487</small></div></nav>
      {kartu}
    </div></div></div></body></html>"""


def publikasi_google_scholar(n=10):
    item = "".join(f"""
    <div class="ar-list-item mb-5">
      <div class="ar-title"><a href="https://example.org/gs{i}">Publikasi contoh nomor {i}</a></div>
      <div class="ar-meta">
        <a href="#!">Authors : Dosen C, Rekan D</a>
        <a href="#!">Jurnal Contoh {i} (1), 1-10, 2024</a>
      </div>
      <div class="ar-meta">
        <a class="ar-year" href="#!"><i class="zmdi"></i> 2024</a>
        <a class="ar-cited" href="#!"><i class="zmdi"></i> {i} cited</a>
      </div>
    </div>""" for i in range(1, n + 1))
    return f"""<!doctype html><html><body>
    <div class="content"><div class="content-box">{item}</div></div></body></html>"""
