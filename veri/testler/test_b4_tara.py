"""B4 kabul (tarama): her adres okunabilen her ağda okunur; okunamayan çekim ağı sessizce kaybolmaz."""
import unittest
from decimal import Decimal

from veri import db as dbm
from veri.adres import AdresKarti, yaz as adres_yaz
from veri.aglar import AGLAR
from veri.borsa import Kayit
from veri.defter import cekim_hareketleri, yaz as hyaz
from veri.testler.test_b4_zincir import A, B, GUN, OKX
from veri.zincir.evm import Bacaklar, bacaklar
from veri.zincir.okuyucu import Okunamadi
from veri.zincir.tara import ag_durumlari, tara


class SahteOkuyucu:
    def __init__(self):
        self.okunan = []

    def okuyucular(self, ag):
        return [] if ag.anahtar == "arbitrum" else ["sahte"]

    def oku(self, adres, ag, onbellek=True):
        self.okunan.append(ag.anahtar)
        if ag.anahtar == "avalanche":
            b = bacaklar(adres, ag, GUN)
        else:
            b = Bacaklar()
        b.kaynak = "sahte"
        return b


class Tara(unittest.TestCase):
    def setUp(self):
        self.db = dbm.baglan(":memory:")
        self.cek = [Kayit("cekim", "w1", 1791722000000, "AVAX", "AVAX-Avalanche C-Chain", Decimal("0.98280221"),
                          Decimal("0.015"), "AVAX", A, "0xc1", "2"),
                    Kayit("cekim", "w2", 1791000000000, "USDT", "USDT-Arbitrum One", Decimal("10"), Decimal("0.1"),
                          "USDT", A, "0xa1", "2")]
        hyaz(self.db, cekim_hareketleri(self.cek))
        kart = AdresKarti(A, "avalanche", ["arbitrum", "avalanche"], 3, "benim", "kanıt", 2, 1, 2, 1, "BENIM_1", ["w1", "w2"])
        adres_yaz(self.db, [kart], self.cek)
        self.ok = SahteOkuyucu()
        self.sonuc = tara(self.db, self.ok, self.cek, [], borsa_adresleri={OKX})

    def test_evm_adresi_her_agda_okunur(self):
        self.assertIn("ethereum", self.ok.okunan)
        self.assertIn("chiliz", self.ok.okunan)
        self.assertNotIn("arbitrum", self.ok.okunan)

    def test_okunamayan_cekim_agi_gorunur(self):
        d = {(x["etiket"], x["ag"]): x["durum"] for x in ag_durumlari(self.db)}
        self.assertEqual(d[("BENIM_1", "arbitrum")], "okunamadi")
        self.assertEqual(d[("BENIM_1", "avalanche")], "okundu")
        self.assertEqual(d.get(("BENIM_1", "ethereum")), "bos")

    def test_hareketler_ve_karsi_adres(self):
        h = self.db.execute("SELECT tur, varlik, miktar, karsi FROM hareket WHERE hesap='cuzdan'").fetchall()
        self.assertIn(("giris", "AVAX", "0.98280221", "ana"), [tuple(r) for r in h])
        karsi = {r["karsi"] for r in h if r["tur"] == "gonderim"}
        self.assertEqual(karsi, {"KARSI_1"})
        r = self.db.execute("SELECT tahmin, cekim_sayisi, kanit FROM adres WHERE etiket='KARSI_1'").fetchone()
        self.assertEqual((r["tahmin"], r["cekim_sayisi"]), ("belli_degil", 0))
        self.assertIn("BENIM_1", r["kanit"])
        toplam = sum(Decimal(r["miktar"]) for r in h if r["varlik"] == "AVAX")
        self.assertEqual(toplam.quantize(Decimal("0.000001")), Decimal("0.780825"))

    def test_tekrar_taramada_cift_satir_yok(self):
        once = self.db.execute("SELECT COUNT(*) FROM hareket").fetchone()[0]
        tara(self.db, self.ok, self.cek, [], borsa_adresleri={OKX})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM hareket").fetchone()[0], once)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM adres WHERE etiket LIKE 'KARSI_%'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
