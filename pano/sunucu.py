"""Pano sunucusu: yerel HTTP, standart kütüphane.

    python -m pano.sunucu                 # http://localhost:3003 (PANO_URL'deki port)
    python -m pano.sunucu --host 0.0.0.0  # aynı Wi-Fi'deki telefondan açmak için

Uçlar:
  GET  /                      pano sayfası
  GET  /api/rapor?oturum=&gizli=1   rapor verisi (gizli öntanımlı açık)
  GET  /api/ayrinti?oturum=&gizli=1 ayrıntılı mod
  GET  /api/oturumlar         oturumlar, en yenisi başta
  GET  /api/muhur-dogrula?gun=      mühür kökünü zincirdekiyle karşılaştırır
  POST /api/isaret            {"adres_etiket", "ag", "sahip": "benim"|"benim_degil"} → yalnız isaret tablosu
Kendi hesabını bağlama (misafir, pano/hesap.py):
  POST /api/hesap/bagla       {"api_key", "secret_key", "passphrase"} — yalnız bu bilgisayardan; 202 {"hesap", "durum"}
  GET  /api/hesap/durum?hesap=      taramanın adımı (adim, sira, toplam, bitti, hata)
  GET  /api/hesaplar          [{"hesap": "ana", "ad": "Ana hesap"}, bitmiş misafir hesapları…]
Yukarıdaki veri uçları ?hesap=<kimlik> alır (yoksa ya da "ana" ise sahibin dosyası; bilinmeyen kimlik 404).
Sunucu sahibin anahtarını okumaz; misafirin anahtarı yalnız bellekte durur. İstemciye hiçbir anahtar gönderilmez.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import sys
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from pano import veri
from pano.hesap import Hesaplar

KOK_DIZIN = Path(__file__).resolve().parents[1]
STATIK = Path(__file__).resolve().parent / "static"
AZAMI_GOVDE = 4096
MISAFIR_MUHUR = {"agent_id": "", "sozlesme": "", "kimlik": ""}      # misafir dosyası mühürlenmez: mühür iddiası yok
YEREL_ISTEMCI = ("127.0.0.1", "::1")
YEREL_KOKEN = ("localhost", "127.0.0.1", "::1")
HESAP_YOK = {"hata": "hesap bulunamadı"}


def _yerel_koken(koken: str | None) -> bool:
    """Tarayıcı Origin gönderdiyse yalnız bu bilgisayardaki pano sayfası (başka sitenin sayfası anahtar gönderemez)."""
    if koken is None:
        return True
    try:
        return urlparse(koken).hostname in YEREL_KOKEN
    except ValueError:
        return False


def muhur_ayari() -> dict:
    """Kamuya açık Fuji değerleri (gizli değil): agentId, mühür sözleşmesi, resmi ERC-8004 Identity."""
    return {"agent_id": os.environ.get("PROOF1_AGENT_ID", ""), "sozlesme": os.environ.get("PROOF1_SEAL_ADDRESS", ""),
            "kimlik": "0x8004A818BFB912233c491871b3d84c89A494BD9e"}


def oturumlar(db: sqlite3.Connection) -> list[str]:
    satirlar = db.execute("SELECT oturum, max(rowid) FROM olgu GROUP BY oturum").fetchall()

    def anahtar(r):
        m = re.search(r"(\d{4}-\d{2}-\d{2})$", r[0])
        return (m.group(1) if m else "", r[1])
    return [r[0] for r in sorted(satirlar, key=anahtar, reverse=True)]


def isleyici(db_yolu: Path, hesaplar: Hesaplar | None = None):
    hesaplar = hesaplar if hesaplar is not None else Hesaplar()

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
            try:
                return self._api(yol, sorgu)
            except sqlite3.Error as e:  # tablolar henüz yok (sabah işi çalışmadı) ya da dosya kilitli
                print(f"veri okunamadı: {type(e).__name__}", file=sys.stderr)
                return self._json(503, {"hata": "Veri kaynağı hazırlanmadı."})

        def _hedef(self, sorgu: dict) -> tuple[Path | None, bool]:
            """(veri dosyası, misafir mi). hesap yoksa, boşsa ya da 'ana' ise sahibin dosyası; misafirde bitmiş
            taramanın dosyası, yoksa None (404)."""
            hesap = (sorgu.get("hesap") or [""])[0]
            if hesap in ("", "ana"):
                return db_yolu, False
            return hesaplar.yol(hesap), True

        def _api(self, yol: str, sorgu: dict):
            if yol == "/api/hesaplar":
                return self._json(200, hesaplar.liste())
            if yol == "/api/hesap/durum":
                d = hesaplar.durum((sorgu.get("hesap") or [""])[0])
                return self._json(200, d) if d else self._json(404, HESAP_YOK)
            hedef, misafir = self._hedef(sorgu)
            if hedef is None:
                return self._json(404, HESAP_YOK)
            with closing(sqlite3.connect(hedef)) as db:
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
                if yol == "/api/ayrinti":
                    oturum = (sorgu.get("oturum") or [None])[0] or (oturumlar(db) or [None])[0]
                    if not oturum:
                        return self._json(404, {"hata": "Veri kaynağı hazırlanmadı."})
                    gizli = (sorgu.get("gizli") or ["1"])[0] != "0"
                    return self._json(200, veri.ayrinti(
                        db, oturum, gizli=gizli, muhur_ayar=MISAFIR_MUHUR if misafir else muhur_ayari(),
                        kullanici="misafir" if misafir else os.environ.get("PROOF1_KULLANICI", "bugra")))
                if yol == "/api/muhur-dogrula":
                    gun = (sorgu.get("gun") or [""])[0]
                    ayar = MISAFIR_MUHUR if misafir else muhur_ayari()
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", gun):
                        return self._json(400, {"hata": "gün YYYY-AA-GG olmalı"})
                    if not (ayar["agent_id"] and ayar["sozlesme"]):
                        return self._json(200, {"durum": "ayar_yok"})
                    from muhur.muhurle import http_rpc
                    rpc = http_rpc(os.environ.get("FUJI_RPC_URL", "https://avalanche-fuji-c-chain-rpc.publicnode.com"))
                    return self._json(200, veri.muhur_dogrula(db, gun, ayar, rpc))
            return self._json(404, {"hata": "bulunamadı"})

        def _govde(self) -> bytes | None:
            """İstek gövdesi (en çok AZAMI_GOVDE bayt); uzunluk geçersizse ya da sınırı aşarsa None."""
            try:
                uzunluk = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if uzunluk <= 0 or uzunluk > AZAMI_GOVDE:
                return None
            return self.rfile.read(uzunluk)

        def do_POST(self):
            istek = urlparse(self.path)
            ham = self._govde()    # cevaptan önce okunur: okunmamış gövdeyle kapanan bağlantıyı Windows koparıyor
            if istek.path == "/api/hesap/bagla":
                return self._bagla(ham)
            if istek.path != "/api/isaret":
                return self._json(404, {"hata": "bulunamadı"})
            hedef, _ = self._hedef(parse_qs(istek.query))
            if hedef is None:
                return self._json(404, HESAP_YOK)
            if ham is None:
                return self._json(400, {"hata": "geçersiz istek"})
            try:
                govde = json.loads(ham)
                with closing(sqlite3.connect(hedef)) as db:
                    veri.isaret_yaz(db, str(govde["adres_etiket"]), str(govde["ag"]), str(govde["sahip"]))
            except (ValueError, KeyError, TypeError) as e:
                return self._json(400, {"hata": str(e) if isinstance(e, veri.IsaretHatasi) else "geçersiz istek"})
            return self._json(200, {"durum": "kaydedildi"})

        def _bagla(self, ham: bytes | None):
            """Kendi hesabını bağla. Anahtar cevaba, iletiye ya da günlüğe girmez; yalnız taramaya bellekte geçer."""
            if self.client_address[0] not in YEREL_ISTEMCI or not _yerel_koken(self.headers.get("Origin")):
                return self._json(403, {"hata": "Yalnız bu bilgisayardan bağlanılabilir."})
            if ham is None:
                return self._json(400, {"hata": "geçersiz istek"})
            try:
                govde = json.loads(ham)
            except (ValueError, RecursionError):
                return self._json(400, {"hata": "geçersiz istek"})
            alanlar = [govde.get(ad) if isinstance(govde, dict) else None for ad in ("api_key", "secret_key", "passphrase")]
            alanlar = [a.strip() if isinstance(a, str) else "" for a in alanlar]
            if not all(alanlar):
                return self._json(400, {"hata": "Üç alan da gerekli."})
            hesap = hesaplar.bagla(*alanlar)
            if hesap is None:
                return self._json(409, {"hata": "Bir tarama zaten sürüyor."})
            return self._json(202, {"hesap": hesap, "durum": "basladi"})

    return Isleyici


def kur(db_yolu, host: str, port: int, hesaplar: Hesaplar | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), isleyici(Path(db_yolu), hesaplar))


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


def veri_dosyasi(kok: Path, ortam) -> tuple[Path, str | None]:
    """Sunulacak veri dosyası ve ekrana yazılacak not. PROOF1_DB verildiyse o, yoksa data/proof1.db. O da yoksa (depoyu
    yeni indiren biri) örnek veritabanının data/ altındaki kopyası: pano açılır, kişi kendi hesabını panodan bağlar.
    Depodaki örnek dosyanın kendisine yazılmaz ("bu adres senin mi?" yanıtı kopyaya gider)."""
    if ortam.get("PROOF1_DB"):
        return kok / ortam["PROOF1_DB"], None
    canli = kok / "data" / "proof1.db"
    if canli.exists():
        return canli, None
    kopya = kok / "data" / "ornek.db"
    if not kopya.exists():
        kopya.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(kok / "ortak" / "ornek" / "proof1_ornek.db", kopya)
    return kopya, "Canlı veri yok: pano örnek veriyle açılıyor. Kendi hesabını panodaki menüden bağlayabilirsin."


def ana(argv=None) -> int:
    from veri.ayar import konsol_utf8
    konsol_utf8()                      # Windows: '→' gibi karakterlerde çökmesin
    _env_yukle()
    varsayilan_port = urlparse(os.environ.get("PANO_URL", "http://localhost:3003")).port or 3003
    ayr = argparse.ArgumentParser(description="proof1 pano")
    ayr.add_argument("--host", default="127.0.0.1")
    ayr.add_argument("--port", type=int, default=varsayilan_port)
    arg = ayr.parse_args(argv)
    db, not_ = veri_dosyasi(KOK_DIZIN, os.environ)
    if not db.exists():
        print(f"Veri dosyası yok: {db}. PROOF1_DB ile gösterin (örnek: ortak/ornek/proof1_ornek.db).",
              file=sys.stderr)
        return 2
    if not_:
        print(not_)
    httpd = kur(db, arg.host, arg.port)
    print(f"proof1 pano: http://{'localhost' if arg.host == '127.0.0.1' else arg.host}:{arg.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(ana())
