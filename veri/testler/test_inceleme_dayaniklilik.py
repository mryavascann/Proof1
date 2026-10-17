"""İnceleme bulgu 11, 12: sohbet seçimi, ağ hatasında token sızmaz; tek adres/adım hatası sabah işini yarıda kesmez."""
import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal

import requests

from calistir.sabah import adim
from calistir.telegram import Telegram
from calistir.telegram_kimlik import sohbet_sec
from veri import db as dbm
from veri.adres import AdresKarti, yaz as adres_yaz
from veri.borsa import Kayit
from veri.testler.test_b4_tara import SahteOkuyucu
from veri.zincir.tara import ag_durumlari, tara


class SohbetSecimi(unittest.TestCase):
    def test_tek_sohbet_secilir(self):
        g = [{"message": {"chat": {"id": 42, "first_name": "Buğra", "type": "private"}}}]
        self.assertEqual(sohbet_sec(g)[0], "42")

    def test_birden_cok_sohbette_secilmez(self):
        g = [{"message": {"chat": {"id": 42, "first_name": "Buğra"}}}, {"message": {"chat": {"id": 77, "first_name": "Yabancı"}}}]
        secilen, liste = sohbet_sec(g)
        self.assertIsNone(secilen)
        self.assertEqual(len(liste), 2)

    def test_ag_hatasinda_token_basilmaz(self):
        class Kopuk:
            def get(self, url, timeout=None):
                raise requests.ConnectionError(f"bağlanamadı: {url}")
        t = Telegram("123:GIZLITOKEN", "", http=Kopuk(), db=dbm.baglan(":memory:"))
        cikti = io.StringIO()
        with redirect_stdout(cikti):
            self.assertEqual(t.guncellemeler(), [])
        self.assertNotIn("GIZLITOKEN", cikti.getvalue())
        self.assertNotIn("GIZLITOKEN", t.db.execute("SELECT parametreler || IFNULL(kod,'') FROM cagri").fetchone()[0])


class TekHataYarimKesmez(unittest.TestCase):
    def test_bir_agdaki_beklenmeyen_hata(self):
        class BozukOkuyucu(SahteOkuyucu):
            def oku(self, adres, ag, onbellek=True):
                if ag.anahtar == "ethereum":
                    raise TypeError("beklenmeyen cevap")
                return super().oku(adres, ag)
        db = dbm.baglan(":memory:")
        a = "0x" + "aa" * 20
        cek = [Kayit("cekim", "w1", 1, "AVAX", "AVAX-Avalanche C-Chain", Decimal(1), Decimal(0), "AVAX", a, "0xc1", "2")]
        adres_yaz(db, [AdresKarti(a, "avalanche", ["avalanche"], 3, "benim", "k", 1, 1, 1, 1, "BENIM_1", ["w1"])], cek)
        sonuc = tara(db, BozukOkuyucu(), cek, [])
        d = {x["ag"]: x["durum"] for x in ag_durumlari(db)}
        self.assertEqual(d["ethereum"], "okunamadi")
        self.assertEqual(d["avalanche"], "okundu")
        self.assertIn(("BENIM_1", "ethereum"), sonuc.okunamayan)

    def test_adim_hatayi_yakalar_ve_yazar(self):
        gunluk = []
        self.assertIsNone(adim(gunluk, "köprü", lambda: 1 / 0))
        self.assertEqual(adim(gunluk, "olgu", lambda: 5), 5)
        self.assertEqual(gunluk, ["köprü tamamlanamadı (ZeroDivisionError)"])


if __name__ == "__main__":
    unittest.main()
