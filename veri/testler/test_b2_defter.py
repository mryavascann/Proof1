"""B2 kabul: defter. Önceki bakiye + değişim = yeni bakiye (hesap ve bot zincirleri ayrı); bot türleri doğru."""
import unittest
from decimal import Decimal

from veri import ayar, db as dbm
from veri.defter import ayristir, hareketlere, yaz, zincirle
from veri.testler.ortak import canli, canli_db

# 16 Ekim 16:00 USDT/TRY bot denemesinin alt hesap defteri (gerçek satırlar, kimlikler kısaltıldı).
BOT_16_EKIM = [
    {"billId": "b1", "ts": "1792155618044", "type": "12", "subType": "202", "ccy": "TRY", "balChg": "-300.00000000000", "bal": "154.05489915222", "fee": "", "sz": "-300"},
    {"billId": "b2", "ts": "1792155618044", "type": "12", "subType": "200", "ccy": "TRY", "balChg": "300", "bal": "300", "fee": "", "sz": "300"},
    {"billId": "b3", "ts": "1792155618046", "type": "2", "subType": "1", "ccy": "USDT", "balChg": "2.02782894", "bal": "2.02782894", "fee": "-0.00447106", "sz": "2.0323", "instId": "USDT-TRY", "ordId": "o1"},
    {"billId": "b4", "ts": "1792155618046", "type": "2", "subType": "2", "ccy": "TRY", "balChg": "-100.3326187", "bal": "199.6673813", "fee": "0", "sz": "100.3326187", "instId": "USDT-TRY", "ordId": "o1"},
    {"billId": "b5", "ts": "1792155628376", "type": "12", "subType": "200", "ccy": "TRY", "balChg": "199.66738130000", "bal": "353.72228045222", "fee": "", "sz": "199.6673813"},
    {"billId": "b6", "ts": "1792155628376", "type": "12", "subType": "202", "ccy": "TRY", "balChg": "-199.6673813", "bal": "0", "fee": "", "sz": "-199.6673813"},
    {"billId": "b7", "ts": "1792155628376", "type": "12", "subType": "200", "ccy": "USDT", "balChg": "2.027828940000000", "bal": "5.381161091449046", "fee": "", "sz": "2.02782894"},
    {"billId": "b8", "ts": "1792155628376", "type": "12", "subType": "202", "ccy": "USDT", "balChg": "-2.02782894", "bal": "0", "fee": "", "sz": "-2.02782894"},
]


class Zincir(unittest.TestCase):
    def setUp(self):
        self.satirlar = ayristir(BOT_16_EKIM, "alt", "account_get_bills")

    def test_fark_sifir_ve_defterler_ayrilir(self):
        sonuc = zincirle(self.satirlar)
        self.assertEqual(sonuc.farklar, [])
        defter = {s.kimlik: s.defter for s in self.satirlar}
        self.assertEqual(defter, {"b1": "hesap", "b2": "bot", "b3": "bot", "b4": "bot",
                                  "b5": "hesap", "b6": "bot", "b7": "hesap", "b8": "bot"})

    def test_bozuk_bakiye_yakalanir(self):
        bozuk = [dict(r) for r in BOT_16_EKIM]
        bozuk[4]["bal"] = "353.72228045223"   # bir kuruşun yüzde biri
        sonuc = zincirle(ayristir(bozuk, "alt", "account_get_bills"))
        self.assertEqual(len(sonuc.farklar), 1)
        self.assertEqual(sonuc.farklar[0].ccy, "TRY")

    def test_hareket_turleri(self):
        zincirle(self.satirlar)
        h = hareketlere(self.satirlar)
        ozet = sorted((x["tur"], x["varlik"], x["miktar"]) for x in h)
        self.assertEqual(ozet, sorted([
            ("bota_giris", "TRY", "-300.00000000000"),
            ("bottan_donus", "TRY", "199.66738130000"),
            ("bottan_donus", "USDT", "2.027828940000000"),
        ]))
        self.assertTrue(all(x["hesap"] == "alt" and x["kaynak"] == "borsa" for x in h))

    def test_islem_ucreti_ayri_satir(self):
        satir = {"billId": "t1", "ts": "1", "type": "2", "subType": "1", "ccy": "USDT", "balChg": "2.02782894",
                 "bal": "2.02782894", "fee": "-0.00447106", "sz": "2.0323", "instId": "USDT-TRY"}
        s = ayristir([satir], "alt", "account_get_bills")
        zincirle(s)
        h = {x["tur"]: Decimal(x["miktar"]) for x in hareketlere(s)}
        self.assertEqual(h, {"alim": Decimal("2.0323"), "ucret": Decimal("-0.00447106")})

    def test_bozuk_satir_okunamadi(self):
        s = ayristir([{"billId": "x", "ts": "abc", "ccy": "TRY", "balChg": "1", "bal": "1"}], "alt", "account_get_bills")
        self.assertEqual(s, [])

    def test_yaz_tekrar_yazmaz(self):
        db = dbm.baglan(":memory:")
        zincirle(self.satirlar)
        h = hareketlere(self.satirlar)
        yaz(db, h)
        yaz(db, h)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM hareket").fetchone()[0], 3)


@canli
class CanliDefter(unittest.TestCase):
    def test_alt_hesap_7_gun_fark_sifir(self):
        from veri.atk import Atk, satirlar
        db = canli_db()
        with Atk(ayar.okx_kimlik("alt"), db, "test-b2") as atk:
            ham = satirlar(atk.cagir("account_get_bills", {"limit": 100}))
        self.assertGreater(len(ham), 0)
        s = ayristir(ham, "alt", "account_get_bills")
        sonuc = zincirle(s)
        self.assertEqual(sonuc.farklar, [], [f"{f.ccy} {f.kimlik}" for f in sonuc.farklar])
        turler = {x["tur"] for x in hareketlere(s)}
        self.assertTrue({"bota_giris", "bottan_donus"} <= turler, turler)

    def test_arsiv_3_ay_fark_sifir(self):
        from veri.atk import Atk
        from veri.defter import alt_defteri
        db = canli_db()
        with Atk(ayar.okx_kimlik("alt"), db, "test-b2") as atk:
            s = alt_defteri(atk)
        sonuc = zincirle(s)
        self.assertEqual(sonuc.farklar, [], [f"{f.ccy} {f.kimlik}" for f in sonuc.farklar])


if __name__ == "__main__":
    unittest.main()
