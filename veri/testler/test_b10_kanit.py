"""B10 kabul: OKX kanıt paneli özeti (araç, süre, alanlar, salt okunur) ve kök README."""
import re
import unittest

from veri import ayar, db as dbm
from veri.kanit import kanit_ozeti
from veri.kayit import cagri_kaydi


class Kanit(unittest.TestCase):
    def test_ozet(self):
        db = dbm.baglan(":memory:")
        for sure_alan in (["amt", "to"], ["amt", "txId"]):
            with cagri_kaydi(db, "OKX TR", "GET /api/v5/asset/withdrawal-history", {"limit": 100}, "s") as c:
                c.alanlar, c.satir = sure_alan, 87
        try:
            with cagri_kaydi(db, "ATK", "account_get_bills", {}, "s") as c:
                c.kod = "504"
                raise IOError("Retry later")
        except IOError:
            pass
        o = {(x["kaynak"], x["ad"]): x for x in kanit_ozeti(db, "s")}
        w = o[("OKX TR", "GET /api/v5/asset/withdrawal-history")]
        self.assertEqual((w["cagri"], w["hata"], w["salt_okunur"]), (2, 0, True))
        self.assertEqual(w["alanlar"], ["amt", "to", "txId"])
        self.assertIsInstance(w["ort_ms"], int)
        b = o[("ATK", "account_get_bills")]
        self.assertEqual((b["hata"], b["son_hata"]), (1, "504"))

    def test_view_var(self):
        db = dbm.baglan(":memory:")
        kanit_ozeti(db)
        self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='cagri_ozet'").fetchone())


class Readme(unittest.TestCase):
    def setUp(self):
        self.metin = (ayar.KOK / "README.md").read_text(encoding="utf-8")

    def test_bolumler(self):
        for b in ("Kurulum", "Çalıştırma", "Örnek veri", "Canlı veri", "OKX araçları", "Avalanche", "Salt okuma"):
            self.assertIn(b, self.metin)

    def test_kullanilan_atk_araclari_listede(self):
        for arac in ("account_get_bills", "account_get_bills_archive", "grid_get_orders", "grid_get_order_details",
                     "spot_get_fills", "account_get_balance", "market_get_candles", "trade_get_history"):
            self.assertIn(arac, self.metin)

    def test_sir_ve_adres_yok(self):
        for satir in self.metin.splitlines():
            for adres in re.findall(r"0x[0-9a-fA-F]{40}", satir):
                self.assertTrue(adres.lower().startswith("0x8004"), f"README'de kişisel adres: {adres[:8]}…")
        self.assertNotRegex(self.metin, r"(?i)(api_key|secret|passphrase|token)\s*=\s*\S{6,}")


if __name__ == "__main__":
    unittest.main()
