"""B2.5 kabul: örnek veritabanı. Gerçek adres/işlem kimliği yok, seviye yok; 11 Ekim AVAX, MOCA ve 16 Ekim botu var."""
import json
import re
import sqlite3
import unittest

from veri.ornek import GUN11, HEDEF, SABAH

GERCEK = re.compile(r"0x[0-9a-fA-F]{40}|\bT[1-9A-HJ-NP-Za-km-z]{33}\b|\b[0-9a-fA-F]{64}\b")


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
                        self.assertIsNone(GERCEK.search(deger), f"{tablo}: {deger[:30]}")

    def test_adresler_yer_tutucu(self):
        for r in self.db.execute("SELECT adres, etiket, kisa FROM adres"):
            self.assertRegex(r["adres"], r"^(BENIM|ADRES)_\w+$")
            self.assertEqual(r["adres"], r["etiket"])

    def test_seviye_yok(self):
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fotograf").fetchone()[0], 0)

    def test_11_ekim_avax(self):
        h = self.db.execute("SELECT tur, varlik, miktar FROM hareket h JOIN adres a ON a.id=h.adres_id "
                            "WHERE a.etiket='BENIM_1' ORDER BY h.zaman").fetchall()
        toplam = sum(float(r["miktar"]) for r in h if r["varlik"] == "AVAX")
        self.assertAlmostEqual(toplam, 0.780825, places=6)
        self.assertIn(("taninmadi", "AVAX", "0.000211981558"), [tuple(r) for r in h])
        cekim = self.db.execute("SELECT miktar FROM hareket WHERE tur='cekim' AND varlik='AVAX'").fetchone()
        self.assertEqual(cekim[0], "-0.98280221")
        olgular = [json.loads(r[0]) for r in self.db.execute("SELECT alanlar FROM olgu WHERE oturum=?", (GUN11,))]
        self.assertIn("0,000212 AVAX", [o.get("miktar") for o in olgular])

    def test_moca(self):
        r = self.db.execute("SELECT SUM(CAST(miktar AS REAL)) FROM hareket WHERE varlik='MOCA'").fetchone()[0]
        self.assertEqual(r, 5653)
        self.assertIsNone(self.db.execute("SELECT dolar FROM hareket WHERE varlik='PIEVERSE'").fetchone()[0])

    def test_16_ekim_botu(self):
        o = [json.loads(r[0]) for r in self.db.execute(
            "SELECT alanlar FROM olgu WHERE oturum=? AND tur='bot_uyusmazlik'", (SABAH,))]
        self.assertEqual(len(o), 1)
        self.assertEqual((o[0]["kayit_sonuc"], o[0]["gercek_sonuc"]), ("+99,89 TL", "-0,22 TL"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM uyari WHERE tur='bot_uyusmazlik' AND onem='acil'").fetchone()[0], 1)
        turler = {r[0] for r in self.db.execute("SELECT tur FROM hareket WHERE hesap='alt'")}
        self.assertTrue({"bota_giris", "bottan_donus"} <= turler)

    def test_cagri_kaydi_salt_okunur(self):
        r = self.db.execute("SELECT COUNT(*), MIN(salt_okunur), COUNT(DISTINCT kaynak) FROM cagri").fetchone()
        self.assertGreater(r[0], 0)
        self.assertEqual(r[1], 1)


if __name__ == "__main__":
    unittest.main()
