"""Merve için örnek veritabanı: ortak/ornek/proof1_ornek.db

Gerçek verinin kesiti. Adresler ve işlem kimlikleri yer tutucudur (BENIM_1, ADRES_7, TX_12), güncel bakiye yoktur.
Borsa satırları canlı okunur (çekim kaydı, alt hesap defteri, botlar); zincir olayları (11 Ekim AVAX, MOCA)
şimdilik devir metnindeki doğrulanmış değerlerdir — B4 bitince zincir okuyucusunun çıktısıyla yeniden üretilir.

Çalıştır:  python -m veri.ornek
"""
import json
from decimal import Decimal

from veri import ayar, bicim, db as dbm
from veri.atk import Atk
from veri.bot import botlari_karsilastir
from veri.borsa import cekimler, tamamlanan
from veri.defter import alt_defteri, cekim_hareketleri, dolar_doldur, hareketlere, yaz, zincirle
from veri.fiyat import Fiyatci
from veri.kayit import simdi
from veri.okx_imzali import OkxTr
from veri.olgu import OlguYazici, bot_olgusu

HEDEF = ayar.KOK / "ortak" / "ornek" / "proof1_ornek.db"
SABAH = "sabah-2026-10-17"
GUN11 = "ornek-2026-10-12"

# Devir metni bölüm 4 (doğrulandı). Zaman UTC; İstanbul = UTC+3.
ZINCIR = [
    # adres, zaman, varlik, miktar, tur, karsi, islem
    ("BENIM_1", "2026-10-11T12:33:00.000Z", "AVAX", "0.98280221", "giris", "ana", "TX_AVAX_1"),
    ("BENIM_1", "2026-10-11T12:52:00.000Z", "AVAX", "-0.1", "takas", None, "TX_AVAX_2"),
    ("BENIM_1", "2026-10-11T12:52:00.000Z", "USDC", "1.039211", "takas", None, "TX_AVAX_2"),
    ("BENIM_1", "2026-10-11T12:52:00.000Z", "AVAX", "-0.001773", "ucret", None, "TX_AVAX_2"),
    ("BENIM_1", "2026-10-11T12:53:00.000Z", "AVAX", "0.000211981558", "taninmadi", None, "TX_AVAX_3"),
    ("BENIM_1", "2026-10-11T12:53:10.000Z", "AVAX", "-0.1", "gonderim", "BENIM_2", "TX_AVAX_4"),
    ("BENIM_1", "2026-10-11T12:53:10.000Z", "AVAX", "-0.000105", "ucret", None, "TX_AVAX_4"),
    ("BENIM_1", "2026-10-11T12:53:20.000Z", "USDC", "-1", "gonderim", "BENIM_2", "TX_AVAX_5"),
    ("BENIM_1", "2026-10-11T12:53:20.000Z", "AVAX", "-0.000311", "ucret", None, "TX_AVAX_5"),
    ("BENIM_2", "2026-10-11T12:53:10.000Z", "AVAX", "0.1", "giris", "BENIM_1", "TX_AVAX_4"),
    ("BENIM_2", "2026-10-11T12:53:20.000Z", "USDC", "1", "giris", "BENIM_1", "TX_AVAX_5"),
    ("ADRES_MOCA", "2025-09-22T10:00:00.000Z", "MOCA", "100", "giris", None, "TX_MOCA_1"),
    ("ADRES_MOCA", "2025-09-24T10:00:00.000Z", "MOCA", "-100", "gonderim", "stake", "TX_MOCA_2"),
    ("ADRES_MOCA", "2025-12-26T10:00:00.000Z", "MOCA", "4066", "giris", None, "TX_MOCA_3"),
    ("ADRES_MOCA", "2026-04-09T10:00:00.000Z", "PIEVERSE", "-46.15", "takas", None, "TX_MOCA_4"),
    ("ADRES_MOCA", "2026-04-09T10:00:00.000Z", "MOCA", "1587", "takas", None, "TX_MOCA_4"),
    ("ADRES_MOCA", "2026-04-09T10:00:00.000Z", "ETH", "-0.000129", "ucret", None, "TX_MOCA_4"),
]


