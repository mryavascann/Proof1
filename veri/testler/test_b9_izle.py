"""B9 kabul: canlı bot izleyicisi, kayıtlı yanıt dizisiyle. Bot listeden düşünce dönen satırlar beklenir,
karşılaştırılır, olgu + acil uyarı yazılır ve Telegram'a gider; durdurmadan mesaja 15 saniyenin altı."""
import json
import unittest
from decimal import Decimal

from calistir.izle import Izleyici, donus_hareketleri
from veri import db as dbm
from veri.testler.test_b2_defter import BOT_16_EKIM
from veri.testler.test_b5_bot import BOT_16

ETKIN = dict(BOT_16, state="running", stopType="", uTime=BOT_16["cTime"])
OLUSTURMA = BOT_16_EKIM[:4]          # durdurmadan önceki satırlar
HEPSI = BOT_16_EKIM


class Saat:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def uyu(self, sn):
        self.t += sn


class SahteAtk:
    """Sırayla: bot etkin → bot düştü; defter önce dönüşsüz, sonra dönüşlü."""

    def __init__(self, saat):
        self.saat = saat
        self.etkin_cagri = 0
        self.defter_cagri = 0
        self.cagrilar = []
        self.araclar = ["grid_get_orders", "account_get_bills", "market_get_candles"]

    def cagir(self, arac, arg=None, alanlar=None):
        self.cagrilar.append((arac, dict(arg or {})))
        if arac == "grid_get_orders" and arg.get("status") == "active":
            self.etkin_cagri += 1
            return {"data": [ETKIN] if self.etkin_cagri < 3 else []}
        if arac == "grid_get_orders":
            return {"data": [BOT_16]}
        if arac == "account_get_bills":
            self.defter_cagri += 1
            return {"data": list(reversed(OLUSTURMA if self.defter_cagri < 2 else HEPSI))}
        if arac == "market_get_candles":
            dk = int(arg["after"]) - 60_000
            return {"data": [[str(dk), "49.361", "49.369", "49.361", "49.369"]]}
        raise AssertionError(arac)


class SahteTelegram:
    def __init__(self):
        self.mesajlar = []
        self.hazir = True

    def gonder_pano(self, metin, baglanti):
        self.mesajlar.append((metin, baglanti))
        return {"message_id": 1}


class Izle(unittest.TestCase):
    def setUp(self):
        self.saat = Saat()
        self.db = dbm.baglan(":memory:")
        self.atk = SahteAtk(self.saat)
        self.tg = SahteTelegram()
        self.iz = Izleyici(self.atk, self.db, self.tg, pano_url="http://localhost:3003", aralik=3,
                           uyku=self.saat.uyu, saat=self.saat)

    def test_durdurma_yakalanir_ve_telegram(self):
        sonuc = self.iz.calis(en_cok_tur=10)
        self.assertEqual(len(sonuc), 1)
        b, sure = sonuc[0]
        self.assertEqual(b.durum, "uyusmazlik")
        self.assertAlmostEqual(float(b.gercek), -0.22, delta=0.01)
        self.assertLess(sure, 15)
        metin, baglanti = self.tg.mesajlar[0]
        self.assertIn("99,89 TL kâr", metin)
        self.assertIn("22 kuruş zarar", metin)
        self.assertTrue(baglanti.endswith("oturum=canli-4014895767398817792"))
        u = self.db.execute("SELECT tur, onem, gonderildi FROM uyari WHERE oturum='canli-4014895767398817792'").fetchone()
        self.assertEqual((u["tur"], u["onem"]), ("bot_uyusmazlik", "acil"))
        self.assertIsNotNone(u["gonderildi"])

    def test_donus_bekleniyor(self):
        self.iz.calis(en_cok_tur=10)
        self.assertGreaterEqual(self.atk.defter_cagri, 2)       # ilk okumada dönüş yoktu, bekleyip yeniden okudu

    def test_yalniz_okuma_araclari(self):
        self.iz.calis(en_cok_tur=10)
        self.assertTrue(all(a in ("grid_get_orders", "account_get_bills", "market_get_candles") for a, _ in self.atk.cagrilar))

    def test_donus_hareketleri_isaretle(self):
        h = donus_hareketleri(HEPSI, BOT_16)
        self.assertEqual(sorted((x["tur"], x["varlik"]) for x in h),
                         [("bota_giris", "TRY"), ("bottan_donus", "TRY"), ("bottan_donus", "USDT")])
        self.assertEqual({x["tur"]: x["miktar"] for x in h if x["varlik"] == "TRY"},
                         {"bota_giris": "-300.00000000000", "bottan_donus": "199.66738130000"})


if __name__ == "__main__":
    unittest.main()
