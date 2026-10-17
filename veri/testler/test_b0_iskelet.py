"""B0 kabul: sırlar ve gerçek veri izlenmiyor; örnek veri ve sözleşme izlenebilir."""
import re
import subprocess
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]


def yok_sayiliyor(yol: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", yol], cwd=KOK)
    return r.returncode == 0


class B0Iskelet(unittest.TestCase):
    def test_sirlar_ve_veri_yok_sayiliyor(self):
        for yol in [".env", "data/proof1.db", "veri/x.db", "devir-bugra.md", "Screenshot 1.png"]:
            self.assertTrue(yok_sayiliyor(yol), yol)

    def test_ornek_ve_sozlesme_izlenebilir(self):
        for yol in [".env.ornek", "ortak/SOZLESME.md", "ortak/ornek/proof1_ornek.db", "README.md"]:
            self.assertFalse(yok_sayiliyor(yol), yol)

    def test_env_ornek_degersiz(self):
        satirlar = (KOK / ".env.ornek").read_text(encoding="utf-8").splitlines()
        adlar = {}
        for s in satirlar:
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", s)
            if m:
                adlar[m.group(1)] = m.group(2).split("#")[0].strip()
        for ad in ["OKX_TR_ANA_API_KEY", "OKX_TR_ALT_SECRET_KEY", "ONCHAINOS_API_KEY",
                   "ETHERSCAN_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                   "ANTHROPIC_API_KEY", "PROOF1_FUJI_PRIVATE_KEY", "PANO_URL", "ANLATICI_KOMUT",
                   "FUJI_RPC_URL", "PROOF1_AGENT_ID", "PROOF1_SEAL_ADDRESS", "PROOF1_TUZ", "PROOF1_USD_TRY",
                   "PROOF1_KULLANICI"]:
            self.assertIn(ad, adlar)
        gizli_olmayan = ("PANO_URL", "PROOF1_DB", "ANLATICI_KOMUT", "FUJI_RPC_URL", "PROOF1_USD_TRY", "PROOF1_KULLANICI")
        for ad, deger in adlar.items():
            if ad not in gizli_olmayan:
                self.assertEqual(deger, "", f"{ad} örnekte boş olmalı")

    def test_izlenen_dosyalarda_sir_yok(self):
        izlenen = subprocess.run(["git", "ls-files"], cwd=KOK, capture_output=True,
                                 text=True, encoding="utf-8").stdout.split()
        for ad in izlenen:
            self.assertFalse(ad.startswith(".env") and ad != ".env.ornek", ad)
            self.assertFalse(ad.startswith("data/"), ad)


if __name__ == "__main__":
    unittest.main()
