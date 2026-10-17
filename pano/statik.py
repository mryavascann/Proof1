"""Herkese açık demo (Vercel): örnek veriyle statik pano.

    python -m pano.statik                               # pano/_yayin/proof1/ üretir
    vercel deploy pano/_yayin/proof1 --prod --yes       # yayınlar (klasör adı Vercel proje adı olur)

Yalnız depodaki anonim örnek veritabanı okunur (ORNEK_DB); canlı veri, anahtar ve kişisel tam adres yayına girmez.
Sunucu uçları veri/ altında JSON dosyası olur (gizli açık ve kapalı iki sürüm; Vercel api/ klasörünü fonksiyon sayar).
"Kendi hesabını bağla" demoda kapalıdır: anahtar hiçbir sunucuya gönderilmez, kişi proof1'ı kendi bilgisayarında çalıştırır.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from pano import veri
from pano.sunucu import oturumlar

KOK = Path(__file__).resolve().parents[1]
STATIK = Path(__file__).resolve().parent / "static"
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
HEDEF = Path(__file__).resolve().parent / "_yayin" / "proof1"          # depoya girmez (.gitignore)
ISARET = ".proof1-yayin"                                                 # yalnız bu dosyayı taşıyan klasör silinir
# Kamuya açık Fuji kimlikleri (gizli değil): ERC-8004 agentId, mühür sözleşmesi, resmi Identity sözleşmesi
MUHUR = {"agent_id": "263", "sozlesme": "0x7C5aB869e8d972885673f19B848084279AAD0d48",
         "kimlik": "0x8004A818BFB912233c491871b3d84c89A494BD9e"}
# Sayfa yalnız OKX TR'ye bağlanabilir: tarayıcıda yapıştırılan anahtar başka hiçbir yere gönderilemez.
CSP = ("default-src 'self'; connect-src 'self' https://tr.okx.com; script-src 'self' https://cdn.jsdelivr.net; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; "
       "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
VERCEL = {"headers": [{"source": "/(.*)", "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"},
                                                      {"key": "Referrer-Policy", "value": "no-referrer"},
                                                      {"key": "Content-Security-Policy", "value": CSP}]}]}
# Zincirdeki son gerçek mühür (kamuya açık): 16 Ekim defteri, 16 satır
SON_MUHUR = {"gun": "2026-10-16", "kok": "0x2f3a83122d7f35c83da99d125dcc25092218a0f2b825cba50b8c1b1bce6b8f22",
             "onceki_kok": None, "islem": "0x5135feef5860b1689908ab2f56def30363fb22ca424ca8f0b109177e91b2ef34",
             "agent_id": "263", "sozlesme": MUHUR["sozlesme"], "zaman": None,
             "gezgin": "https://testnet.snowtrace.io/tx/0x5135feef5860b1689908ab2f56def30363fb22ca424ca8f0b109177e91b2ef34"}


def _yaz(yol: Path, nesne) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(nesne, ensure_ascii=False), encoding="utf-8")


def uret(hedef: Path = HEDEF) -> Path:
    hedef = Path(hedef)
    if hedef.exists():
        if not (hedef / ISARET).is_file():
            raise ValueError(f"{hedef} bir proof1 yayın klasörü değil; silinmedi")
        shutil.rmtree(hedef)
    shutil.copytree(STATIK, hedef / "static")
    (hedef / ISARET).write_text("python -m pano.statik çıktısı\n", encoding="utf-8")
    html = (STATIK / "index.html").read_text(encoding="utf-8").replace('<html lang="tr">', '<html lang="tr" data-statik="1">', 1)
    (hedef / "index.html").write_text(html, encoding="utf-8")
    (hedef / "static" / "index.html").unlink()
    with tempfile.TemporaryDirectory() as gecici:
        db_yolu = Path(gecici) / "ornek.db"
        shutil.copy(ORNEK_DB, db_yolu)                                   # depodaki dosya değişmez
        with closing(sqlite3.connect(db_yolu)) as db:
            oturum = oturumlar(db)[0]
        from anlatim import anlat
        anlat.anlat(db_yolu, oturum, None, kullanici="ornek")           # kalıp cümleler; model çağrısı ve ücret yok
        with closing(sqlite3.connect(db_yolu)) as db:
            for g in ("1", "0"):
                r = veri.rapor(db, oturum, gizli=g == "1")
                for kap in (r.get("kopru") or {}).get("kapsamlar", {}).values():   # örnekte seviye yok: "0 $" yanıltır
                    kap["kalemler"] = [k for k in kap["kalemler"] if k["kalem"] not in ("baslangic", "bitis")]
                _yaz(hedef / "veri" / f"rapor-{g}.json", r)
                a = veri.ayrinti(db, oturum, gizli=g == "1", muhur_ayar=MUHUR, kullanici="ornek")
                a["muhur"]["son"] = a["muhur"]["son"] or [SON_MUHUR]
                _yaz(hedef / "veri" / f"ayrinti-{g}.json", a)
    _yaz(hedef / "veri" / "hesaplar.json", [{"hesap": "ana", "ad": "Örnek hesap"}])
    _yaz(hedef / "vercel.json", VERCEL)
    return hedef


if __name__ == "__main__":
    from veri.ayar import konsol_utf8
    konsol_utf8()
    print(f"statik demo: {uret(Path(sys.argv[1]) if len(sys.argv) > 1 else HEDEF)}")
