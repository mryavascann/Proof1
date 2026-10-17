"""M6 kabul: ayrıntılı mod verisi — defter, bot incelemesi (iz), OKX kanıtı, mühür, bütçe. Salt okunur."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from anlatim import anlat, arastir, butce
from muhur import kok
from pano import veri

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"
AYAR = {"agent_id": "263", "sozlesme": "0x7C5aB869e8d972885673f19B848084279AAD0d48",
        "kimlik": "0x8004A818BFB912233c491871b3d84c89A494BD9e"}
KOK_17 = "0x" + "ab" * 32


class Ayrinti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dizin = Path(tempfile.mkdtemp())
        cls.db = cls.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, cls.db)
        anlat.anlat(cls.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        arastir.arastir(cls.db, OTURUM, arastir.KayitliAraclar(KOK / "anlatim" / "kayit" / "bot_16_ekim.json"))
        with closing(sqlite3.connect(cls.db)) as db:
            butce.yaz(db, "bugra", "2026-10", butce.SONNET, 1200, 300, Decimal("0.27"), "ok")
            butce.yaz(db, "bugra", "2026-10", butce.SONNET, 0, 0, Decimal("0"), "zaman_asimi")
            kok.muhur_yaz(db, {"gun": "2026-10-17", "kok": KOK_17, "onceki_kok": "0x" + "00" * 32,
                               "islem_kimligi": "0x" + "cd" * 32, "agent_id": "263", "ag": "fuji",
                               "sozlesme": AYAR["sozlesme"]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dizin)

    def ayrinti(self, gizli=True):
        with closing(sqlite3.connect(self.db)) as db:
            return veri.ayrinti(db, OTURUM, gizli=gizli, muhur_ayar=AYAR)

    def test_salt_okunur(self):
        with closing(sqlite3.connect(self.db)) as db:
            once = {t for (t,) in db.execute("SELECT name FROM sqlite_master")}
            veri.ayrinti(db, OTURUM, gizli=True, muhur_ayar=AYAR)
            sonra = {t for (t,) in db.execute("SELECT name FROM sqlite_master")}
        self.assertEqual(once, sonra)  # görünüm ya da tablo oluşturmaz

    def test_hareketler_rapor_gunu(self):
        h = self.ayrinti()["hareketler"]
        with closing(sqlite3.connect(self.db)) as db:
            beklenen = db.execute("SELECT count(*) FROM hareket WHERE zaman >= '2026-10-16T06:00:00' "
                                  "AND zaman < '2026-10-17T06:00:00'").fetchone()[0]
        self.assertEqual(h["toplam"], beklenen)
        self.assertIn("16 Ekim 2026 09.00", h["pencere"])
        s = h["satirlar"][0]
        for alan in ("zaman", "tur", "varlik", "miktar", "dolar", "kaynak_okuma", "islem"):
            self.assertIn(alan, s)
        self.assertTrue(all(x["dolar"] is None or x["dolar"].endswith("$") for x in h["satirlar"]))
        self.assertTrue(all(x["islem"] is None or len(x["islem"]) <= 14 for x in h["satirlar"]))

    def test_uyari_gruplari(self):
        g = self.ayrinti()["uyarilar"]
        with closing(sqlite3.connect(self.db)) as db:
            beklenen = dict(((t, o), n) for t, o, n in db.execute(
                "SELECT tur, onem, count(*) FROM uyari WHERE oturum=? GROUP BY tur, onem", (OTURUM,)))
        self.assertEqual({(x["tur"], x["onem"]): x["sayi"] for x in g}, beklenen)
        if g:
            self.assertTrue(all(x["metin"] for x in g))
            self.assertEqual(g[0]["onem"], min((x["onem"] for x in g), key=veri.ONEM_SIRASI.get))

    def test_cumleler_denetim_etiketli(self):
        c = self.ayrinti()["cumleler"]
        self.assertTrue(c)
        self.assertTrue(all(x["denetim"] in ("gecti", "kalip") and x["olgular"] for x in c))

    def test_bot_incelemesi_iz(self):
        b = self.ayrinti()["bot"]
        self.assertIn("+99,89 TL", b["olgu"]["kayit_sonuc"])
        araclar = [a["arac"] for a in b["iz"]]
        self.assertEqual(araclar[0], "grid_get_order_details [kayıt]")
        self.assertTrue(b["kayit"])
        self.assertTrue(any(a["sonuc"].startswith("hata") for a in b["iz"]))
        self.assertIn("iki kez sayılmış gibi", b["iz"][-1]["karar"])

    def test_okx_kaniti(self):
        k = self.ayrinti()["kanit"]
        with closing(sqlite3.connect(self.db)) as db:
            toplam = db.execute("SELECT count(*) FROM cagri WHERE oturum=?", (OTURUM,)).fetchone()[0]
            hata = db.execute("SELECT count(*) FROM cagri WHERE oturum=? AND sonuc!='ok'", (OTURUM,)).fetchone()[0]
        self.assertEqual(k["toplam"], toplam)
        self.assertEqual(sum(g["hata"] for g in k["gruplar"]), hata)
        self.assertTrue(k["salt_okunur_hepsi"])
        g = k["gruplar"][0]
        for alan in ("kaynak", "ad", "cagri", "hata", "ort_ms", "alanlar", "salt_okunur"):
            self.assertIn(alan, g)
        self.assertLessEqual(len(k["hatalar"]), 10)
        self.assertTrue(all(h["kod"] for h in k["hatalar"]))

    def test_muhur(self):
        m = self.ayrinti()["muhur"]
        self.assertEqual((m["ag"], m["chain_id"], m["agent_id"]), ("Avalanche Fuji", 43113, "263"))
        self.assertEqual(m["gun_muhru"]["kok"], KOK_17)
        self.assertIn("testnet.snowtrace.io/tx/0x" + "cd" * 32, m["gun_muhru"]["gezgin"])
        self.assertIn("doğruluğunu kanıtlamaz", m["not"])
        self.assertEqual(m["dogrulama"], "bekliyor")  # zincire sorulmadan "doğrulandı" yazılmaz

    def test_muhur_dogrulama(self):
        with closing(sqlite3.connect(self.db)) as db:
            d = veri.muhur_dogrula(db, "2026-10-17", AYAR, rpc=lambda y, p: KOK_17 if y == "eth_call" else None)
            self.assertEqual(d["durum"], "dogrulandi")
            d = veri.muhur_dogrula(db, "2026-10-17", AYAR, rpc=lambda y, p: "0x" + "00" * 32)
            self.assertEqual(d["durum"], "zincirde_yok")
            d = veri.muhur_dogrula(db, "2026-10-17", AYAR, rpc=lambda y, p: "0x" + "11" * 32)
            self.assertEqual(d["durum"], "uyusmuyor")

            def kopuk(y, p):
                raise OSError("ağ yok")
            self.assertEqual(veri.muhur_dogrula(db, "2026-10-17", AYAR, rpc=kopuk)["durum"], "baglanilamadi")
            self.assertEqual(veri.muhur_dogrula(db, "2026-10-16", AYAR, rpc=lambda y, p: KOK_17)["durum"], "yerel_kayit_yok")

    def test_butce(self):
        b = self.ayrinti()["butce"]
        self.assertEqual((b["kullanici"], b["ay"], b["tavan"]), ("bugra", "2026-10", "35 TL"))
        self.assertEqual(b["harcanan"], "0,27 TL")
        self.assertEqual(b["cagri"], 2)
        self.assertEqual(b["durumlar"].get("zaman_asimi"), 1)
        self.assertIn(b["kip"], ("claude-sonnet-5-5", "claude-haiku-5-5", "kalip"))

    def test_gizli_mod_seviye_yok(self):
        metin = json.dumps(self.ayrinti(gizli=True), ensure_ascii=False)
        self.assertNotIn('"baslangic"', metin)
        with closing(sqlite3.connect(self.db)) as db:
            tam = [a for (a,) in db.execute("SELECT adres FROM adres") if a and len(a) > 12]
        self.assertFalse(any(a in metin for a in tam))


if __name__ == "__main__":
    unittest.main()
