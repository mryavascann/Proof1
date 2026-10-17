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
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone

from veri import ayar, bicim, db as dbm
from veri.kayit import iso

IST = timezone(timedelta(hours=3))
GUN_MS = 24 * 3600 * 1000
# Misafir taramasının adımları (panoda /api/hesap/durum). Son adımı ("Hazır") taramayı başlatan söyler.
ILERLEME = ("Anahtar denetleniyor", "Borsa okunuyor", "Zincirler taranıyor", "Dolar karşılıkları", "Botlar ve köprü",
            "Hazır")


@dataclass
class Mesaj:
    metin: str
    baglanti: str
    kaynak: str                     # model adı ya da 'kalip'
    olgular: list = field(default_factory=list)


def _sayilar(metin: str) -> list:
    """Türkçe biçimli sayılar → Decimal ('1.234,56' → 1234.56; nokta binlik, virgül ondalık)."""
    sonuc = []
    for s in re.findall(r"\d[\d.,]*", metin):
        s = s.rstrip(".,")
        try:
            sonuc.append(Decimal(s.replace(".", "").replace(",", ".")))
        except InvalidOperation:
            pass
    return sonuc


def _gizli_sizdi_mi(db, oturum: str, metin: str) -> bool:
    """Cümledeki bir sayı gizli bir olgu değerine yakınsa (±%2; yuvarlama ve biçim farkı dahil) sızmış sayılır.
    Tek haneli tam sayılar (1, 3 kez…) karşılaştırılmaz."""
    gizli = []
    for (alanlar,) in db.execute("SELECT alanlar FROM olgu WHERE oturum=? AND gizli=1", (oturum,)):
        for v in json.loads(alanlar).values():
            gizli += [g for g in _sayilar(str(v)) if not (g == g.to_integral_value() and g < 10)]
    for s in _sayilar(metin):
        for g in gizli:
            if g and abs(s - g) <= abs(g) * Decimal("0.02"):
                return True
    return False


def _telegram_cumlesi(db, oturum: str):
    try:
        # Yalnız modelin denetimden geçmiş cümlesi; anlatıcı kalıba düştüyse bizim kalıbımız gider (devir metnindeki biçim).
        return db.execute("SELECT metin, model, olgular FROM cumle WHERE oturum=? AND yer='telegram' "
                          "AND denetim='gecti' ORDER BY id DESC LIMIT 1", (oturum,)).fetchone()
    except Exception:
        return None                 # cumle tablosu Merve'nin; henüz yoksa kalıp


