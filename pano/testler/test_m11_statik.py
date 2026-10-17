"""Herkese açık demo (Vercel): örnek veriyle statik pano.

Yalnız depodaki anonim örnek veritabanı kullanılır; canlı veri, anahtar ve kişisel tam adres yayına girmez.
Sunucu uçları veri/ altında JSON dosyası olur (Vercel api/ klasörünü fonksiyon sayar); "Kendi hesabını bağla" demoda kapalıdır (anahtar hiçbir sunucuya gitmez).
"""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from pano import statik

KOK = Path(__file__).resolve().parents[2]
HERKESE_ACIK = {"0x7c5ab869e8d972885673f19b848084279aad0d48", "0x8004a818bfb912233c491871b3d84c89a494bd9e",
                "0x09a292458f780a28622062dac6560fa6b87b3ed6"}


class StatikDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hedef = Path(tempfile.mkdtemp()) / "proof1"
        statik.uret(cls.hedef)

    def oku(self, ad):
        return json.loads((self.hedef / "veri" / ad).read_text(encoding="utf-8"))

    def test_dosyalar(self):
        for ad in ("index.html", "static/pano.js", "static/pano.css", "static/kus-64.png", "vercel.json",
                   "veri/rapor-1.json", "veri/rapor-0.json", "veri/ayrinti-1.json", "veri/ayrinti-0.json", "veri/hesaplar.json"):
            self.assertTrue((self.hedef / ad).is_file(), ad)

    def test_yalniz_ornek_veri(self):
        r = self.oku("rapor-1.json")
        self.assertEqual(r["veri_turu"], "örnek")
        self.assertTrue(r["akis"]["gruplar"])
        self.assertTrue(r["ozet"])                       # kalıp cümleler üretildi (model çağrısı yok)
        self.assertEqual(self.oku("hesaplar.json"), [{"hesap": "ana", "ad": "Örnek hesap"}])

    def test_kisisel_adres_ve_sir_yok(self):
        for dosya in self.hedef.rglob("*"):
            if dosya.suffix not in (".json", ".html", ".js", ".css"):
                continue
            metin = dosya.read_text(encoding="utf-8")
            for adres in re.findall(r"0x[0-9a-fA-F]{40}(?![0-9a-fA-F])", metin):
                self.assertIn(adres.lower(), HERKESE_ACIK, f"{dosya.name}: {adres[:8]}…")
            self.assertNotRegex(metin, r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b", dosya.name)
            self.assertNotRegex(metin, r"(?i)(api_key|secret_key|passphrase|bot_token)\"?\s*[:=]\s*\"[A-Za-z0-9]{8,}", dosya.name)

    def test_ornek_veride_sahte_bakiye_yok(self):
        # örnek veritabanında bakiye seviyesi yok; köprünün "0 $" seviyesi yayına konmaz (sayfa "örnek veride yok" der)
        for g in ("0", "1"):
            r = self.oku(f"rapor-{g}.json")
            for kap in (r.get("kopru") or {}).get("kapsamlar", {}).values():
                self.assertFalse({"baslangic", "bitis"} & {k["kalem"] for k in kap["kalemler"]}, g)

    def test_muhur_kamu_degerleri(self):
        mu = self.oku("ayrinti-1.json")["muhur"]
        self.assertEqual(mu["agent_id"], "263")
        self.assertEqual(mu["sozlesme"].lower(), "0x7c5ab869e8d972885673f19b848084279aad0d48")

    def test_sayfa_statik_kipte_ve_hesap_baglama_kapali(self):
        html = (self.hedef / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-statik="1"', html)
        self.assertIn('id="bagla-demo"', html)
        js = (self.hedef / "static" / "pano.js").read_text(encoding="utf-8")
        self.assertIn("STATIK", js)

    def test_yanlis_klasor_silinmez(self):
        baska = Path(tempfile.mkdtemp())
        (baska / "onemli.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            statik.uret(baska)
        self.assertTrue((baska / "onemli.txt").exists())

    def test_canli_veritabani_okunmaz(self):
        self.assertEqual(statik.ORNEK_DB, KOK / "ortak" / "ornek" / "proof1_ornek.db")
        self.assertNotIn("proof1.db\"", Path(statik.__file__).read_text(encoding="utf-8").replace("proof1_ornek.db", ""))


class YeniKurulum(unittest.TestCase):
    """Depoyu yeni indiren biri `python -m pano.sunucu` deyince pano açılır (örnek verinin kopyasıyla), sonra kendi
    hesabını bağlar. Depodaki örnek dosyanın kendisine yazılmaz."""

    def kok(self):
        kok = Path(tempfile.mkdtemp())
        (kok / "ortak" / "ornek").mkdir(parents=True)
        shutil.copy(statik.ORNEK_DB, kok / "ortak" / "ornek" / "proof1_ornek.db")
        return kok

    def test_veri_yoksa_ornek_kopyasi(self):
        from pano import sunucu
        kok = self.kok()
        yol, not_ = sunucu.veri_dosyasi(kok, {})
        self.assertEqual(yol, kok / "data" / "ornek.db")
        self.assertTrue(yol.is_file())
        self.assertIn("örnek", not_)

    def test_canli_veri_ya_da_proof1_db_varsa_o(self):
        from pano import sunucu
        kok = self.kok()
        (kok / "data").mkdir()
        (kok / "data" / "proof1.db").write_bytes(b"")
        self.assertEqual(sunucu.veri_dosyasi(kok, {}), (kok / "data" / "proof1.db", None))
        self.assertEqual(sunucu.veri_dosyasi(kok, {"PROOF1_DB": "x/y.db"})[0], kok / "x" / "y.db")


if __name__ == "__main__":
    unittest.main()
