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
VERCEL = {"headers": [{"source": "/(.*)", "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"},
                                                      {"key": "Referrer-Policy", "value": "no-referrer"}]}]}


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
                _yaz(hedef / "veri" / f"rapor-{g}.json", veri.rapor(db, oturum, gizli=g == "1"))
                _yaz(hedef / "veri" / f"ayrinti-{g}.json",
                     veri.ayrinti(db, oturum, gizli=g == "1", muhur_ayar=MUHUR, kullanici="ornek"))
    _yaz(hedef / "veri" / "hesaplar.json", [{"hesap": "ana", "ad": "Örnek hesap"}])
    _yaz(hedef / "vercel.json", VERCEL)
    return hedef


if __name__ == "__main__":
    from veri.ayar import konsol_utf8
    konsol_utf8()
    print(f"statik demo: {uret(Path(sys.argv[1]) if len(sys.argv) > 1 else HEDEF)}")
