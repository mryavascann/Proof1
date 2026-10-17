"""B5 kabul: bot karşılaştırıcı. Gerçek sonuç botun kaydından değil, bota giren ve hesaba dönen paradan."""
import unittest
from decimal import Decimal

from veri import ayar
from veri.bot import karsilastir
from veri.defter import ayristir, hareketlere, zincirle
from veri.testler.ortak import canli, canli_db
from veri.testler.test_b2_defter import BOT_16_EKIM

BOT_16 = {"algoId": "4014895767398817792", "instId": "USDT-TRY", "cTime": "1792155618042", "uTime": "1792155628377",
          "investment": "300", "totalPnl": "99.89115517772", "stopType": "2", "state": "stopped", "gridNum": "3"}


class Karsilastir(unittest.TestCase):
    def setUp(self):
        s = ayristir(BOT_16_EKIM, "alt", "account_get_bills")
        zincirle(s)
        self.h = hareketlere(s)

    def test_16_ekim_usdt_try_uyusmazlik(self):
        b = karsilastir(BOT_16, self.h, lambda cift, ts: Decimal("49.367"))
        self.assertEqual(b.kayit_pnl.quantize(Decimal("0.01")), Decimal("99.89"))
        self.assertAlmostEqual(float(b.gercek), -0.22, delta=0.01)
        self.assertEqual(b.durum, "uyusmazlik")
        self.assertTrue(b.iki_kez)
        self.assertEqual(b.donen, {"TRY": Decimal("199.66738130000"), "USDT": Decimal("2.027828940000000")})

    def test_donus_yoksa_bekleniyor(self):
        giris = [x for x in self.h if x["tur"] == "bota_giris"]
        b = karsilastir(BOT_16, giris, lambda cift, ts: Decimal("49.367"))
        self.assertEqual(b.durum, "bekleniyor")

    def test_fiyat_yoksa_bilinmiyor(self):
        b = karsilastir(BOT_16, self.h, lambda cift, ts: None)
        self.assertEqual(b.durum, "fiyat_yok")
        self.assertIsNone(b.gercek)

    def test_tutan_bot(self):
        bot = dict(BOT_16, totalPnl="-0.2248")
        b = karsilastir(bot, self.h, lambda cift, ts: Decimal("49.367"))
        self.assertEqual(b.durum, "tutuyor")
        self.assertFalse(b.iki_kez)


@canli
class CanliBot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from veri.atk import Atk
        from veri.bot import botlari_karsilastir
        db = canli_db()
        with Atk(ayar.okx_kimlik("alt"), db, "test-b5") as atk:
            cls.sonuc = {b.algo_id: b for b in botlari_karsilastir(atk, db)}

    def test_16_ekim_usdt_try(self):
        b = self.sonuc["4014895767398817792"]
        self.assertEqual(b.kayit_pnl.quantize(Decimal("0.01")), Decimal("99.89"))
        self.assertAlmostEqual(float(b.gercek), -0.22, delta=0.01)
        self.assertEqual(b.durum, "uyusmazlik")
        self.assertTrue(b.iki_kez)

    def test_06_ekim_xrp_try_tutuyor(self):
        b = self.sonuc["3985361557394993152"]
        self.assertEqual(b.yatirim, Decimal("150"))
        self.assertEqual(b.kayit_pnl.quantize(Decimal("0.01")), Decimal("-0.08"))
        self.assertAlmostEqual(float(b.gercek), -0.08, delta=0.01)
        self.assertEqual(b.durum, "tutuyor")

    def test_dokuz_botun_besi_tutuyor(self):
        # Devir metnindeki sayım 17 Ekim'den önce kurulan botlar içindir; sonrası prova/sahne botları.
        once = [b for b in self.sonuc.values() if b.olus_ms < 1792195200000]       # 2026-10-17T00:00:00Z
        durum = [b.durum for b in once]
        self.assertEqual(len(durum), 9)
        self.assertEqual(durum.count("tutuyor"), 5)
        self.assertEqual(durum.count("uyusmazlik"), 4)

    def test_bugunku_coinleri_tut_botlari_uyusmazlik(self):
        bugun = [b for b in self.sonuc.values() if b.olus_ms >= 1792195200000 and b.stop_type == "2" and b.inst == "USDT-TRY"]
        for b in bugun:
            self.assertEqual(b.durum, "uyusmazlik", b.algo_id)
            self.assertTrue(b.iki_kez, b.algo_id)


if __name__ == "__main__":
    unittest.main()
