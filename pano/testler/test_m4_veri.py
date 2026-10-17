"""M4 kabul: panonun rapor verisi. Örnek veritabanıyla; gizli mod seviyeleri hiçbir alanda taşımaz."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from anlatim import anlat
from pano import veri

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


class Rapor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dizin = Path(tempfile.mkdtemp())
        cls.db = cls.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, cls.db)
        anlat.anlat(cls.db, OTURUM, None, kullanici="bugra", ay="2026-10")  # kalıp cümleler

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dizin)

    def rapor(self, gizli=True):
        with closing(sqlite3.connect(self.db)) as db:
            return veri.rapor(db, OTURUM, gizli=gizli)

    def test_ornek_veri_etiketli(self):
        r = self.rapor()
        self.assertEqual(r["veri_turu"], "örnek")
        self.assertTrue(r["gizli"])

    def test_akis_tarihsel_cekim_ve_donem(self):
        a = self.rapor()["akis"]
        self.assertEqual(a["donem"], "Aralık 2024 – Ekim 2026")
        self.assertEqual(a["kaynak"]["tutar"], "48.280 $")
        self.assertIn("bugünkü bakiye değil", a["not"])
        self.assertEqual(a["birim"], "USD")

    def test_akis_gruplari_ve_diger(self):
        gruplar = self.rapor()["akis"]["gruplar"]
        self.assertLessEqual(len(gruplar), 7)
        self.assertGreaterEqual(len(gruplar), 5)
        adlar = [g["ad"] for g in gruplar]
        self.assertEqual(adlar[:4], ["Arbitrum", "Ethereum", "Chiliz", "Polygon"])
        diger = gruplar[-1]
        self.assertEqual(diger["ad"], "Diğer")
        self.assertIsNone(diger["tutar"])  # pano yeni toplam üretmez
        self.assertEqual([(x["ad"], x["tutar"]) for x in diger["alt"]], [("Tron", "28,9 $"), ("Avalanche", "10,33 $")])
        # Geometri değerleri kaynak tutarlarla orantılı.
        self.assertAlmostEqual(gruplar[0]["deger"], 20889.0)
        self.assertAlmostEqual(diger["deger"], 28.9 + 10.33, places=2)

    def test_moca_cumlesi_ethereum_bandinda(self):
        eth = next(g for g in self.rapor()["akis"]["gruplar"] if g["ad"] == "Ethereum")
        metinler = [c["metin"] for c in eth["cumleler"]]
        self.assertTrue(any("46,15 PIEVERSE verip 1.587 MOCA aldın; ağ ücreti 0,000129 ETH" in m for m in metinler))
        moca = next(c for c in eth["cumleler"] if "PIEVERSE" in c["metin"])
        self.assertEqual(moca["olgular"], ["o9"])
        self.assertIn("9 Nisan 2026", moca["donem_notu"])

    def test_ag_kapsami(self):
        ava = next(x for x in self.rapor()["akis"]["gruplar"][-1]["alt"] if x["ad"] == "Avalanche")
        self.assertEqual(ava["kapsam"]["adres"], 2)
        eth = next(g for g in self.rapor()["akis"]["gruplar"] if g["ad"] == "Ethereum")
        self.assertEqual(eth["kapsam"]["katmanlar"], ["Çekim görüldü", "Bakiye okundu", "Sonraki hareketler izlendi"])

    def test_gizli_modda_seviye_ve_yuzde_yok(self):
        metin = json.dumps(self.rapor(gizli=True), ensure_ascii=False)
        self.assertNotIn("360", metin)
        self.assertNotIn("kalan", metin.lower())
        self.assertNotIn("%", metin)
        self.assertNotIn("baslangic", metin)
        self.assertNotIn("bitis", metin)

    def test_gizli_kapaliyken_kalan_gorunur(self):
        r = self.rapor(gizli=False)
        self.assertIn("360 $", r["kalan"]["metin"])
        self.assertIn("ayrı zaman", r["kalan"]["not"])

    def test_tam_adres_yok(self):
        with closing(sqlite3.connect(self.db)) as db:
            tam = [a for (a,) in db.execute("SELECT adres FROM adres") if a]
        metin = json.dumps(self.rapor(), ensure_ascii=False)
        self.assertFalse(any(a in metin for a in tam if len(a) > 12))

    def test_kopru_ayri_donem_ve_coin_birimleri(self):
        k = self.rapor()["kopru"]
        self.assertEqual(k["gun"], "2026-10-12")
        self.assertIn("ayrı", k["not"])
        servet = k["kapsamlar"]["servet"]
        self.assertLessEqual(len(servet["ozet"]), 5)
        adlar = [s["ad"] for s in servet["ozet"]]
        self.assertIn("Açıklanamayan", adlar)
        self.assertIn("Ücretler", adlar)
        ucret = next(s for s in servet["ozet"] if s["ad"] == "Ücretler")
        self.assertEqual(ucret["varliklar"], ["−0,017189 AVAX"])
        self.assertIsNone(ucret["dolar"])  # tutar henüz doldurulmadı: sıfır yazılmaz
        self.assertTrue(any(k_["kalem"] == "aktarim" for k_ in servet["kalemler"]))

    def test_uyarilar_en_cok_uc(self):
        u = self.rapor()["uyarilar"]
        self.assertLessEqual(len(u["liste"]), 3)
        self.assertEqual(u["liste"][0]["onem"], "acil")
        self.assertIn("+99,89 TL", u["liste"][0]["metin"])
        self.assertEqual(u["toplam"], 2)

    def test_sahiplik_sorulari(self):
        s = self.rapor()["sahiplik"]
        self.assertEqual({x["etiket"] for x in s}, {"BENIM_1", "BENIM_2"})
        self.assertTrue(all(x["durum"] == "tahmin" for x in s))
        self.assertTrue(all(x["kanit"] for x in s))

    def ayri_db(self):
        yol = self.dizin / f"{self._testMethodName}.db"
        shutil.copy(self.db, yol)
        return yol

    def test_isaret_tahminin_yerine_gecer(self):
        with closing(sqlite3.connect(self.ayri_db())) as db:
            veri.isaret_yaz(db, "BENIM_1", "avalanche", "benim")
            s = {x["etiket"]: x["durum"] for x in veri.rapor(db, OTURUM)["sahiplik"]}
            veri.isaret_yaz(db, "BENIM_1", "avalanche", "benim_degil")
            s2 = {x["etiket"]: x["durum"] for x in veri.rapor(db, OTURUM)["sahiplik"]}
        self.assertEqual(s["BENIM_1"], "benim")
        self.assertEqual(s2["BENIM_1"], "benim_degil")

    def test_isaret_dogrulanir(self):
        with closing(sqlite3.connect(self.ayri_db())) as db:
            with self.assertRaises(veri.IsaretHatasi):
                veri.isaret_yaz(db, "BENIM_1", "avalanche", "belki")
            with self.assertRaises(veri.IsaretHatasi):
                veri.isaret_yaz(db, "YOK_9", "avalanche", "benim")
            tablolar = {t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            yazilan = db.execute("SELECT count(*) FROM isaret").fetchone()[0] if "isaret" in tablolar else 0
        self.assertEqual(yazilan, 0)

    def test_isaret_baska_tabloya_yazmaz(self):
        with closing(sqlite3.connect(self.ayri_db())) as db:
            once = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    for t in ("hareket", "adres", "olgu", "uyari", "kopru", "fotograf")}
            veri.isaret_yaz(db, "BENIM_2", "avalanche", "benim")
            sonra = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in once}
        self.assertEqual(once, sonra)


if __name__ == "__main__":
    unittest.main()