def uret(hedef=HEDEF) -> dict:
    if hedef.exists():
        hedef.unlink()
    db = dbm.baglan(hedef)
    db.execute("CREATE TABLE _ornek (anahtar TEXT PRIMARY KEY, deger TEXT)")
    canli = dbm.baglan(ayar.KOK / "data" / "ornek_uretim.db")     # fiyat önbelleği, depoya girmez

    okx = OkxTr(ayar.okx_kimlik("ana"), db, SABAH)
    cek = tamamlanan(cekimler(okx))

    # Adresler: gerçek adres yerine etiket. 11 Ekim AVAX alıcısı BENIM_1.
    etiket, sira = {}, 0
    for k in cek:
        anahtar = (k.adres, k.ag.anahtar)
        if anahtar in etiket:
            continue
        if k.ccy == "AVAX":
            etiket[anahtar] = "BENIM_1"
        else:
            sira += 1
            etiket[anahtar] = f"ADRES_{sira}"
    adres_id = {}
    for (adres, ag), et in etiket.items():
        ilgili = [k for k in cek if (k.adres, k.ag.anahtar) == (adres, ag)]
        ag_ = ilgili[0].ag
        c = db.execute("INSERT INTO adres (adres, etiket, kisa, ag, katman, tahmin, kanit, cekim_sayisi, ilk_cekim, son_cekim)"
                       " VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (et, et, et, ag, ag_.katman, "benim" if et.startswith("BENIM") else "belli_degil",
                        "Örnek veri: B3'te kanıtla yeniden üretilecek." if not et.startswith("BENIM")
                        else "Çekim kaydındaki alıcı; zincirde ikinci hesaba aktarım yaptı.",
                        len(ilgili), bicim.tarih(min(k.ts for k in ilgili)), bicim.tarih(max(k.ts for k in ilgili))))
        adres_id[et] = c.lastrowid
    for et, ag in (("BENIM_2", "avalanche"), ("ADRES_MOCA", "ethereum")):
        c = db.execute("INSERT INTO adres (adres, etiket, kisa, ag, katman, tahmin, kanit) VALUES (?,?,?,?,?,?,?)",
                       (et, et, et, ag, 3, "benim" if et == "BENIM_2" else "belli_degil",
                        "11 Ekim'de BENIM_1'den aktarım aldı (ikinci hesap)." if et == "BENIM_2" else "MOCA hikâyesinin adresi."))
        adres_id[et] = c.lastrowid

    # Çekim hareketleri: adres → etiket, işlem kimliği → TX_n
    h = cekim_hareketleri(cek)
    for i, x in enumerate(h):
        k = next(k for k in cek if x["ham_kimlik"].startswith(f"cekim:{k.kimlik}"))
        et = etiket[(k.adres, k.ag.anahtar)]
        x.update(karsi=et, islem_kimligi=f"TX_C{cek.index(k) + 1}", ham_kimlik=f"ornek:{x['ham_kimlik'].split(':', 1)[1]}")
    yaz(db, h)

    with Atk(ayar.okx_kimlik("alt"), db, SABAH) as atk:
        s = alt_defteri(atk)
        zincirle(s)
        ah = hareketlere(s)
        for x in ah:
            x["ham_kimlik"] = "ornek:" + x["ham_kimlik"].rsplit(":", 1)[-1]
        yaz(db, ah)
        botlar = botlari_karsilastir(atk, canli, hareketler=hareketlere(s))
        # zincir olayları (devir metninden)
        zh = []
        for i, (et, zaman, varlik, miktar, tur, karsi, tx) in enumerate(ZINCIR):
            zh.append({"zaman": zaman, "kaynak": "zincir", "hesap": "cuzdan", "adres_id": adres_id[et],
                       "ag": "avalanche" if varlik in ("AVAX", "USDC") else "ethereum", "varlik": varlik, "miktar": miktar,
                       "dolar": None, "tur": tur, "islem_kimligi": tx, "karsi": karsi, "supheli": 0, "durum": "ok",
                       "kaynak_okuma": "devir-metni (B4'te zincirden)", "ham_kimlik": f"ornek:zincir:{i}"})
        yaz(db, zh)
        dolar_doldur(db, Fiyatci(atk, canli), en_cok=2000)
    # PIEVERSE'in o günkü dolar fiyatı yok: uydurulmaz.
    db.execute("UPDATE hareket SET dolar=NULL WHERE varlik='PIEVERSE'")

    # Olgular
    y = OlguYazici(db, SABAH)
    devir = [k for k in cek if k.ts < 1791752400000]
    toplam = sum((Decimal(r["dolar"]) for r in db.execute(
        "SELECT dolar FROM hareket WHERE tur='cekim' AND dolar IS NOT NULL AND zaman < '2026-10-11T21'")), Decimal(0))
    o_ozet = y.ekle("cekim_ozet", {"cekim_sayisi": str(len(devir)), "adres_sayisi": "37", "toplam_dolar": bicim.dolar(-toplam),
                                   "donem": "Aralık 2024 – Ekim 2026", "borsa": "OKX TR"})
    o_kalan = y.ekle("kalan_ozet", {"adres_sayisi": "10", "dolar": "360 $"}, gizli=True)
    for ag, ad in (("arbitrum", "Arbitrum"), ("ethereum", "Ethereum"), ("chiliz", "Chiliz"), ("polygon", "Polygon"),
                   ("tron", "Tron"), ("avalanche", "Avalanche")):
        ilgili = [k for k in devir if k.ag.anahtar == ag]
        d = sum((Decimal(r["dolar"]) for r in db.execute(
            "SELECT h.dolar FROM hareket h WHERE h.tur='cekim' AND h.dolar IS NOT NULL AND h.zaman < '2026-10-11T21' AND h.ag LIKE ?",
            (f"%{ilgili[0].ag_adi}",))), Decimal(0)) if ilgili else Decimal(0)
        y.ekle("ag_payi", {"ag": ad, "cekim_sayisi": str(len(ilgili)), "dolar": bicim.dolar(-d)})
    y.ekle("moca_takas", {"tarih": "9 Nisan 2026", "verilen": "46,15 PIEVERSE", "alinan": "1.587 MOCA",
                          "ag_ucreti": "0,000129 ETH", "verilen_dolar": "bilinmiyor", "adres": "ADRES_MOCA"})
    y.ekle("moca_stake", {"tarih": "24 Eylül 2025", "miktar": "100 MOCA", "islev": "stake", "geri_donmedi": "evet",
                          "adres": "ADRES_MOCA"})
    for b in botlar:
        if b.algo_id in ("4014895767398817792", "3985361557394993152"):
            bot_olgusu(y, b)

    y11 = OlguYazici(db, GUN11)
    o1 = y11.ekle("cekim", {"tarih": "11 Ekim 2026 15:32", "miktar": "0,9828 AVAX", "ag": "Avalanche",
                            "ucret": "0,015 AVAX", "adres": "BENIM_1"})
    o2 = y11.ekle("takas", {"tarih": "11 Ekim 2026 15:52", "verilen": "0,1 AVAX", "alinan": "1,04 USDC",
                            "ag_ucreti": "0,001773 AVAX", "adres": "BENIM_1"})
    o3 = y11.ekle("taninmadi", {"tarih": "11 Ekim 2026 15:53", "miktar": "0,000212 AVAX", "adres": "BENIM_1"})
    o4 = y11.ekle("gonderim", {"tarih": "11 Ekim 2026 15:53", "miktar": "0,1 AVAX", "alici": "BENIM_2",
                               "alici_benim": "evet", "ag_ucreti": "0,000105 AVAX"})
    o5 = y11.ekle("gonderim", {"tarih": "11 Ekim 2026 15:53", "miktar": "1 USDC", "alici": "BENIM_2",
                               "alici_benim": "evet", "ag_ucreti": "0,000311 AVAX"})
    o6 = y11.ekle("kopru", {"kapsam": "borsa", "degisim": "-0,9978 AVAX"})
    o7 = y11.ekle("kopru", {"kapsam": "servet", "degisim": "-0,017 AVAX", "neden": "yalnız ücretler"})
    y11.uyari("taninmadi", "bilgi", [o3])
    for sira, (kapsam, kalem, varlik_tutar, aciklama, olg) in enumerate([
        ("borsa", "disari", {"AVAX": "-0.98280221"}, "BENIM_1'e çekim", [o1]),
        ("borsa", "ucret", {"AVAX": "-0.015"}, "çekim ücreti", [o1]),
        ("servet", "aktarim", {"AVAX": "0"}, "borsa → BENIM_1 (kendi hesapların arası)", [o1]),
        ("servet", "takas", {"AVAX": "-0.1", "USDC": "1.039211"}, "AVAX → USDC", [o2]),
        ("servet", "ucret", {"AVAX": "-0.017189"}, "çekim ücreti + 3 ağ ücreti", [o1, o2, o4, o5]),
        ("servet", "aciklanamayan", {"AVAX": "0.000211981558"}, "kaynağı tanınmayan giriş", [o3]),
        ("servet", "aktarim", {"AVAX": "0", "USDC": "0"}, "BENIM_1 → BENIM_2 (kendi hesapların arası)", [o4, o5]),
    ], start=1):
        db.execute("INSERT INTO kopru (gun, kapsam, sira, kalem, tutar, varlik_tutar, aciklama, olgular) VALUES (?,?,?,?,?,?,?,?)",
                   ("2026-10-12", kapsam, sira, kalem, "0", json.dumps(varlik_tutar), aciklama, json.dumps(olg)))

    # Çağrı kaydı: bu üretimde yapılan gerçek çağrılar (maskeli) zaten SABAH oturumuyla yazıldı.
    db.execute("INSERT INTO _ornek VALUES ('surum', 'v1'), ('uretim', ?), ('not', ?)",
               (simdi(), "Zincir olayları devir metninden; kopru.tutar dolar alanları B6'da doldurulacak. Seviye/bakiye yok."))
    db.commit()
    ozet = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("hareket", "adres", "olgu", "uyari", "kopru", "cagri", "fotograf")}
    db.execute("PRAGMA journal_mode=DELETE")
    db.close()
    canli.close()
    return ozet


if __name__ == "__main__":
    print(uret())
