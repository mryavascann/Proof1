"""B2.5 kabul: örnek veritabanı. Gerçek adres/işlem kimliği yok, seviye yok; 11 Ekim AVAX, MOCA ve 16 Ekim botu var."""
import json
import re
import sqlite3
import unittest
from decimal import Decimal

from veri.ornek import GUN11, HEDEF, SABAH

GERCEK = re.compile(r"0x[0-9a-fA-F]{40}|\bT[1-9A-HJ-NP-Za-km-z]{33}\b|\b[0-9a-fA-F]{64}\b|0x[0-9a-fA-F]{2,6}…[0-9a-fA-F]{4}")


@unittest.skipUnless(HEDEF.exists(), "örnek veritabanı yok: python -m veri.ornek")
class Ornek(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(f"file:{HEDEF}?mode=ro", uri=True)
        cls.db.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_hicbir_alanda_gercek_adres_yok(self):
        for (tablo,) in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for satir in self.db.execute(f"SELECT * FROM {tablo}"):
                for deger in satir:
                    if isinstance(deger, str):
                        self.assertIsNone(GERCEK.search(deger), f"{tablo}: {deger[:40]}")

    def test_adresler_yer_tutucu(self):
        for r in self.db.execute("SELECT adres, etiket, kisa, gezgin_url FROM adres"):
            self.assertRegex(r["adres"], r"^(BENIM|ADRES|KARSI)_\w+$")
            self.assertEqual((r["adres"], r["kisa"]), (r["etiket"], r["etiket"]))
            self.assertIsNone(r["gezgin_url"])

    def test_seviye_yok(self):
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fotograf").fetchone()[0], 0)
        for r in self.db.execute("SELECT tutar FROM kopru WHERE kalem IN ('baslangic','bitis')"):
            self.assertEqual(r[0], "0")
        for (alanlar,) in self.db.execute("SELECT alanlar FROM olgu WHERE gizli=1"):
            self.assertEqual(set(json.loads(alanlar).values()), {"gizli"})
        tablolar = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(tablolar & {"_defter", "_zincir_ham", "_tx_gonderen"})

    def _avax_adresi(self):
        return self.db.execute("SELECT karsi FROM hareket WHERE tur='cekim' AND varlik='AVAX'").fetchone()[0]

    def test_11_ekim_avax(self):
        et = self._avax_adresi()
        h = self.db.execute("SELECT h.zaman, h.tur, h.varlik, h.miktar FROM hareket h JOIN adres a ON a.id=h.adres_id "
                            "WHERE a.etiket=? AND h.zaman LIKE '2026-10-11%' ORDER BY h.zaman", (et,)).fetchall()
        gun = sum((Decimal(r["miktar"]) for r in h if r["varlik"] == "AVAX"), Decimal(0))
        self.assertEqual(gun.quantize(Decimal("0.000001")), Decimal("0.780825"))
        self.assertIn("taninmadi", [r["tur"] for r in h])
        cekim = self.db.execute("SELECT miktar FROM hareket WHERE tur='cekim' AND varlik='AVAX'").fetchone()
        self.assertEqual(cekim[0], "-0.98280221")
        olgular = [json.loads(r[0]) for r in self.db.execute("SELECT alanlar FROM olgu WHERE tur='taninmadi'")]
        self.assertIn("0,000212 AVAX", [o.get("miktar") for o in olgular])

    def test_11_ekim_koprusu(self):
        k = {(a["kapsam"], a["kalem"]): a for a in (json.loads(r[0]) for r in self.db.execute(
            "SELECT alanlar FROM olgu WHERE oturum=? AND tur='kopru'", (GUN11,)))}
        self.assertIn("-0,9828 AVAX", k[("borsa", "aktarim")]["coin"])
        self.assertIn("-0,01719 AVAX", k[("servet", "ucret")]["coin"])
        self.assertIn("0,000212 AVAX", k[("servet", "aciklanamayan")]["coin"])

    def test_moca(self):
        aid = self.db.execute("SELECT adres_id FROM hareket WHERE varlik='PIEVERSE' AND tur='takas'").fetchone()[0]
        r = self.db.execute("SELECT miktar FROM hareket WHERE varlik='MOCA' AND adres_id=?", (aid,)).fetchall()
        self.assertEqual(sum(Decimal(x[0]) for x in r).quantize(Decimal(1)), Decimal(5653))
        o = [json.loads(x[0]) for x in self.db.execute("SELECT alanlar FROM olgu WHERE tur='takas'")]
        self.assertIn(("46,15 PIEVERSE", "1.587 MOCA"), [(x.get("verilen"), x.get("alinan")) for x in o])

    def test_16_ekim_botu(self):
        o = [json.loads(r[0]) for r in self.db.execute(
            "SELECT alanlar FROM olgu WHERE oturum=? AND tur='bot_uyusmazlik'", (SABAH,))]
        self.assertEqual(len(o), 1)
        self.assertEqual((o[0]["kayit_sonuc"], o[0]["gercek_sonuc"]), ("+99,89 TL", "-0,22 TL"))
        self.assertGreaterEqual(self.db.execute(
            "SELECT COUNT(*) FROM uyari WHERE oturum=? AND tur='bot_uyusmazlik' AND onem='acil'", (SABAH,)).fetchone()[0], 1)
        turler = {r[0] for r in self.db.execute("SELECT tur FROM hareket WHERE hesap='alt'")}
        self.assertTrue({"bota_giris", "bottan_donus"} <= turler)

    def test_cagri_kaydi_salt_okunur(self):
        r = self.db.execute("SELECT COUNT(*), COUNT(DISTINCT kaynak) FROM cagri WHERE kaynak != 'Telegram'").fetchone()
        self.assertGreater(r[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cagri WHERE kaynak != 'Telegram' AND salt_okunur=0").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
