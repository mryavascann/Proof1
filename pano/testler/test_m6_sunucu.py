"""M6 kabul: ayrıntılı mod uçları."""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from anlatim import anlat
from pano import sunucu

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


class Uclar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dizin = Path(tempfile.mkdtemp())
        cls.db = cls.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, cls.db)
        anlat.anlat(cls.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        cls.eski = {k: os.environ.get(k) for k in ("PROOF1_AGENT_ID", "PROOF1_SEAL_ADDRESS")}
        os.environ.update(PROOF1_AGENT_ID="263", PROOF1_SEAL_ADDRESS="0x7C5aB869e8d972885673f19B848084279AAD0d48")
        cls.httpd = sunucu.kur(cls.db, "127.0.0.1", 0)
        cls.adres = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for k, v in cls.eski.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(cls.dizin)

    def al(self, yol):
        with urllib.request.urlopen(self.adres + yol, timeout=10) as y:
            return json.loads(y.read())

    def test_ayrinti(self):
        a = self.al(f"/api/ayrinti?oturum={OTURUM}")
        self.assertTrue(a["gizli"])
        for anahtar in ("hareketler", "cumleler", "bot", "kanit", "muhur", "butce"):
            self.assertIn(anahtar, a)
        self.assertEqual(a["muhur"]["agent_id"], "263")
        self.assertEqual(a["muhur"]["dogrulama"], "bekliyor")

    def test_muhur_dogrula_yerel_kayit_yoksa(self):
        self.assertEqual(self.al("/api/muhur-dogrula?gun=2026-10-17")["durum"], "yerel_kayit_yok")


if __name__ == "__main__":
    unittest.main()
