"""
Server SINTA tiruan (lokal) untuk menguji autorun tanpa menyentuh server asli.

Meniru bentuk URL + markup minimal yang dipakai scraper:
    /authors/profile/<id>
    /subjects/detail/<id>?page=N&sort=1
    /affiliations/profile/<id>   (lokasi JABODETABEK dan non-JABODETABEK)
    /affiliations/authors/<id>?page=N
    /authors?q=...&page=N

Jalankan:
    python tests/fake_sinta_server.py 8765
lalu:
    SINTA_BASE_URL=http://127.0.0.1:8765 python autorun.py --no-open
"""
from __future__ import annotations

import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# id dosen -> (nama, institusi, affil_id, kode_negara)
AUTHORS = {
    "100001": ("RINA FITRIANI", "Universitas Indonesia", "430", "id"),
    "100002": ("BUDI SANTOSO", "Universitas Padjadjaran", "429", "id"),
    "100003": ("SITI AMINAH", "Universitas Tarumanagara", "476", "id"),
    "100004": ("AGUS PRASETYO", "Institut Teknologi Bandung", "421", "id"),
}

AFFILS = {
    "430": ("Universitas Indonesia", "KOTA ADM. JAKARTA PUSAT - DKI JAKARTA, ID"),
    "476": ("Universitas Tarumanagara", "KOTA ADM. JAKARTA BARAT - DKI JAKARTA, ID"),
    "429": ("Universitas Padjadjaran", "KAB. SUMEDANG - JAWA BARAT, ID"),
    "421": ("Institut Teknologi Bandung", "KOTA BANDUNG - JAWA BARAT, ID"),
}

# dosen -> daftar judul publikasi (mengandung kata kunci farmasi bahan alam)
PUBS = {
    "100001": [
        ("Antioxidant activity of Moringa oleifera leaf extract and total phenolic content", "2023", "Journal of Young Pharmacists"),
        ("Flavonoid profiling of Syzygium polyanthum extract by HPLC", "2022", "Indonesian Journal of Pharmacy"),
        ("Screening fitokimia ekstrak etanol daun salam", "2021", "Jurnal Farmasi Indonesia"),
    ],
    "100003": [
        ("Ekstraksi maserasi dan uji DPPH ekstrak kulit buah manggis", "2020", "Jurnal Fitokimia"),
    ],
    "100002": [("Teknik mesin dan efisiensi bahan bakar", "2019", "Jurnal Teknik")],
    "100004": [("Sistem kontrol cerdas untuk industri", "2021", "Jurnal Teknik")],
}

SUBJECTS = {"6518": list(AUTHORS)}          # subjek = semua dosen


