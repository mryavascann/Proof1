"""M3 kabul: kalıp cümleler denetimden geçer; bütçe hesabı, model seçimi ve 35 TL tavanı."""
import json
import sqlite3
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from anlatim import butce, kalip
from anlatim.denetim import Olgu, denetle

ORNEK_DB = Path(__file__).resolve().parents[2] / "ortak" / "ornek" / "proof1_ornek.db"


def ornek_olgular():
    with closing(sqlite3.connect(ORNEK_DB)) as db:
        return [Olgu(no, tur, json.loads(alanlar), bool(gizli)) for no, tur, alanlar, gizli in
                db.execute("SELECT no, tur, alanlar, gizli FROM olgu ORDER BY oturum, no")]


class Kaliplar(unittest.TestCase):
    def test_her_ornek_olgunun_kalibi_denetimden_gecer(self):
        sayilan = 0
        for o in ornek_olgular():
            metin = kalip.olgu_cumlesi(o)
            if o.gizli:
                self.assertIsNone(metin, o.no)
                continue
            if metin is None:
                continue
            s = denetle({"metin": metin, "olgular": [o.no]}, [o])
            self.assertTrue(s.gecti, f"{o.no} {o.tur}: {metin} → {s.neden}")
            sayilan += 1
        self.assertGreaterEqual(sayilan, 10)

    def test_moca_kalibi_ve_fiyatsiz_token(self):
        o = Olgu("o9", "moca_takas", {"tarih": "9 Nisan 2026", "verilen": "46,15 PIEVERSE", "alinan": "1.587 MOCA",
                                      "ag_ucreti": "0,000129 ETH", "verilen_dolar": "bilinmiyor"})
        metin = kalip.olgu_cumlesi(o)
        self.assertIn("46,15 PIEVERSE verip 1.587 MOCA aldın", metin)
        self.assertIn("ağ ücreti 0,000129 ETH", metin)
        self.assertIn("dolar fiyatı yok", metin)
        self.assertNotIn("$", metin)

    def test_taninmayan_giris(self):
        o = Olgu("o3", "taninmadi", {"tarih": "11 Ekim 2026 15:53", "miktar": "0,000212 AVAX"})
        self.assertIn("kaynağını tanıyamadım", kalip.olgu_cumlesi(o))


class Butce(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")

    def tearDown(self):
        self.db.close()

    def test_tutar_resmi_fiyatlarla(self):
        kullanim = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0}
        self.assertEqual(butce.tutar_usd("claude-sonnet-5-5", kullanim), Decimal("2"))
        self.assertEqual(butce.tutar_usd("claude-haiku-5-5", kullanim), Decimal("0.10"))
        kullanim = {"input_tokens": 0, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
                    "cache_creation_input_tokens": 0}
        self.assertEqual(butce.tutar_usd("claude-sonnet-5-5", kullanim), Decimal("10.20"))

    def test_model_secimi_ve_tavan(self):
        sec = lambda: butce.model_sec(self.db, "bugra", "2026-10", girdi_tahmini=4000, azami_cikti=2000)
        self.assertEqual(sec(), "claude-sonnet-5-5")
        butce.yaz(self.db, "bugra", "2026-10", "claude-sonnet-5-5", 0, 0, Decimal("29"), "ok")
        self.assertEqual(sec(), "claude-haiku-5-5")
        butce.yaz(self.db, "bugra", "2026-10", "claude-haiku-5-5", 0, 0, Decimal("5.995"), "ok")
        self.assertEqual(sec(), "kalip")

    def test_baska_ay_sayilmaz(self):
        butce.yaz(self.db, "bugra", "2026-09", "claude-sonnet-5-5", 0, 0, Decimal("35"), "ok")
        self.assertEqual(butce.model_sec(self.db, "bugra", "2026-10", 4000, 2000), "claude-sonnet-5-5")

    def test_sozlesme_sutunlari(self):
        butce.yaz(self.db, "bugra", "2026-10", "kalip", 0, 0, Decimal("0"), "tavan")
        sutunlar = [r[1] for r in self.db.execute("PRAGMA table_info(butce)")]
        self.assertEqual(sutunlar, ["kullanici", "ay", "model", "girdi_parca", "cikti_parca", "tutar_tl",
                                    "tavan_tl", "durum"])
        self.assertEqual(self.db.execute("select tavan_tl from butce").fetchone()[0], "35")


if __name__ == "__main__":
    unittest.main()
