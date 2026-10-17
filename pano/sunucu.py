"""Pano sunucusu: yerel HTTP, standart kütüphane.

    python -m pano.sunucu                 # http://localhost:3003 (PANO_URL'deki port)
    python -m pano.sunucu --host 0.0.0.0  # aynı Wi-Fi'deki telefondan açmak için

Uçlar:
  GET  /                      pano sayfası
  GET  /api/rapor?oturum=&gizli=1   rapor verisi (gizli öntanımlı açık)
  GET  /api/oturumlar         oturumlar, en yenisi başta
  POST /api/isaret            {"adres_etiket", "ag", "sahip": "benim"|"benim_degil"} → yalnız isaret tablosu
Sunucu hiçbir anahtar okumaz ve istemciye anahtar göndermez.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
import sys
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from pano import veri

KOK_DIZIN = Path(__file__).resolve().parents[1]
STATIK = Path(__file__).resolve().parent / "static"
AZAMI_GOVDE = 4096


def oturumlar(db: sqlite3.Connection) -> list[str]:
    satirlar = db.execute("SELECT oturum, max(rowid) FROM olgu GROUP BY oturum").fetchall()

    def anahtar(r):
        m = re.search(r"(\d{4}-\d{2}-\d{2})$", r[0])
        return (m.group(1) if m else "", r[1])
    return [r[0] for r in sorted(satirlar, key=anahtar, reverse=True)]


def isleyici(db_yolu: Path):
    class Isleyici(BaseHTTPRequestHandler):
        server_version = "proof1-pano"

        def log_message(self, bicim, *arg):  # adres/parametre içeren istek satırlarını basma
            pass

        def _gonder(self, durum: int, govde: bytes, tur: str):
            self.send_response(durum)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(govde)

        def _json(self, durum: int, nesne):
            self._gonder(durum, json.dumps(nesne, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _statik(self, goreli: str):
            hedef = (STATIK / goreli).resolve()
            if STATIK.resolve() not in hedef.parents and hedef != STATIK.resolve() or not hedef.is_file():
                return self._json(404, {"hata": "bulunamadı"})
            tur = mimetypes.guess_type(hedef.name)[0] or "application/octet-stream"
            if tur.startswith("text/") or tur in ("application/javascript",):
                tur += "; charset=utf-8"
            self._gonder(200, hedef.read_bytes(), tur)

        def do_GET(self):
            istek = urlparse(self.path)
            yol = unquote(istek.path)
            sorgu = parse_qs(istek.query)
            if yol in ("/", "/index.html"):
                return self._statik("index.html")
            if yol.startswith("/static/"):
                return self._statik(yol[len("/static/"):])
            with closing(sqlite3.connect(db_yolu)) as db:
                if yol == "/api/oturumlar":
                    return self._json(200, oturumlar(db))
                if yol == "/api/rapor":
                    oturum = (sorgu.get("oturum") or [None])[0]
                    if not oturum:
                        liste = oturumlar(db)
                        if not liste:
                            return self._json(404, {"hata": "Veri kaynağı hazırlanmadı."})
                        oturum = liste[0]
                    gizli = (sorgu.get("gizli") or ["1"])[0] != "0"
                    return self._json(200, veri.rapor(db, oturum, gizli=gizli))
            return self._json(404, {"hata": "bulunamadı"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/isaret":
                return self._json(404, {"hata": "bulunamadı"})
            uzunluk = int(self.headers.get("Content-Length") or 0)
            if uzunluk <= 0 or uzunluk > AZAMI_GOVDE:
                return self._json(400, {"hata": "geçersiz istek"})
            try:
                govde = json.loads(self.rfile.read(uzunluk))
                with closing(sqlite3.connect(db_yolu)) as db:
                    veri.isaret_yaz(db, str(govde["adres_etiket"]), str(govde["ag"]), str(govde["sahip"]))
            except (ValueError, KeyError, TypeError) as e:
                return self._json(400, {"hata": str(e) if isinstance(e, veri.IsaretHatasi) else "geçersiz istek"})
            return self._json(200, {"durum": "kaydedildi"})

    return Isleyici


def kur(db_yolu, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), isleyici(Path(db_yolu)))


def _env_yukle() -> None:
    yol = KOK_DIZIN / ".env"
    if not yol.exists():
        return
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        ad, deger = satir.split("=", 1)
        deger = deger.split(" #")[0].strip()
        if deger and ad.strip() not in os.environ:
            os.environ[ad.strip()] = deger


def ana(argv=None) -> int:
    _env_yukle()
    varsayilan_port = urlparse(os.environ.get("PANO_URL", "http://localhost:3003")).port or 3003
    ayr = argparse.ArgumentParser(description="proof1 pano")
    ayr.add_argument("--host", default="127.0.0.1")
    ayr.add_argument("--port", type=int, default=varsayilan_port)
    arg = ayr.parse_args(argv)
    db = KOK_DIZIN / os.environ.get("PROOF1_DB", "data/proof1.db")
    if not db.exists():
        print(f"Veri dosyası yok: {db}. PROOF1_DB ile gösterin (örnek: ortak/ornek/proof1_ornek.db).",
              file=sys.stderr)
        return 2
    httpd = kur(db, arg.host, arg.port)
    print(f"proof1 pano: http://{'localhost' if arg.host == '127.0.0.1' else arg.host}:{arg.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(ana())