def card(author_id: str, with_location=None) -> str:
    name, affil, affil_id, _ = AUTHORS[author_id]
    dept = "S1 - Farmasi"
    loc = f'<div class="affil-loc"><i class="el el-map-marker mr-1"></i>{with_location}</div>' if with_location else ""
    return f"""
    <div class="list-item row mb-4">
      <div class="col-lg profile-side">
        <div class="profile-name"><a href="/authors/profile/{author_id}">{name}</a></div>
        <div class="profile-affil"><a href="/affiliations/profile/{affil_id}">
          <i class="el el-map-marker mr-1"></i> {affil} </a></div>
        <div class="profile-dept"><a href="/departments/profile/{affil_id}/x/y">
          <i class="el el-child mr-1"></i> {dept} </a></div>
        <div class="profile-id"><i class="el el-user mr-1"></i>SINTA ID : {author_id}</div>
        <div class="pr-num">555</div><div class="pr-txt">SINTA Score 3Yr</div>
        <div class="pr-num">3.062</div><div class="pr-txt">SINTA Score Overall</div>
        {loc}
      </div>
      <div class="col-lg meta-side">
        <ul class="subject-list">
          <li><a href="/subjects/detail/6518">Farmasi bahan alam</a></li>
          <li><a href="/subjects/detail/24108">Kimia Farmasi</a></li>
        </ul>
        <div class="profile-hindex">
          <span class="profile-id text-warning"><i class="zmdi zmdi-chart-donut mr-1"></i> Scopus H-Index : 7</span>
          <span class="profile-id text-success ml-3"><i class="zmdi zmdi-chart-donut mr-1"></i> GS H-Index : 11</span>
        </div>
      </div>
    </div>"""


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html><head><title>{title}</title></head><body>
    <div class="content"><div class="content-box">{body}</div></div>
    </body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # senyap
        pass

    def _send(self, body: bytes, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path

        if path == "/favicon.ico":
            return self._send(b"", 404)

        # profil dosen -----------------------------------------------------
        m = re.match(r"^/authors/profile/(\d+)$", path)
        if m:
            aid = m.group(1)
            if aid not in AUTHORS:
                return self._send(page("404", "<p>not found</p>"), 200)
            name, affil, affil_id, _ = AUTHORS[aid]
            loc = AFFILS[affil_id][1]
            pubs = "".join(
                f"""<div class="ar-list-item mb-5">
                      <div class="ar-title"><a href="https://example.org/{i}">{t}</a></div>
                      <div class="ar-meta">
                        <a class="ar-quartile"><i class="zmdi"></i> Q3 Journal</a>
                        <a class="ar-pub"><i class="el el-book"></i>{v}</a>
                        <a>Author Order : 1 of 3</a>
                      </div>
                      <div class="ar-meta">
                        <a class="ar-year"><i class="zmdi"></i> {y}</a>
                        <a class="ar-cited"><i class="zmdi"></i> 4 cited</a>
                      </div>
                    </div>"""
                for i, (t, y, v) in enumerate(PUBS.get(aid, []))
            )
            body = f"""
              <h3><a href="#!">{name}</a></h3>
              <div class="meta-profile">
                <a href="/affiliations/profile/{affil_id}"><i class="el el-map-marker mr-1"></i> {affil}</a>
                <a href="/departments/profile/{affil_id}/x/y"><i class="el el-child mr-1"></i> S1 - Farmasi</a>
                <a href="#!"><i class="el el-user mr-1"></i> SINTA ID : {aid}</a>
              </div>
              <div class="profile-subject mt-3"><ul class="subject-list">
                <li><a href="/subjects/detail/6518">Farmasi bahan alam</a></li>
                <li><a href="/subjects/detail/24108">Kimia Farmasi</a></li>
              </ul></div>
              <div class="stat-profile">
                <div class="pr-num">3.062</div><div class="pr-txt">SINTA Score Overall</div>
                <div class="pr-num">555</div><div class="pr-txt">SINTA Score 3Yr</div>
              </div>
              {pubs}"""
            return self._send(page(f"Profil {name}", body))

        # subjek -----------------------------------------------------------
        m = re.match(r"^/subjects/detail/(\d+)$", path)
        if m:
            sid = m.group(1)
            ids = SUBJECTS.get(sid, list(AUTHORS))  # subjek apa pun -> semua dosen
            per_page, page_no = 2, int(q.get("page", ["1"])[0])
            chunk = ids[(page_no - 1) * per_page: page_no * per_page]
            cards = "".join(card(a) for a in chunk)
            total_pages = max(1, -(-len(ids) // per_page))
            nav = (f'<div class="pagination-text"><small>Page {page_no} of '
                   f'{total_pages} | Total Records {len(ids)}</small></div>')
            return self._send(page("Subjects", nav + cards))

        # profil institusi --------------------------------------------------
        m = re.match(r"^/affiliations/profile/(\d+)$", path)
        if m:
            aid = m.group(1)
            if aid not in AFFILS:
                return self._send(page("404", "<p>not found</p>"), 200)
            name, loc = AFFILS[aid]
            body = f"""
              <div class="univ-name"><h3><a href="#!">{name}</a></h3>
                <div class="meta-profile">
                  <span class="affil-abbrev mr-3"><i class="zmdi"></i> -</span>
                  <a href="#!" class="affil-loc"><i class="el el-map-marker mr-1"></i> {loc}</a>
                  <a href="#!" class="affil-code"><i class="el el-certificate mr-1"></i> ID : {aid}</a>
                </div>
              </div>"""
            return self._send(page(name, body))

        # daftar dosen institusi --------------------------------------------
        m = re.match(r"^/affiliations/authors/(\d+)$", path)
        if m:
            aid = m.group(1)
            ids = [k for k, v in AUTHORS.items() if v[2] == aid]
            cards = "".join(card(a) for a in ids)
            return self._send(page("Authors", cards))

        # daftar institusi (mode kampus) -------------------------------------
        if path == "/affiliations":
            page_no = int(q.get("page", ["1"])[0])
            ids = list(AFFILS)
            cards = ""
            for aid in ids:
                name, loc = AFFILS[aid]
                cards += f"""
                <div class="list-item row mb-4">
                  <div class="affil-name"><a href="/affiliations/profile/{aid}">{name}</a></div>
                  <div class="affil-loc"><i class="el el-map-marker mr-1"></i>{loc}</div>
                  <div class="profile-id"><i class="el el-certificate mr-1"></i> ID : {aid} | CODE : 001</div>
                </div>"""
            nav = (f'<div class="pagination-text"><small>Page {page_no} of 1 | '
                   f'Total Records {len(ids)}</small></div>')
            return self._send(page("Affiliations", nav + cards))

        # pencarian ---------------------------------------------------------
        if path == "/authors":
            term = (q.get("q", [""])[0] or "").lower()
            ids = [k for k, v in AUTHORS.items() if term in v[0].lower()]
            cards = "".join(card(a) for a in ids)
            return self._send(page("Search", cards))

        return self._send(page("404", "<p>tidak ada</p>"), 200)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Fake SINTA server: http://127.0.0.1:{port}  (Ctrl+C untuk stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
