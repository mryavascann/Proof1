"""M4 kabul: panonun rapor verisi. Beklentiler örnek veritabanından okunur (Buğra veriyi yeniden üretebilir)."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from anlatim import anlat
from anlatim.denetim import sayilari_ayikla
from pano import veri

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


def sorgu(sql, *arg):
    with closing(sqlite3.connect(ORNEK_DB)) as db:
        return db.execute(sql, arg).fetchall()


def olgu(tur):
    return [(no, json.loads(a)) for no, a in sorgu("SELECT no, alanlar FROM olgu WHERE oturum=? AND tur=? AND gizli=0",
                                                    OTURUM, tur)]


def benim_adres():
    return sorgu("SELECT etiket, ag FROM adres WHERE tahmin='benim' ORDER BY id LIMIT 1")[0]


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

    def rapor(self, gizli=True, db_yolu=None):
        with closing(sqlite3.connect(db_yolu or self.db)) as db:
            return veri.rapor(db, OTURUM, gizli=gizli)

    def ayri_db(self):
        yol = self.dizin / f"{self._testMethodName}.db"
        shutil.copy(self.db, yol)
        return yol

    def test_ornek_veri_etiketli(self):
        r = self.rapor()
        self.assertEqual(r["veri_turu"], "örnek")
        self.assertTrue(r["gizli"])

    def test_akis_tarihsel_cekim_ve_donem(self):
        _, ozet = olgu("cekim_ozet")[0]
        a = self.rapor()["akis"]
        self.assertEqual(a["donem"], ozet["donem"])
        self.assertEqual(a["kaynak"]["tutar"], ozet["toplam_dolar"])
        self.assertIn("bugünkü bakiye değil", a["not"])
        self.assertEqual(a["birim"], "USD")

    def test_akis_gruplari_ve_diger(self):
        paylar = sorted(((a["ag"], a["dolar"]) for _, a in olgu("ag_payi")),
                        key=lambda x: sayilari_ayikla(x[1])[0].deger, reverse=True)
        gruplar = self.rapor()["akis"]["gruplar"]
        self.assertLessEqual(len(gruplar), 5)
        if len(paylar) > 5:
            self.assertEqual([g["ad"] for g in gruplar[:4]], [p[0] for p in paylar[:4]])
            diger = gruplar[-1]
            self.assertEqual(diger["ad"], "Diğer")
            self.assertIsNone(diger["tutar"])  # pano yeni toplam üretmez
            self.assertEqual([(x["ad"], x["tutar"]) for x in diger["alt"]], paylar[4:])
        self.assertAlmostEqual(gruplar[0]["deger"], float(sayilari_ayikla(paylar[0][1])[0].deger))

    def test_moca_cumlesi_ethereum_bandinda(self):
        eth = next(g for g in self.rapor()["akis"]["gruplar"] if g["ad"] == "Ethereum")
        moca = [c for c in eth["cumleler"] if "46,15 PIEVERSE verip 1.587 MOCA aldın" in c["metin"]]
        self.assertEqual(len(moca), 1, [c["metin"] for c in eth["cumleler"]])
        self.assertIn("ağ ücreti", moca[0]["metin"])
        self.assertIn("dolar fiyatı yok", moca[0]["metin"])
        self.assertIn("9 Nisan 2026", moca[0]["donem_notu"])

    def test_ag_kapsami(self):
        beklenen = sorgu("SELECT count(*) FROM adres WHERE ag='ethereum'")[0][0]
        eth = next(g for g in self.rapor()["akis"]["gruplar"] if g["ad"] == "Ethereum")
        self.assertEqual(eth["kapsam"]["adres"], beklenen)
        self.assertEqual(eth["kapsam"]["katmanlar"][0], "Çekim görüldü")

    def test_gizli_modda_seviye_ve_yuzde_yok(self):
        r = self.rapor(gizli=True)
        metin = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("kalan", r)
        self.assertNotIn("%", metin)
        self.assertNotIn('"baslangic"', metin)
        self.assertNotIn('"bitis"', metin)

    def test_gizli_kapaliyken_kalan_yalniz_sayi_varsa(self):
        r = self.rapor(gizli=False)
        kalan = [a for _, a in [(n, json.loads(x)) for n, x in sorgu(
            "SELECT no, alanlar FROM olgu WHERE oturum=? AND tur='kalan_ozet'", OTURUM)]]
        if kalan and sayilari_ayikla(kalan[0].get("dolar", "")):
            self.assertIn(kalan[0]["dolar"], r["kalan"]["metin"])
        else:
            self.assertNotIn("kalan", r)  # "gizli adreste yaklaşık gizli" gibi cümle kurulmaz

    def test_tam_adres_yok(self):
        tam = [a for (a,) in sorgu("SELECT adres FROM adres") if a and len(a) > 12]
        metin = json.dumps(self.rapor(), ensure_ascii=False)
        self.assertFalse(any(a in metin for a in tam))

    def test_kopru_ayri_donem(self):
        gun = sorgu("SELECT max(gun) FROM kopru WHERE gun <= '2026-10-17'")[0][0]
        k = self.rapor()["kopru"]
        self.assertEqual(k["gun"], gun)
        self.assertIn("ayrı", k["not"])
        for kapsam in k["kapsamlar"].values():
            self.assertLessEqual(len(kapsam["ozet"]), 5)
            for s in kapsam["ozet"]:
                self.assertTrue(s["dolar"] is None or s["dolar"].endswith("$"))

    def test_kopru_dolar_yoksa_sifir_yazilmaz(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE kopru (gun, kapsam, sira, kalem, tutar, varlik_tutar, aciklama, olgular)")
            db.execute("INSERT INTO kopru VALUES ('2026-10-12','servet',1,'ucret','0','{\"AVAX\": \"-0.017189\"}','x','[]')")
            k = veri._kopru(db, OTURUM, True)
        ucret = k["kapsamlar"]["servet"]["ozet"][0]
        self.assertEqual(ucret["varliklar"], ["−0,017189 AVAX"])
        self.assertIsNone(ucret["dolar"])

    def test_uyarilar_en_cok_uc(self):
        u = self.rapor()["uyarilar"]
        self.assertLessEqual(len(u["liste"]), 3)
        self.assertEqual(u["toplam"], sorgu("SELECT count(*) FROM uyari WHERE oturum=?", OTURUM)[0][0])
        if sorgu("SELECT 1 FROM uyari WHERE onem='acil' AND oturum=?", OTURUM):
            self.assertEqual(u["liste"][0]["onem"], "acil")

    def test_uyarilar_baska_gunu_karistirmaz_canliyi_alir(self):
        yol = self.ayri_db()
        with closing(sqlite3.connect(yol)) as db:
            db.execute("INSERT INTO uyari (oturum, zaman, tur, onem, olgular) VALUES "
                       "('sabah-2026-10-01', '2026-10-01T07:00:00Z', 'aciklanamayan', 'acil', '[]'),"
                       "('canli-42', '2026-10-17T23:00:00Z', 'bot_uyusmazlik', 'acil', '[]'),"
                       "('canli-41', '2026-10-10T12:00:00Z', 'bot_uyusmazlik', 'acil', '[]')")
            db.commit()
        u = self.rapor(db_yolu=yol)["uyarilar"]
        self.assertEqual(u["toplam"], sorgu("SELECT count(*) FROM uyari WHERE oturum=?", OTURUM)[0][0] + 1)
        self.assertEqual(u["liste"][0]["zaman"], "2026-10-17T23:00:00Z")

    def test_kopru_try_tl_yazilir(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE kopru (gun, kapsam, sira, kalem, tutar, varlik_tutar, aciklama, olgular)")
            db.execute("INSERT INTO kopru VALUES ('2026-10-12','servet',1,'cekim','0','{\"TRY\": \"-1500.5\"}','x','[]')")
            k = veri._kopru(db, OTURUM, True)
        self.assertEqual(k["kapsamlar"]["servet"]["kalemler"][0]["varliklar"], ["−1.500,5 TL"])

    def test_sahiplik_sorulari(self):
        beklenen = {e for (e,) in sorgu("SELECT etiket FROM adres WHERE tahmin='benim'")}
        s = self.rapor()["sahiplik"]
        self.assertEqual({x["etiket"] for x in s}, beklenen)
        self.assertTrue(all(x["durum"] == "tahmin" and x["kanit"] for x in s))

    def test_isaret_tahminin_yerine_gecer(self):
        etiket, ag = benim_adres()
        yol = self.ayri_db()
        with closing(sqlite3.connect(yol)) as db:
            veri.isaret_yaz(db, etiket, ag, "benim")
            s = {x["etiket"]: x["durum"] for x in veri.rapor(db, OTURUM)["sahiplik"]}
            veri.isaret_yaz(db, etiket, ag, "benim_degil")
            s2 = {x["etiket"]: x["durum"] for x in veri.rapor(db, OTURUM)["sahiplik"]}
        self.assertEqual(s[etiket], "benim")
        self.assertEqual(s2[etiket], "benim_degil")

    def test_isaret_dogrulanir(self):
        etiket, ag = benim_adres()
        with closing(sqlite3.connect(self.ayri_db())) as db:
            with self.assertRaises(veri.IsaretHatasi):
                veri.isaret_yaz(db, etiket, ag, "belki")
            with self.assertRaises(veri.IsaretHatasi):
                veri.isaret_yaz(db, "YOK_9", ag, "benim")
            tablolar = {t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            yazilan = db.execute("SELECT count(*) FROM isaret").fetchone()[0] if "isaret" in tablolar else 0
        self.assertEqual(yazilan, 0)

    def test_isaret_baska_tabloya_yazmaz(self):
        etiket, ag = benim_adres()
        with closing(sqlite3.connect(self.ayri_db())) as db:
            once = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    for t in ("hareket", "adres", "olgu", "uyari", "kopru", "fotograf")}
            veri.isaret_yaz(db, etiket, ag, "benim")
            sonra = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in once}
        self.assertEqual(once, sonra)


if __name__ == "__main__":
    unittest.main()
