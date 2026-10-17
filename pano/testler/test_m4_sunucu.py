"""M4 kabul: pano sunucusu. Yerel HTTP; anahtar yok; yalnız isaret yazılır."""
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from anlatim import anlat
from pano import sunucu

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


class Sunucu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dizin = Path(tempfile.mkdtemp())
        cls.db = cls.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, cls.db)
        anlat.anlat(cls.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        cls.httpd = sunucu.kur(cls.db, "127.0.0.1", 0)
        cls.adres = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.dizin)

    def al(self, yol):
        with urllib.request.urlopen(self.adres + yol, timeout=5) as y:
            return y.status, dict(y.headers), y.read().decode("utf-8")

    def gonder(self, yol, govde):
        istek = urllib.request.Request(self.adres + yol, data=json.dumps(govde).encode(),
                                       headers={"content-type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(istek, timeout=5) as y:
                return y.status, json.loads(y.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_sayfa(self):
        durum, basliklar, govde = self.al("/")
        self.assertEqual(durum, 200)
        self.assertIn("text/html", basliklar["Content-Type"])
        self.assertIn("<title>proof1</title>", govde)
        self.assertNotIn("360", govde)

    def test_rapor_varsayilan_gizli(self):
        durum, basliklar, govde = self.al(f"/api/rapor?oturum={OTURUM}")
        self.assertEqual(durum, 200)
        self.assertEqual(basliklar["Cache-Control"], "no-store")
        r = json.loads(govde)
        self.assertTrue(r["gizli"])
        self.assertNotIn("kalan", r)
        self.assertNotIn("360", govde)

    def test_rapor_gizli_kapali(self):
        r = json.loads(self.al(f"/api/rapor?oturum={OTURUM}&gizli=0")[2])
        self.assertFalse(r["gizli"])

    def test_oturum_verilmezse_en_son(self):
        r = json.loads(self.al("/api/rapor")[2])
        self.assertEqual(r["oturum"], OTURUM)
        oturumlar = json.loads(self.al("/api/oturumlar")[2])
        self.assertEqual(oturumlar[0], OTURUM)

    def test_isaret(self):
        with closing(sqlite3.connect(self.db)) as db:
            etiket, ag = db.execute("SELECT etiket, ag FROM adres WHERE tahmin='benim' ORDER BY id LIMIT 1").fetchone()
        durum, cevap = self.gonder("/api/isaret", {"adres_etiket": etiket, "ag": ag, "sahip": "benim"})
        self.assertEqual((durum, cevap.get("durum")), (200, "kaydedildi"))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT sahip FROM isaret WHERE adres_etiket=?", (etiket,)).fetchone()[0], "benim")
        durum, _ = self.gonder("/api/isaret", {"adres_etiket": etiket, "ag": ag, "sahip": "hepsi"})
        self.assertEqual(durum, 400)
        durum, _ = self.gonder("/api/isaret", {"adres_etiket": "YOK", "ag": ag, "sahip": "benim"})
        self.assertEqual(durum, 400)

    def test_dizin_disina_cikilmaz(self):
        for yol in ("/static/../veri.py", "/static/%2e%2e/veri.py", "/static/../../.env"):
            with self.assertRaises(urllib.error.HTTPError) as h:
                self.al(yol)
            self.assertEqual(h.exception.code, 404)

    def test_bilinmeyen_uc(self):
        with self.assertRaises(urllib.error.HTTPError) as h:
            self.al("/api/yok")
        self.assertEqual(h.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
