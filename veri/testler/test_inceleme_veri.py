"""İnceleme bulgu 5, 6, 7, 9, 10: fiyat önbelleği, bot eşiği, KARSI adresleri, gizli denetim, EVM/Tron dışı ağlar."""
import unittest
from decimal import Decimal

from calistir.sabah import _gizli_sizdi_mi
from veri import db as dbm
from veri.adres import AdresKarti, yaz as adres_yaz
from veri.atk import AtkHata
from veri.borsa import Kayit
from veri.fiyat import Fiyatci
from veri.olgu import OlguYazici


class GeciciHataliAtk:
    def __init__(self):
        self.n = 0

    def cagir(self, arac, arg=None, alanlar=None):
        self.n += 1
        if self.n == 1:
            raise AtkHata("504", "Retry later")
        if arac == "market_get_instruments":
            return {"data": [{"instId": "AVAX-USDT"}]}
        dk = int(arg["after"]) - (60_000 if arg["bar"] == "1m" else 3_600_000)
        return {"data": [[str(dk), "10", "11", "9", "10.5"]]}


class FiyatOnbellegi(unittest.TestCase):
    def test_gecici_hata_kalici_yok_yapmaz(self):
        f = Fiyatci(GeciciHataliAtk(), dbm.baglan(":memory:"))
        ts = 1792155600000
        self.assertIsNone(f.mum("AVAX-USDT", ts))          # ilk çağrı 504
        self.assertEqual(f.mum("AVAX-USDT", ts), Decimal("10.5"))

    def test_liste_hatasi_kalici_degil(self):
        f = Fiyatci(GeciciHataliAtk(), dbm.baglan(":memory:"))
        self.assertFalse(f.listede("AVAX"))                 # ilk çağrı 504
        self.assertTrue(f.listede("AVAX"))

    def test_aralik_hatasi_kalici_degil(self):
        f = Fiyatci(GeciciHataliAtk(), dbm.baglan(":memory:"))
        self.assertIsNone(f.aralik("USDT-TRY", 1792155628377))
        self.assertEqual(f.aralik("USDT-TRY", 1792155628377), (Decimal(9), Decimal(11)))


class KarsiAdresleri(unittest.TestCase):
    def test_sabah_yeniden_yazinca_karsi_ve_kimlikler_kalir(self):
        db = dbm.baglan(":memory:")
        a = "0x" + "aa" * 20
        cek = [Kayit("cekim", "w1", 1, "AVAX", "AVAX-Avalanche C-Chain", Decimal(1), Decimal(0), "AVAX", a, "0xc1", "2")]
        kart = lambda: [AdresKarti(a, "avalanche", ["avalanche"], 3, "benim", "k", 1, 1, 1, 1, "BENIM_1", ["w1"])]
        adres_yaz(db, kart(), cek)
        db.execute("INSERT INTO adres (adres, etiket, kisa, ag, katman, tahmin, kanit, cekim_sayisi) "
                   "VALUES ('0x" + "bb" * 20 + "', 'KARSI_1', 'k', 'avalanche', 3, 'belli_degil', 'k', 0)")
        once = {r["etiket"]: r["id"] for r in db.execute("SELECT id, etiket FROM adres")}
        adres_yaz(db, kart(), cek)
        sonra = {r["etiket"]: r["id"] for r in db.execute("SELECT id, etiket FROM adres")}
        self.assertEqual(once, sonra)


class GizliDenetim(unittest.TestCase):
    def _db(self):
        db = dbm.baglan(":memory:")
        y = OlguYazici(db, "s")
        y.ekle("kalan_ozet", {"adres_sayisi": "10", "dolar": "1.234,56 $"}, gizli=True)
        y.ekle("kopru", {"kalem": "baslangic", "coin": "0,7808 AVAX"}, gizli=True)
        return db

    def test_bicim_farkina_ragmen_yakalar(self):
        db = self._db()
        self.assertTrue(_gizli_sizdi_mi(db, "s", "Adreslerinde 1.234 $ duruyor."))
        self.assertTrue(_gizli_sizdi_mi(db, "s", "Cüzdanda 0,78 AVAX var."))
        self.assertTrue(_gizli_sizdi_mi(db, "s", "10 adreste para var."))

    def test_ilgisiz_sayilar_gecer(self):
        db = self._db()
        self.assertFalse(_gizli_sizdi_mi(db, "s", "Kayıt 99,89 TL kâr diyor; gerçekte 22 kuruş zarar."))
        self.assertFalse(_gizli_sizdi_mi(db, "s", "1 botun sonucu 3 kez kontrol edildi."))


class BotEsigi(unittest.TestCase):
    def test_usdt_koteli_botta_esik_tl_karsiligi(self):
        from veri.bot import esik
        self.assertEqual(esik("TRY"), Decimal(1))
        self.assertLess(esik("USDT"), Decimal("0.1"))


class EvmTronDisiAglar(unittest.TestCase):
    def test_solana_cekimi_okunamayan_olarak_gorunur(self):
        from veri.testler.test_b4_tara import SahteOkuyucu
        from veri.zincir.tara import ag_durumlari, tara
        db = dbm.baglan(":memory:")
        sol = "So1ana" + "1" * 38
        cek = [Kayit("cekim", "w1", 1, "USDC", "USDC-Solana", Decimal(5), Decimal(0), "USDC", sol, "tx", "2")]
        adres_yaz(db, [AdresKarti(sol, "solana", ["solana"], 1, "belli_degil", "k", 1, 1, 1, 0, "ADRES_1", ["w1"])], cek)
        ok = SahteOkuyucu()
        ok.okuyucular = lambda ag: [] if ag.anahtar == "solana" else ["sahte"]
        tara(db, ok, cek, [])
        self.assertNotIn("tron", ok.okunan)
        d = {(x["etiket"], x["ag"]): x["durum"] for x in ag_durumlari(db)}
        self.assertEqual(d[("ADRES_1", "solana")], "okunamadi")


if __name__ == "__main__":
    unittest.main()
