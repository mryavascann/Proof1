"""Merve için örnek veritabanı: ortak/ornek/proof1_ornek.db

Gerçek verinin kesiti. Adresler ve işlem kimlikleri yer tutucudur (BENIM_1, ADRES_7, TX_12), güncel bakiye yoktur.
Borsa satırları canlı okunur (çekim kaydı, alt hesap defteri, botlar); zincir olayları (11 Ekim AVAX, MOCA)
şimdilik devir metnindeki doğrulanmış değerlerdir — B4 bitince zincir okuyucusunun çıktısıyla yeniden üretilir.

Çalıştır:  python -m veri.ornek
"""
import json
from decimal import Decimal
from pathlib import Path

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


IC_TABLOLAR_SIL = ("_zincir_ham", "_tx_gonderen", "_defter", "_atk_denetim", "_fiyat")
MASKE = __import__("re").compile(r"(?:0x)?[0-9a-fA-F]{2,6}…[0-9a-fA-F]{4}|T[1-9A-HJ-NP-Za-km-z]{3,5}…\w{4}")


def gecmis_gun(db, gun: str, oturum: str):
    """Var olan defterden geçmiş bir günün köprüsü ve olguları (yeniden okuma yok; fiyatlar ATK'dan)."""
    from datetime import datetime, timedelta, timezone
    from veri.kopru import kopru_kur, kopruyu_yaz
    from veri.olgu import olgulari_kur
    ist = timezone(timedelta(hours=3))
    bit = int(datetime.strptime(gun, "%Y-%m-%d").replace(hour=9, tzinfo=ist).timestamp() * 1000)
    bas = bit - 24 * 3600 * 1000
    with Atk(ayar.okx_kimlik("alt"), db, oturum) as atk:
        f = Fiyatci(atk, db)
        k = kopru_kur(db, gun, bas, bit, f.dolar)
        kopruyu_yaz(db, gun, k, olgulari_kur(db, oturum, gun, k, [], (bas, bit), f.dolar))


# Beyaz liste: örnek veritabanına yalnız bunlar girer (Merve'nin tabloları, iç önbellekler, bakiye/kapanış girmez).
IZINLI_TABLOLAR = ("hareket", "adres", "fotograf", "kopru", "olgu", "uyari", "cagri", "_ag_durum", "_olay", "_ornek")


