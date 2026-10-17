"""Sabah işi (tek komut): defter → adresler → zincir → fotoğraf → köprü → bot → olgular → anlatıcı → Telegram.

Çalıştır:   python -m calistir.sabah              (bugün, Telegram'a gönderir)
            python -m calistir.sabah --gonderme   (her şeyi yapar, mesajı yalnız ekrana yazar)
            python -m calistir.sabah --gun 2026-10-17
            python -m calistir.sabah --taze       (zincir önbelleğini atla)
Pazartesi ayrıca haftalık özet gider (ya da --hafta).
"""
import argparse
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from veri import ayar, bicim, db as dbm
from veri.kayit import iso

IST = timezone(timedelta(hours=3))
GUN_MS = 24 * 3600 * 1000


@dataclass
class Mesaj:
    metin: str
    baglanti: str
    kaynak: str                     # model adı ya da 'kalip'
    olgular: list = field(default_factory=list)


def _sayilar(metin: str) -> set[str]:
    return {s.rstrip(".,") for s in re.findall(r"\d[\d.,]*", metin)}


def _gizli_sizdi_mi(db, oturum: str, metin: str) -> bool:
    gizli = set()
    for (alanlar,) in db.execute("SELECT alanlar FROM olgu WHERE oturum=? AND gizli=1", (oturum,)):
        for v in json.loads(alanlar).values():
            gizli |= {s for s in _sayilar(str(v)) if len(s.replace(",", "").replace(".", "")) >= 2}
    return bool(gizli & _sayilar(metin))


def mesaj_hazirla(db, oturum: str, anlatici_komut: str, pano_url: str, zaman_asimi: float = 5.0) -> Mesaj:
    baglanti = f"{pano_url.rstrip('/')}/?oturum={oturum}"
    if anlatici_komut:
        komut = anlatici_komut.replace("{oturum}", oturum).replace("{db}", f'"{ayar.db_yolu()}"')
        p = subprocess.Popen(komut, shell=True, cwd=ayar.KOK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=zaman_asimi)
        except subprocess.TimeoutExpired:
            p.kill()                # 5 saniyede dönmedi: kalıp cümle
    try:
        r = db.execute("SELECT metin, model, olgular FROM cumle WHERE oturum=? AND yer='telegram' AND denetim='gecti' "
                       "ORDER BY id DESC LIMIT 1", (oturum,)).fetchone()
    except Exception:
        r = None                    # cumle tablosu Merve'nin; yoksa kalıp
    if r and r["metin"] and not _gizli_sizdi_mi(db, oturum, r["metin"]):
        return Mesaj(r["metin"], baglanti, r["model"] or "anlatici", json.loads(r["olgular"] or "[]"))
    from veri.olgu import kalip_cumle
    metin, dayanak = kalip_cumle(db, oturum)
    return Mesaj(metin or "proof1 bu sabah yeni bir şey görmedi.", baglanti, "kalip", dayanak)


def _geri_sar(db, foto: dict, hedef_ms: int, simdi_ms: int) -> dict:
    """Şimdiki borsa fotoğrafından 09:00'daki seviyeyi bulur: şimdi − (09:00, şimdi] akışları."""
    from decimal import Decimal
    from veri.kopru import _ms
    sonuc = {yer: dict(d) for yer, d in foto.items()}
    for r in db.execute("SELECT zaman, hesap, varlik, miktar FROM hareket WHERE kaynak='borsa' AND durum='ok'"):
        t = _ms(r["zaman"])
        if hedef_ms < t <= simdi_ms:
            d = sonuc.setdefault(f"borsa:{r['hesap']}", {})
            d[r["varlik"]] = d.get(r["varlik"], Decimal(0)) - Decimal(r["miktar"])
    return sonuc


