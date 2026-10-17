"""M2 kabul: satır satır kök, kalıcı tuzlar, Merkle kanıtı, zincirli kök, mühür çağrısı."""
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from muhur import kok

KOK_DIZIN = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK_DIZIN / "ortak" / "ornek" / "proof1_ornek.db"
GUN = "2026-10-11"


def beklenen_satir():
    with sqlite3.connect(ORNEK_DB) as db:
        return db.execute("SELECT count(*) FROM hareket WHERE zaman >= '2026-10-10T21:00:00' "
                          "AND zaman < '2026-10-11T21:00:00'").fetchone()[0]


def sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


class Kanonik(unittest.TestCase):
    def test_alan_sirasi_ondalik_ve_id_disarida(self):
        satir = {"id": 99, "zaman": "2026-10-11T12:32:23.000Z", "miktar": "-0.98280221", "dolar": "1.2300",
                 "supheli": 0, "adres_id": None, "varlik": "AVAX", "ham_kimlik": "x"}
        metin = kok.kanonik(satir)
        self.assertNotIn('"id"', metin)
        self.assertEqual(list(json.loads(metin).keys()), sorted(json.loads(metin).keys()))
        self.assertIn('"miktar":"-0.98280221"', metin)
        self.assertIn('"dolar":"1.23"', metin)
        self.assertIn('"adres_id":null', metin)

    def test_ondalik_bicimi(self):
        self.assertEqual(kok.ondalik("1.000"), "1")
        self.assertEqual(kok.ondalik("-0.0"), "0")
        self.assertEqual(kok.ondalik("0.000211981558"), "0.000211981558")
        self.assertEqual(kok.ondalik("1E+2"), "100")
        self.assertIsNone(kok.ondalik(None))
        with self.assertRaises(ValueError):
            kok.ondalik("bir")


class GunSatirlari(unittest.TestCase):
    def test_istanbul_gunu_ve_sira(self):
        with sqlite3.connect(ORNEK_DB) as db:
            satirlar = kok.gun_satirlari(db, GUN)
        self.assertEqual(len(satirlar), beklenen_satir())
        self.assertGreater(len(satirlar), 0)
        anahtarlar = [(s["zaman"], s["ham_kimlik"]) for s in satirlar]
        self.assertEqual(anahtarlar, sorted(anahtarlar))
        self.assertIn("-0.98280221", [s["miktar"] for s in satirlar])

    def test_gun_sayisi(self):
        self.assertEqual(kok.gun_sayi("2026-10-11"), 20261011)


class Tuzlar(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.mkdtemp()
        self.yol = Path(self.dizin) / "tuzlar.json"

    def tearDown(self):
        shutil.rmtree(self.dizin)

    def test_kalici_ve_yalniz_eksik_uretilir(self):
        t1 = kok.tuzlari_hazirla(self.yol, ["a", "b"])
        self.assertEqual(set(t1), {"a", "b"})
        self.assertTrue(all(len(v) == 32 for v in t1.values()))
        t2 = kok.tuzlari_hazirla(self.yol, ["a", "b", "c"])
        self.assertEqual(t2["a"], t1["a"])
        self.assertEqual(t2["b"], t1["b"])
        self.assertIn("c", t2)
        self.assertEqual(stat.S_IMODE(os.stat(self.yol).st_mode), 0o600)


class Merkle(unittest.TestCase):
    def test_tek_yaprak_kurali(self):
        a, b, c = sha(b"a"), sha(b"b"), sha(b"c")
        self.assertEqual(kok.merkle([]), bytes(32))
        self.assertEqual(kok.merkle([a]), a)
        self.assertEqual(kok.merkle([a, b]), sha(a + b))
        self.assertEqual(kok.merkle([a, b, c]), sha(sha(a + b) + c))

    def test_her_yapragin_kaniti_dogrulanir(self):
        yapraklar = [sha(bytes([i])) for i in range(7)]
        kokum = kok.merkle(yapraklar)
        for i, y in enumerate(yapraklar):
            self.assertTrue(kok.kanit_dogrula(y, kok.kanit(yapraklar, i), kokum), i)
        self.assertFalse(kok.kanit_dogrula(sha(b"sahte"), kok.kanit(yapraklar, 3), kokum))


class GunKoku(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.mkdtemp()
        self.tuz_yolu = Path(self.dizin) / "tuzlar.json"
        with sqlite3.connect(ORNEK_DB) as db:
            self.satirlar = kok.gun_satirlari(db, GUN)

    def tearDown(self):
        shutil.rmtree(self.dizin)

    def test_tekrar_hesap_ayni_kok(self):
        onceki = sha(b"onceki")
        k1 = kok.gun_koku(self.satirlar, self.tuz_yolu, onceki)
        k2 = kok.gun_koku(self.satirlar, self.tuz_yolu, onceki)
        self.assertEqual(k1["kok"], k2["kok"])
        self.assertEqual(k1["kok"], sha(k1["merkle"] + onceki))
        self.assertEqual(k1["yaprak_sayisi"], beklenen_satir())

    def test_baska_tuz_baska_kok(self):
        k1 = kok.gun_koku(self.satirlar, self.tuz_yolu, bytes(32))
        k2 = kok.gun_koku(self.satirlar, Path(self.dizin) / "baska.json", bytes(32))
        self.assertNotEqual(k1["kok"], k2["kok"])

    def test_bir_satirin_kaniti_digerlerini_acmadan(self):
        k = kok.gun_koku(self.satirlar, self.tuz_yolu, bytes(32))
        tuzlar = kok.tuzlari_hazirla(self.tuz_yolu, [])
        s = self.satirlar[4]
        yaprak = kok.yaprak(tuzlar[s["ham_kimlik"]], s)
        self.assertTrue(kok.kanit_dogrula(yaprak, k["kanitlar"][s["ham_kimlik"]], k["merkle"]))
        degismis = dict(s, miktar="0.5")
        self.assertFalse(kok.kanit_dogrula(kok.yaprak(tuzlar[s["ham_kimlik"]], degismis),
                                           k["kanitlar"][s["ham_kimlik"]], k["merkle"]))


class MuhurCagrisi(unittest.TestCase):
    def test_seal_cagri_verisi(self):
        veri = kok.seal_cagri_verisi(263, 20261011, b"\x11" * 32)
        from eth_utils import keccak
        self.assertEqual(veri[:4], keccak(text="seal(uint256,uint32,bytes32)")[:4])
        self.assertEqual(len(veri), 4 + 32 * 3)
        self.assertEqual(int.from_bytes(veri[4:36], "big"), 263)
        self.assertEqual(int.from_bytes(veri[36:68], "big"), 20261011)
        self.assertEqual(veri[68:], b"\x11" * 32)


class MuhurTablosu(unittest.TestCase):
    def test_sozlesme_sutunlari(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "x.db"
            with sqlite3.connect(yol) as db:
                kok.muhur_yaz(db, {"gun": GUN, "kok": "0x" + "ab" * 32, "onceki_kok": "0x" + "00" * 32,
                                   "islem_kimligi": "0xdead", "agent_id": "263", "ag": "fuji",
                                   "sozlesme": "0x7C5aB869e8d972885673f19B848084279AAD0d48"})
                sutunlar = [r[1] for r in db.execute("PRAGMA table_info(muhur)")]
                self.assertEqual(sutunlar, ["gun", "kok", "onceki_kok", "islem_kimligi", "agent_id", "ag",
                                            "sozlesme", "zaman"])
                self.assertEqual(db.execute("select count(*) from muhur").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
