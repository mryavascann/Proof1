"""İnceleme bulgu 1, 2, 8: canlı izleyici hatada çökmez, her durumda doğru cümleyi yazar, Telegram'ı bir kez yeniden dener."""
import unittest
from decimal import Decimal

import requests

from calistir.izle import Izleyici
from calistir.telegram import Telegram
from veri import db as dbm
from veri.atk import AtkHata
from veri.olgu import OlguYazici, kalip_cumle
from veri.testler.test_b2_defter import BOT_16_EKIM
from veri.testler.test_b5_bot import BOT_16
from veri.testler.test_b9_izle import ETKIN, OLUSTURMA, Saat, SahteAtk, SahteTelegram


class HataliAtk(SahteAtk):
    """Geçmiş kaydı iki kez 504, defter bir kez 504; sonra normal."""

    def __init__(self, saat, donus_gecikme_sn=0):
        super().__init__(saat)
        self.gecmis_hata = 2
        self.defter_hata = 1
        self.donus_gecikme = donus_gecikme_sn
        self.dusme_ani = None

    def cagir(self, arac, arg=None, alanlar=None):
        if arac == "grid_get_orders" and arg.get("status") == "history" and self.gecmis_hata:
            self.gecmis_hata -= 1
            raise AtkHata("504", "Retry later")
        if arac == "account_get_bills" and self.defter_hata:
            self.defter_hata -= 1
            raise AtkHata("504", "Retry later")
        sonuc = super().cagir(arac, arg, alanlar)
        if arac == "grid_get_orders" and arg.get("status") == "active" and not sonuc["data"] and self.dusme_ani is None:
            self.dusme_ani = self.saat()
        if arac == "account_get_bills" and self.donus_gecikme and self.saat() - (self.dusme_ani or 0) < self.donus_gecikme:
            return {"data": list(reversed(OLUSTURMA))}
        return sonuc


class OluAtk(SahteAtk):
    def __init__(self, saat):
        super().__init__(saat)
        self.olu = True
        self.yeniden = 0

    def canli_mi(self):
        return not self.olu

    def yeniden_baslat(self):
        self.yeniden += 1
        self.olu = False

    def cagir(self, arac, arg=None, alanlar=None):
        if self.olu:
            raise AtkHata("zaman_asimi", "tools/call")
        return super().cagir(arac, arg, alanlar)


class BirKezBasarisizTelegram(SahteTelegram):
    def __init__(self):
        super().__init__()
        self.deneme = 0

    def gonder_pano(self, metin, baglanti):
        self.deneme += 1
        if self.deneme == 1:
            return None
        return super().gonder_pano(metin, baglanti)


def _izleyici(atk, tg, saat, db=None):
    return Izleyici(atk, db or dbm.baglan(":memory:"), tg, "http://p", aralik=3, uyku=saat.uyu, saat=saat)


class Saglamlik(unittest.TestCase):
    def test_atk_hatasinda_cokmez_ve_mesaj_gider(self):
        saat = Saat()
        tg = SahteTelegram()
        sonuc = _izleyici(HataliAtk(saat), tg, saat).calis(en_cok_tur=10)
        self.assertEqual(len(sonuc), 1)
        self.assertEqual(sonuc[0][0].durum, "uyusmazlik")
        self.assertIn("22 kuruş zarar", tg.mesajlar[0][0])

    def test_olu_atk_yeniden_baslatilir(self):
        saat = Saat()
        atk = OluAtk(saat)
        iz = _izleyici(atk, SahteTelegram(), saat)
        self.assertIsNone(iz.etkinler())
        self.assertEqual(atk.yeniden, 1)
        self.assertIsNotNone(iz.etkinler())

    def test_donus_gec_gelirse_60_sn_bekler(self):
        saat = Saat()
        tg = SahteTelegram()
        sonuc = _izleyici(HataliAtk(saat, donus_gecikme_sn=25), tg, saat).calis(en_cok_tur=10)
        self.assertEqual(sonuc[0][0].durum, "uyusmazlik")

    def test_telegram_bir_kez_yeniden_denenir(self):
        saat = Saat()
        tg = BirKezBasarisizTelegram()
        db = dbm.baglan(":memory:")
        _izleyici(SahteAtk(saat), tg, saat, db).calis(en_cok_tur=10)
        self.assertEqual(tg.deneme, 2)
        self.assertIsNotNone(db.execute("SELECT gonderildi FROM uyari").fetchone()[0])


class Cumleler(unittest.TestCase):
    def _cumle(self, tur, alanlar):
        db = dbm.baglan(":memory:")
        OlguYazici(db, "c").ekle(tur, alanlar)
        return kalip_cumle(db, "c")[0]

    def test_tutan_bot(self):
        c = self._cumle("bot_tutuyor", {"bot": "XRP/TRY spot grid", "kayit_sozle": "8 kuruş zarar", "gercek_sozle": "8 kuruş zarar"})
        self.assertIn("kayıt tutuyor", c)
        self.assertIn("8 kuruş zarar", c)

    def test_bekleniyor_ve_fiyat_yok(self):
        self.assertIn("henüz görünmüyor", self._cumle("bot_bekleniyor", {"bot": "USDT/TRY spot grid", "kayit_sozle": "1 TL kâr"}))
        self.assertIn("hesaplayamadım", self._cumle("bot_fiyat_yok", {"bot": "ABC/TRY spot grid", "kayit_sozle": "1 TL kâr"}))
        self.assertNotIn("yeni bir şey görmedi", self._cumle("bot_tutuyor", {"bot": "X", "kayit_sozle": "a", "gercek_sozle": "a"}))


class TelegramCiftGonderimYok(unittest.TestCase):
    def test_zaman_asiminda_duz_metne_gecilmez(self):
        class ZamanAsimiHttp:
            def __init__(self):
                self.n = 0

            def post(self, *a, **k):
                self.n += 1
                raise requests.Timeout()
        http = ZamanAsimiHttp()
        self.assertIsNone(Telegram("1:A", "2", http=http).gonder_pano("x", "http://p"))
        self.assertEqual(http.n, 2)            # aynı HTML mesajı bir kez yeniden; düz metin yedeği yalnız 400'de


if __name__ == "__main__":
    unittest.main()