def veriyi_topla(db, oturum: str, okx, atk, gunluk: list, taze: bool = False):
    """Borsa + zincir okuma ve deftere yazma (sabah işi ve canlı izleyici ortak kullanır)."""
    from veri.adres import adresleri_cikar, cekim_dolar_guncelle, yaz as adres_yaz
    from veri.borsa import cekimler, fonlama_defteri, tamamlanan, yatirmalar
    from veri.defter import (alt_defteri, cekim_hareketleri, defter_yaz, fonlama_hareketleri, hareketlere, yaz as hyaz,
                             zincirle)
    from veri.zincir.okuyucu import ZincirOkuyucu
    from veri.zincir.tara import tara
    from veri.zincir.tx import TxOkuyucu
    cek, yat = tamamlanan(cekimler(okx)), tamamlanan(yatirmalar(okx))
    hyaz(db, cekim_hareketleri(cek + yat))
    gunluk.append(f"borsa: {len(cek)} çekim, {len(yat)} yatırma")
    try:
        hyaz(db, fonlama_hareketleri(fonlama_defteri(okx)))
    except Exception as e:
        gunluk.append(f"fonlama defteri okunamadı ({type(e).__name__})")
    s = alt_defteri(atk)
    z = zincirle(s)
    hyaz(db, hareketlere(s))
    defter_yaz(db, s)
    gunluk.append(f"alt hesap defteri: {len(s)} satır, bakiye farkı {len(z.farklar)}")
    # Ana hesabın işlem hesabı (fonlama → işlem aktarımlarının karşı tarafı): ATK'nın ana profiliyle
    try:
        from veri.atk import Atk
        with Atk(ayar.okx_kimlik("ana"), db, oturum) as atk_ana:
            sa = alt_defteri(atk_ana, hesap="ana")
        za = zincirle(sa)
        hyaz(db, hareketlere(sa))
        defter_yaz(db, sa)
        gunluk.append(f"ana hesap işlem defteri: {len(sa)} satır, bakiye farkı {len(za.farklar)}")
    except Exception as e:
        gunluk.append(f"ana hesap işlem defteri okunamadı ({type(e).__name__})")
    kartlar = adresleri_cikar(cek, yat, TxOkuyucu(db, oturum).gonderen)
    adres_yaz(db, kartlar, cek)
    gunluk.append(f"adres: {len(kartlar)} ({sum(1 for k in kartlar if k.tahmin == 'benim')} büyük olasılıkla senin)")
    t = tara(db, ZincirOkuyucu(db, oturum, onbellek=not taze), cek, yat)
    gunluk.append(f"zincir: {t.okunan} adres-ağ okundu, {len(t.okunamayan)} okunamadı, {t.supheli} şüpheli")
    return cek, yat, cekim_dolar_guncelle