def canlidan(kaynak=None, hedef=HEDEF, gecmis: bool = True) -> dict:
    """v3: sabah işinin gerçek çıktısından anonim kopya, beyaz listeyle sıfırdan kurulur.
    Adres → etiket, işlem kimliği → TX_n; seviye, bakiye, sohbet kimliği ve kaynak kimlikleri yok."""
    import sqlite3
    kaynak = Path(kaynak or ayar.db_yolu())
    if gecmis:
        gecmis_gun(dbm.baglan(kaynak), "2026-10-12", GUN11)           # 11 Ekim AVAX günü
    if hedef.exists():
        hedef.unlink()
    db = dbm.baglan(hedef)                                              # yalnız sözleşmedeki (Buğra'nın) tablolar
    db.execute("""CREATE TABLE IF NOT EXISTS _ag_durum (adres_id INTEGER, ag TEXT, durum TEXT, kaynak TEXT,
                  olay INTEGER, cekim_agi INTEGER, zaman TEXT, PRIMARY KEY (adres_id, ag))""")
    db.execute("""CREATE TABLE IF NOT EXISTS _olay (adres_id INTEGER, ag TEXT, tx TEXT, ts INTEGER, tur TEXT, islev TEXT,
                  neden TEXT, PRIMARY KEY (adres_id, ag, tx))""")
    db.execute("ATTACH DATABASE ? AS k", (str(kaynak),))
    var = {r[0] for r in db.execute("SELECT name FROM k.sqlite_master WHERE type='table'")}
    for t in ("hareket", "adres", "kopru", "olgu", "uyari", "cagri", "_ag_durum", "_olay"):
        if t in var:
            db.execute(f"INSERT INTO main.{t} SELECT * FROM k.{t}")
    db.commit()
    db.execute("DETACH DATABASE k")
    db.row_factory = sqlite3.Row
    db.execute("UPDATE adres SET adres=etiket, kisa=etiket, gezgin_url=NULL")
    db.execute("UPDATE olgu SET kaynak='[]'")                                    # billId / algoId / hareket kimliği yok
    db.execute("DELETE FROM cagri WHERE kaynak='Telegram'")                      # sohbet kimliği taşıyabilir
    db.execute("UPDATE kopru SET varlik_tutar='{}' WHERE kalem='fiyat'")          # fiyat kalemi = dünkü seviye × fark
    for r in db.execute("SELECT oturum, no, alanlar FROM olgu WHERE tur='kopru'").fetchall():
        a = json.loads(r["alanlar"])
        if a.get("kalem") == "fiyat" and "coin" in a:
            a.pop("coin")
            db.execute("UPDATE olgu SET alanlar=? WHERE oturum=? AND no=?", (json.dumps(a, ensure_ascii=False), r["oturum"], r["no"]))
    # Kırp: depoya sığsın. Benim adreslerin anlamlı işlemleri tam; diğer adreslerde (adres, ağ) başına son 100 satır;
    # yalnız ücretten ibaret işlemler (onay, başarısız) atılır.
    benim = "(SELECT id FROM adres WHERE tahmin='benim')"
    db.execute(f"""DELETE FROM hareket WHERE id IN (SELECT id FROM (
                     SELECT id, ROW_NUMBER() OVER (PARTITION BY adres_id, ag ORDER BY zaman DESC) sira FROM hareket
                     WHERE hesap='cuzdan' AND tur != 'ucret' AND adres_id NOT IN {benim}) WHERE sira > 100)""")
    db.execute("CREATE TEMP TABLE anlamli AS SELECT DISTINCT adres_id, islem_kimligi FROM hareket WHERE hesap='cuzdan' AND tur != 'ucret'")
    db.execute("CREATE INDEX temp.anlamli_i ON anlamli (adres_id, islem_kimligi)")
    db.execute("""DELETE FROM hareket WHERE hesap='cuzdan' AND tur='ucret' AND NOT EXISTS (
                    SELECT 1 FROM anlamli a WHERE a.adres_id=hareket.adres_id AND a.islem_kimligi=hareket.islem_kimligi)""")
    # İşlem kimliği → TX_n (eşleme tablosuyla tek geçiş)
    db.execute("CREATE TEMP TABLE txmap (eski TEXT PRIMARY KEY, yeni TEXT)")
    db.execute("INSERT INTO txmap SELECT islem_kimligi, 'TX_' || ROW_NUMBER() OVER (ORDER BY MIN(id)) FROM hareket "
               "WHERE islem_kimligi IS NOT NULL GROUP BY islem_kimligi")
    db.execute("UPDATE hareket SET islem_kimligi=(SELECT yeni FROM txmap WHERE eski=hareket.islem_kimligi) WHERE islem_kimligi IS NOT NULL")
    db.execute("UPDATE hareket SET ham_kimlik='ornek:' || id")
    try:
        db.execute("DELETE FROM _olay WHERE tx NOT IN (SELECT eski FROM txmap)")        # kırpılanlar
        db.execute("UPDATE _olay SET tx=(SELECT yeni FROM txmap WHERE eski=_olay.tx)")   # zincir kimlikleri zaten küçük harf
    except sqlite3.OperationalError:
        pass
    from veri.kayit import maskele_metin
    for r in db.execute("SELECT id, parametreler FROM cagri").fetchall():
        db.execute("UPDATE cagri SET parametreler=? WHERE id=?", (MASKE.sub("…", maskele_metin(r["parametreler"])), r["id"]))
    db.execute("DELETE FROM fotograf")                                         # seviye yok
    db.execute("UPDATE kopru SET tutar='0', varlik_tutar='{}', aciklama=aciklama || ' (örnekte seviye yok)' "
               "WHERE kalem IN ('baslangic','bitis')")
    for r in db.execute("SELECT oturum, no, alanlar FROM olgu WHERE gizli=1").fetchall():
        alanlar = {k: "gizli" for k in json.loads(r["alanlar"])}
        db.execute("UPDATE olgu SET alanlar=? WHERE oturum=? AND no=?", (json.dumps(alanlar, ensure_ascii=False), r["oturum"], r["no"]))
    db.execute("CREATE TABLE IF NOT EXISTS _ornek (anahtar TEXT PRIMARY KEY, deger TEXT)")
    db.execute("DELETE FROM _ornek")
    db.execute("INSERT INTO _ornek VALUES ('surum', 'v3'), ('uretim', ?), ('not', ?)",
               (simdi(), "Sabah işinin gerçek çıktısı (beyaz liste); adres/işlem kimliği yer tutucu, seviye, bakiye ve gizli olgu değerleri yok."))
    db.commit()
    ozet = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("hareket", "adres", "olgu", "uyari", "kopru", "cagri", "fotograf")}
    fazla = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} - set(IZINLI_TABLOLAR)
    if fazla:
        raise RuntimeError(f"örnek veritabanında izinsiz tablo: {fazla}")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("VACUUM")
    db.close()
    return ozet


if __name__ == "__main__":
    import sys
    print(uret() if "--v1" in sys.argv else canlidan())
