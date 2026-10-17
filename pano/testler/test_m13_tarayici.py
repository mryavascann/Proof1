"""Tarayıcıda hızlı görünüm (Vercel): kullanıcı yalnız "Okuma" yetkili OKX TR anahtarını sayfaya yapıştırır; istekleri
tarayıcı kendisi imzalar ve doğrudan tr.okx.com'a gönderir (OKX TR tarayıcı isteklerine izin veriyor). Sunucu yok:
anahtar hiçbir yere gitmez, kaydedilmez. Yayındaki sayfa tarayıcı kuralıyla (CSP) yalnız OKX TR'ye bağlanabilir."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from pano import statik

KOK = Path(__file__).resolve().parents[2]
STATIK = KOK / "pano" / "static"
JS = (STATIK / "tarayici.js").read_text(encoding="utf-8")
HTML = (STATIK / "index.html").read_text(encoding="utf-8")
YAZMA_IZI = r"order|trade/|withdrawal$|transfer|cancel|amend|bot|grid|purchase|redeem|convert|lending"


class TarayiciIstemci(unittest.TestCase):
    def test_yalniz_okx_tr_ve_yalniz_get(self):
        self.assertIn('TABAN = "https://tr.okx.com"', JS)
        self.assertNotRegex(JS, r'method:\s*"(POST|PUT|DELETE|PATCH)"')
        uclar = re.findall(r'"(/api/v5/[a-z\-/]+)"', JS)
        self.assertTrue(uclar)
        for uc in uclar:
            self.assertNotRegex(uc, YAZMA_IZI, uc)
        self.assertIn('credentials: "omit"', JS)
        self.assertIn("IZINLI.indexOf(yol) < 0", JS)          # listede olmayan uç çağrılmaz

    def test_imza_ve_yazma_yetkisi_reddi(self):
        self.assertIn("crypto.subtle", JS)
        self.assertIn('"HMAC"', JS)
        self.assertIn('"trade"', JS)
        self.assertIn('"withdraw"', JS)

    def test_anahtar_saklanmaz(self):
        for yasak in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "console.log"):
            self.assertNotIn(yasak, JS)

    def test_sayfa_betigi_yukler_ve_dis_betik_butunlugu(self):
        self.assertIn('src="/static/tarayici.js"', HTML)
        for etiket in re.findall(r"<script[^>]+src=\"https?://[^>]+>", HTML):
            self.assertRegex(etiket, r'integrity="sha384-[A-Za-z0-9+/=]{40,}"', etiket)
            self.assertIn('crossorigin="anonymous"', etiket)


class Yayin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hedef = Path(tempfile.mkdtemp()) / "proof1"
        statik.uret(cls.hedef)

    def test_csp_yalniz_okx_tr(self):
        v = json.loads((self.hedef / "vercel.json").read_text(encoding="utf-8"))
        csp = next(h["value"] for g in v["headers"] for h in g["headers"] if h["key"] == "Content-Security-Policy")
        connect = re.search(r"connect-src ([^;]+)", csp).group(1).split()
        self.assertEqual(sorted(connect), sorted(["'self'", "https://tr.okx.com"]))
        for parca in ("form-action 'none'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'"):
            self.assertIn(parca, csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotRegex(re.search(r"script-src ([^;]+)", csp).group(1), r"unsafe-inline")

    def test_son_muhur_demoda(self):
        mu = json.loads((self.hedef / "veri" / "ayrinti-1.json").read_text(encoding="utf-8"))["muhur"]
        self.assertEqual(mu["son"][0]["gun"], "2026-10-16")
        self.assertTrue(mu["son"][0]["gezgin"].endswith("0x5135feef5860b1689908ab2f56def30363fb22ca424ca8f0b109177e91b2ef34"))


if __name__ == "__main__":
    unittest.main()
