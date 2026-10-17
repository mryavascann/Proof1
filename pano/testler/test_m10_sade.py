"""Sade ilk sayfa (17 Ekim yeniden tasarım).

- Uyarı kartı kısa başlık taşır; bot uyuşmazlığında iki sayı (kayıt / gerçek) kod tarafından verilir, sayfa uydurmaz.
- Kendi hesabını bağlama formu: üç alan da ekranda gizli (sunumda yansıtılıyor), tarayıcıda saklanmaz.
- Dış betikler sabit sürümle yüklenir; sayfa onlarsız da çalışır (hareket yalnız süstür).
"""
import re
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pano import veri

KOK = Path(__file__).resolve().parents[2]
STATIK = KOK / "pano" / "static"
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


class UyariKarti(unittest.TestCase):
    def setUp(self):
        self.yol = Path(tempfile.mkdtemp()) / "p.db"
        shutil.copy(ORNEK_DB, self.yol)

    def test_her_kartin_kisa_basligi_var(self):
        with closing(sqlite3.connect(self.yol)) as db:
            u = veri._uyarilar(db, OTURUM)
        self.assertTrue(u["liste"])
        for x in u["liste"]:
            self.assertTrue(x["baslik"])
            self.assertLessEqual(len(x["baslik"]), 28, x["baslik"])

    def test_bot_kartinda_kayit_ve_gercek(self):
        with closing(sqlite3.connect(self.yol)) as db:
            u = veri._uyarilar(db, OTURUM)
            bot_olgu = next(o for o in veri.olgulari_oku(db, OTURUM) if o.tur == "bot_uyusmazlik")
        bot = next(x for x in u["liste"] if x["tur"] == "bot_uyusmazlik")
        self.assertEqual(bot["baslik"], "Bot kaydı tutmuyor")
        # sayılar olgudan aynen gelir (eksi işareti tipografik eksiye çevrilebilir)
        self.assertEqual(bot["kayit"].replace("−", "-"), bot_olgu.alanlar["kayit_sonuc"])
        self.assertEqual(bot["gercek"].replace("−", "-"), bot_olgu.alanlar["gercek_sonuc"])

    def test_bilinmeyen_tur_genel_baslik(self):
        self.assertEqual(veri.uyari_basligi("yeni_bir_tur"), "Uyarı")


class Sayfa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIK / "index.html").read_text(encoding="utf-8")
        cls.js = (STATIK / "pano.js").read_text(encoding="utf-8")

    def test_anahtar_alanlari_ekranda_gizli(self):
        for ad in ("api_key", "secret_key", "passphrase"):
            m = re.search(r'<input[^>]*name="%s"[^>]*>' % ad, self.html)
            self.assertIsNotNone(m, ad)
            self.assertIn('type="password"', m.group(0))
            self.assertIn('autocomplete="off"', m.group(0))

    def test_anahtar_tarayicida_saklanmaz(self):
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)
        self.assertIn("/api/hesap/bagla", self.js)
        self.assertIn("reset()", self.js)              # gönderilince form temizlenir

    def test_dis_betik_surumu_sabit(self):
        dis = re.findall(r'<script[^>]+src="(https?://[^"]+)"', self.html)
        self.assertTrue(dis)
        for src in dis:
            self.assertRegex(src, r"@\d+\.\d+\.\d+/", src)

    def test_sade_ve_detay_kipleri(self):
        for kimlik in ('id="sade"', 'id="detay"', 'id="sahne"', 'id="detay-dugme"', 'id="bagla-perde"'):
            self.assertIn(kimlik, self.html)
        self.assertIn("window.gsap", self.js)         # GSAP yoksa (çevrimdışı) sayfa yine çizilir

    def test_hesap_parametresi_her_istekte(self):
        self.assertIn("function api(", self.js)
        for uc in ('"/api/rapor"', '"/api/ayrinti"', '"/api/isaret"'):
            self.assertIn("api(" + uc, self.js)


if __name__ == "__main__":
    unittest.main()