def mesaj_hazirla(db, oturum: str, anlatici_komut: str, pano_url: str, zaman_asimi: float = 5.0) -> Mesaj:
    """Anlatıcı önce Telegram cümlesini, sonra pano/bant cümlelerini yazar. Telegram cümlesi gelir gelmez devam
    edilir; anlatıcı öldürülmez (pano cümlelerini arka planda yazmayı sürdürür). 5 sn'de gelmezse kalıp cümle."""
    baglanti = f"{pano_url.rstrip('/')}/?oturum={oturum}"
    r = None
    if anlatici_komut:
        komut = anlatici_komut.replace("{oturum}", oturum).replace("{db}", f'"{ayar.db_yolu()}"')
        p = subprocess.Popen(komut, shell=True, cwd=ayar.KOK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bitis = time.monotonic() + zaman_asimi
        while time.monotonic() < bitis:
            r = _telegram_cumlesi(db, oturum)
            if r is not None or p.poll() is not None:
                break
            time.sleep(0.2)
    r = r or _telegram_cumlesi(db, oturum)
    if r and r["metin"] and not _gizli_sizdi_mi(db, oturum, r["metin"]):
        return Mesaj(r["metin"], baglanti, r["model"] or "anlatici", json.loads(r["olgular"] or "[]"))
    from veri.olgu import kalip_cumle
    metin, dayanak = kalip_cumle(db, oturum)
    return Mesaj(metin or "proof1 bu sabah yeni bir şey görmedi.", baglanti, "kalip", dayanak)


def adim(gunluk: list, ad: str, fn):
    """Bir adımı çalıştırır; beklenmeyen hata işi yarıda kesmez, günlüğe yazılır ve None döner."""
    try:
        return fn()
    except Exception as e:
        gunluk.append(f"{ad} tamamlanamadı ({type(e).__name__})")
        return None


def hazir_gonder(db, oturum: str, telegram, anlatici_komut: str, pano_url: str) -> tuple:
    """Var olan olgulardan mesajı hazırlar ve gönderir (veri yeniden toplanmaz). (Mesaj, gönderildi mi)."""
    m = mesaj_hazirla(db, oturum, anlatici_komut, pano_url)
    gonderildi = bool(telegram is not None and telegram.hazir and telegram.gonder_pano(m.metin, m.baglanti))
    if gonderildi:
        db.execute("UPDATE uyari SET gonderildi=? WHERE oturum=? AND onem='acil'", (iso(datetime.now(timezone.utc)), oturum))
        db.commit()
    return m, gonderildi


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


def veriyi_topla(db, oturum: str, okx, atk, gunluk: list, taze: bool = False, tek_hesap: bool = False, ilerleme=None):
    """Borsa + zincir okuma ve deftere yazma (sabah işi ve canlı izleyici ortak kullanır).
    tek_hesap: okx ile atk aynı hesabın anahtarı (misafir). İşlem hesabının defteri bir kez ve 'ana' adıyla okunur;
    ikinci ATK açılmaz (aynı satırlar 'alt' ve 'ana' diye iki kez sayılmasın)."""
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
    s = alt_defteri(atk, hesap="ana" if tek_hesap else "alt")
    z = zincirle(s)
    hyaz(db, hareketlere(s))
    defter_yaz(db, s)
    gunluk.append(f"{'işlem hesabı' if tek_hesap else 'alt hesap'} defteri: {len(s)} satır, bakiye farkı {len(z.farklar)}")
    # Ana hesabın işlem hesabı (fonlama → işlem aktarımlarının karşı tarafı): ATK'nın ana profiliyle
    if not tek_hesap:                                   # tek hesapta yukarıda okundu
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
    if ilerleme:
        ilerleme(ILERLEME[2])
    kartlar = adresleri_cikar(cek, yat, TxOkuyucu(db, oturum).gonderen)
    adres_yaz(db, kartlar, cek)
    gunluk.append(f"adres: {len(kartlar)} ({sum(1 for k in kartlar if k.tahmin == 'benim')} büyük olasılıkla senin)")
    t = tara(db, ZincirOkuyucu(db, oturum, onbellek=not taze), cek, yat)
    gunluk.append(f"zincir: {t.okunan} adres-ağ okundu, {len(t.okunamayan)} okunamadı, {t.supheli} şüpheli")
    return cek, yat, cekim_dolar_guncelle


def calistir(gun: str | None = None, gonder: bool = True, hafta: bool | None = None, taze: bool = False,
             kimlik=None, db_yolu=None, anlatici: bool = True, ilerleme=None) -> dict:
    """Öntanımlılar sahibin sabah işidir: .env'deki iki hesap, öntanımlı veri dosyası, Telegram, anlatıcı.

    Misafir (panodan bağlanan tek hesap): kimlik=OkxKimlik, db_yolu=ayrı dosya, gonder=False, anlatici=False.
    Anahtarın yetkisi okunamazsa ya da işlem/çekim yetkisi varsa ATK açılırken, hiçbir hesap verisi okunmadan durur;
    borsa okunamazsa hata yükselir (boş dosyada geri düşülecek eski okuma yok). ilerleme(etiket): ILERLEME adımları.
    db_yolu verilirse bağlantı dönüşte kapanır (dosya sonra taşınabilsin ya da silinebilsin)."""
    if kimlik is not None and (gonder or anlatici):
        raise ValueError("misafir taraması Telegram'a yazmaz ve ücretli anlatıcıyı çalıştırmaz")
    ayar.env_yukle()
    db = dbm.baglan(db_yolu)
    try:
        return _calistir(db, gun, gonder, hafta, taze, kimlik, anlatici, ilerleme or (lambda _etiket: None))
    finally:
        if db_yolu is not None:
            db.close()


def _calistir(db, gun, gonder, hafta, taze, kimlik, anlatici, ilerleme) -> dict:
    from veri.atk import Atk
    from veri.bot import botlari_karsilastir
    from veri.defter import dolar_doldur
    from veri.fiyat import Fiyatci
    from veri.fotograf import borsa_bakiyeleri, cuzdan_seviyeleri
    from veri.kopru import fotograf_oku, fotografi_yaz, kopru_kur, kopruyu_yaz
    from veri.okx_imzali import OkxTr
    from veri.olgu import olgulari_kur
    from calistir.telegram import Telegram

    simdi_ms = int(time.time() * 1000)
    gun = gun or datetime.now(IST).strftime("%Y-%m-%d")
    bit_ms = int(datetime.strptime(gun, "%Y-%m-%d").replace(hour=9, tzinfo=IST).timestamp() * 1000)
    bas_ms = bit_ms - GUN_MS
    oturum = f"sabah-{gun}"
    gunluk: list[str] = []
    tek = kimlik is not None                       # misafir: tek hesap, iki rolü de aynı anahtar okur
    okx = OkxTr(kimlik if tek else ayar.okx_kimlik("ana"), db, oturum)
    ilerleme(ILERLEME[0])
    with Atk(kimlik if tek else ayar.okx_kimlik("alt"), db, oturum, yetki_zorunlu=tek) as atk:
        ilerleme(ILERLEME[1])
        # Her adım ayrı: biri düşerse (ör. tr.okx.com bağlantıyı keserse) eldeki defterle devam edilir ve mesaj yine gider.
        if tek:
            veriyi_topla(db, oturum, okx, atk, gunluk, taze, tek_hesap=True, ilerleme=ilerleme)
        elif adim(gunluk, "borsa/zincir okuması", lambda: veriyi_topla(db, oturum, okx, atk, gunluk, taze)) is None:
            gunluk.append("veritabanındaki son okuma kullanılıyor")
        from veri.adres import cekim_dolar_guncelle
        ilerleme(ILERLEME[3])
        fiyatci = Fiyatci(atk, db)
        n = adim(gunluk, "dolar karşılığı", lambda: dolar_doldur(db, fiyatci, en_cok=20000))
        adim(gunluk, "adres dolar toplamı", lambda: cekim_dolar_guncelle(db))
        gunluk.append(f"dolar karşılığı: {n or 0} satır")
        ilerleme(ILERLEME[4])
        atk_alt = None if tek else atk              # tek hesapta borsa:ana işlem hesabını da kapsar (iki kez sayılmaz)
        foto = adim(gunluk, "borsa fotoğrafı", lambda: _geri_sar(db, borsa_bakiyeleri(okx, atk_alt), bit_ms, simdi_ms)
                    if simdi_ms > bit_ms else borsa_bakiyeleri(okx, atk_alt)) or {}
        adim(gunluk, "fotoğraf kaydı", lambda: fotografi_yaz(db, gun, iso(datetime.fromtimestamp(bit_ms / 1000, tz=timezone.utc)),
                                                            {**foto, **cuzdan_seviyeleri(db, bit_ms)}, fiyatci.dolar, bit_ms))
        dun = (datetime.strptime(gun, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        dunku = {y: d for y, d in fotograf_oku(db, dun).items() if y.startswith("borsa")}
        fotolar = {**({"bit": foto} if foto else {}), **({"bas": dunku} if dunku else {})}
        if not dunku:
            gunluk.append("dünkü fotoğraf yok: borsa seviyesi defterden geri hesaplandı")
        kopru = adim(gunluk, "köprü", lambda: kopru_kur(db, gun, bas_ms, bit_ms, fiyatci.dolar, fotolar))
        from veri.kanit import atk_denetim_kaydi
        adim(gunluk, "ATK denetim kaydı", lambda: atk_denetim_kaydi(atk, db))   # panoda “denetim kaydı” (trade_get_history)
        botlar = adim(gunluk, "bot karşılaştırması", lambda: [b for b in botlari_karsilastir(atk, db)
                                                               if b.durus_ms and bas_ms < b.durus_ms <= bit_ms]) or []
        kopru_olgu = adim(gunluk, "olgular", lambda: olgulari_kur(db, oturum, gun, kopru, botlar, (bas_ms, bit_ms), fiyatci.dolar))
        if kopru:
            adim(gunluk, "köprü kaydı", lambda: kopruyu_yaz(db, gun, kopru, kopru_olgu or {}))
        if hafta or (hafta is None and datetime.strptime(gun, "%Y-%m-%d").weekday() == 0):
            def haftalik():
                h_kopru = kopru_kur(db, f"hafta-{gun}", bit_ms - 7 * GUN_MS, bit_ms, fiyatci.dolar, {"bit": foto} if foto else {})
                olgulari_kur(db, f"hafta-{gun}", gun, h_kopru, [b for b in botlari_karsilastir(atk, db)
                                                                if b.durus_ms and bit_ms - 7 * GUN_MS < b.durus_ms <= bit_ms],
                             (bit_ms - 7 * GUN_MS, bit_ms), fiyatci.dolar)
                kopruyu_yaz(db, f"hafta-{gun}", h_kopru)
                gunluk.append("haftalık özet hazırlandı")
            adim(gunluk, "haftalık özet", haftalik)
    komut = ayar.al("ANLATICI_KOMUT") if anlatici else ""          # anlatıcı yoksa kalıp cümle
    if gonder:
        t = Telegram(db=db, oturum=oturum)
        if not t.hazir:
            gunluk.append("Telegram gönderilmedi: eksik " + ", ".join(ayar.eksikler(["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])))
        m, gonderildi = hazir_gonder(db, oturum, t, komut, ayar.al("PANO_URL", "http://localhost:3003"))
    else:
        m, gonderildi = mesaj_hazirla(db, oturum, komut, ayar.al("PANO_URL", "http://localhost:3003")), False
    return {"oturum": oturum, "mesaj": m.metin, "kaynak": m.kaynak, "baglanti": m.baglanti, "gonderildi": gonderildi,
            "olgu": db.execute("SELECT COUNT(*) FROM olgu WHERE oturum=?", (oturum,)).fetchone()[0],
            "uyari": db.execute("SELECT COUNT(*) FROM uyari WHERE oturum=?", (oturum,)).fetchone()[0], "gunluk": gunluk}


def main():
    from veri.ayar import konsol_utf8
    konsol_utf8()                      # Windows: '→' gibi karakterlerde çökmesin
    p = argparse.ArgumentParser(description="proof1 sabah işi")
    p.add_argument("--gun")
    p.add_argument("--gonderme", action="store_true")
    p.add_argument("--hafta", action="store_true", default=None)
    p.add_argument("--taze", action="store_true", help="zincir önbelleğini kullanma")
    p.add_argument("--yalniz-gonder", action="store_true", help="veri toplama; var olan olgulardan mesajı gönder")
    a = p.parse_args()
    bas = time.time()
    if a.yalniz_gonder:
        from calistir.telegram import Telegram
        ayar.env_yukle()
        db = dbm.baglan()
        oturum = f"sabah-{a.gun or datetime.now(IST).strftime('%Y-%m-%d')}"
        m, ok = hazir_gonder(db, oturum, Telegram(db=db, oturum=oturum), ayar.al("ANLATICI_KOMUT"),
                             ayar.al("PANO_URL", "http://localhost:3003"))
        print(f"[{m.kaynak}] {m.metin}\nPanoyu aç: {m.baglanti}\nTelegram: {'gönderildi' if ok else 'gönderilmedi'}")
        return
    s = calistir(a.gun, gonder=not a.gonderme, hafta=a.hafta, taze=a.taze)
    for satir in s["gunluk"]:
        print("·", satir)
    print(f"\n[{s['kaynak']}] {s['mesaj']}\nPanoyu aç: {s['baglanti']}")
    print(f"\n{s['olgu']} olgu, {s['uyari']} uyarı · Telegram: {'gönderildi' if s['gonderildi'] else 'gönderilmedi'} · {time.time() - bas:.0f} sn")


if __name__ == "__main__":
    main()