def calistir(gun: str | None = None, gonder: bool = True, hafta: bool | None = None, taze: bool = False) -> dict:
    from veri.atk import Atk
    from veri.bot import botlari_karsilastir
    from veri.defter import dolar_doldur
    from veri.fiyat import Fiyatci
    from veri.fotograf import borsa_bakiyeleri, cuzdan_seviyeleri
    from veri.kopru import fotograf_oku, fotografi_yaz, kopru_kur, kopruyu_yaz
    from veri.okx_imzali import OkxTr
    from veri.olgu import olgulari_kur
    from calistir.telegram import Telegram

    ayar.env_yukle()
    db = dbm.baglan()
    simdi_ms = int(time.time() * 1000)
    gun = gun or datetime.now(IST).strftime("%Y-%m-%d")
    bit_ms = int(datetime.strptime(gun, "%Y-%m-%d").replace(hour=9, tzinfo=IST).timestamp() * 1000)
    bas_ms = bit_ms - GUN_MS
    oturum = f"sabah-{gun}"
    gunluk: list[str] = []
    okx = OkxTr(ayar.okx_kimlik("ana"), db, oturum)
    with Atk(ayar.okx_kimlik("alt"), db, oturum) as atk:
        cek, yat, cekim_dolar_guncelle = veriyi_topla(db, oturum, okx, atk, gunluk, taze)
        fiyatci = Fiyatci(atk, db)
        n = dolar_doldur(db, fiyatci, en_cok=20000)
        cekim_dolar_guncelle(db)
        gunluk.append(f"dolar karşılığı: {n} satır")
        foto = _geri_sar(db, borsa_bakiyeleri(okx, atk), bit_ms, simdi_ms) if simdi_ms > bit_ms else borsa_bakiyeleri(okx, atk)
        fotografi_yaz(db, gun, iso(datetime.fromtimestamp(bit_ms / 1000, tz=timezone.utc)),
                      {**foto, **cuzdan_seviyeleri(db, bit_ms)}, fiyatci.dolar, bit_ms)
        dun = (datetime.strptime(gun, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        dunku = {y: d for y, d in fotograf_oku(db, dun).items() if y.startswith("borsa")}
        fotolar = {"bit": foto, **({"bas": dunku} if dunku else {})}
        if not dunku:
            gunluk.append("dünkü fotoğraf yok: borsa seviyesi defterden geri hesaplandı")
        kopru = kopru_kur(db, gun, bas_ms, bit_ms, fiyatci.dolar, fotolar)
        botlar = [b for b in botlari_karsilastir(atk, db) if b.durus_ms and bas_ms < b.durus_ms <= bit_ms]
        kopru_olgu = olgulari_kur(db, oturum, gun, kopru, botlar, (bas_ms, bit_ms), fiyatci.dolar)
        kopruyu_yaz(db, gun, kopru, kopru_olgu)
        if hafta or (hafta is None and datetime.strptime(gun, "%Y-%m-%d").weekday() == 0):
            h_oturum = f"hafta-{gun}"
            h_kopru = kopru_kur(db, f"hafta-{gun}", bit_ms - 7 * GUN_MS, bit_ms, fiyatci.dolar, {"bit": foto})
            olgulari_kur(db, h_oturum, gun, h_kopru, [b for b in botlari_karsilastir(atk, db)
                                                      if b.durus_ms and bit_ms - 7 * GUN_MS < b.durus_ms <= bit_ms],
                         (bit_ms - 7 * GUN_MS, bit_ms), fiyatci.dolar)
            kopruyu_yaz(db, f"hafta-{gun}", h_kopru)
            gunluk.append("haftalık özet hazırlandı")
    m = mesaj_hazirla(db, oturum, ayar.al("ANLATICI_KOMUT"), ayar.al("PANO_URL", "http://localhost:3003"))
    gonderildi = False
    if gonder:
        t = Telegram(db=db, oturum=oturum)
        if t.hazir:
            gonderildi = bool(t.gonder_pano(m.metin, m.baglanti))
        else:
            gunluk.append("Telegram gönderilmedi: eksik " + ", ".join(ayar.eksikler(["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])))
    if gonderildi:
        db.execute("UPDATE uyari SET gonderildi=? WHERE oturum=? AND onem='acil'", (iso(datetime.now(timezone.utc)), oturum))
        db.commit()
    return {"oturum": oturum, "mesaj": m.metin, "kaynak": m.kaynak, "baglanti": m.baglanti, "gonderildi": gonderildi,
            "olgu": db.execute("SELECT COUNT(*) FROM olgu WHERE oturum=?", (oturum,)).fetchone()[0],
            "uyari": db.execute("SELECT COUNT(*) FROM uyari WHERE oturum=?", (oturum,)).fetchone()[0], "gunluk": gunluk}


def main():
    p = argparse.ArgumentParser(description="proof1 sabah işi")
    p.add_argument("--gun")
    p.add_argument("--gonderme", action="store_true")
    p.add_argument("--hafta", action="store_true", default=None)
    p.add_argument("--taze", action="store_true", help="zincir önbelleğini kullanma")
    a = p.parse_args()
    bas = time.time()
    s = calistir(a.gun, gonder=not a.gonderme, hafta=a.hafta, taze=a.taze)
    for satir in s["gunluk"]:
        print("·", satir)
    print(f"\n[{s['kaynak']}] {s['mesaj']}\nPanoyu aç: {s['baglanti']}")
    print(f"\n{s['olgu']} olgu, {s['uyari']} uyarı · Telegram: {'gönderildi' if s['gonderildi'] else 'gönderilmedi'} · {time.time() - bas:.0f} sn")


if __name__ == "__main__":
    main()
