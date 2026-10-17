"""Yetki ve sınırlar: proof1 yalnız okuma yetkili OKX anahtarıyla çalışır; işlem/çekim yetkili anahtarı reddeder."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from veri import ayar
from veri.atk import Atk, AtkHata, yetki_denetle
from veri.testler.ortak import canli, canli_db


class YetkiDenetimi(unittest.TestCase):
    def test_yalniz_okuma_gecer(self):
        yetki_denetle("read_only")
        yetki_denetle(" read_only ")

    def test_islem_ya_da_cekim_yetkisi_reddedilir(self):
        for perm in ("read_only,trade", "trade", "read_only,withdraw", "read_only,trade,withdraw"):
            with self.assertRaises(AtkHata) as e:
                yetki_denetle(perm)
            self.assertEqual(e.exception.kod, "yazma_yetkili_anahtar", perm)


# Sahte ATK: MCP satırlarını okur, account_get_config'e verilen yetkiyi döndürür; gördüğü ortamı ve araçları günlüğe yazar.
SAHTE_ATK = r'''
import json, os, sys
perm, gunluk = sys.argv[1], sys.argv[2]
def yaz(s):
    with open(gunluk, "a", encoding="utf-8") as f:
        f.write(s + "\n")
yaz("ortam " + json.dumps({"ev": os.environ.get("USERPROFILE"), "home": os.environ.get("HOME"),
                           "anahtar_var": bool(os.environ.get("OKX_API_KEY"))}))
for satir in sys.stdin:
    m = json.loads(satir)
    if "id" not in m:
        continue
    if m["method"] == "initialize":
        r = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "sahte"}}
    elif m["method"] == "tools/list":
        r = {"tools": [{"name": n} for n in ("account_get_config", "account_get_bills", "account_get_balance")]}
    else:
        ad = m["params"]["name"]
        yaz("arac " + ad)
        if ad == "account_get_config" and perm == "tanimadi":
            hata = {"tool": ad, "error": True, "type": "AuthenticationError", "message": "Invalid OK-ACCESS-KEY"}
            r = {"isError": True, "content": [{"type": "text", "text": json.dumps(hata, indent=2)}]}
        elif ad == "account_get_config":
            r = {"content": [{"type": "text", "text": json.dumps({"data": [{"perm": perm}]})}]}
        else:
            r = {"content": [{"type": "text", "text": json.dumps({"data": []})}]}
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}), flush=True)
'''


class MisafirAnahtari(unittest.TestCase):
    """Panodan bağlanan (misafir) anahtar: yetki okunamazsa da reddedilir, hiçbir hesap okuması yetkiden önce olmaz."""

    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dizin, True)
        self.betik = self.dizin / "sahte_atk.py"
        self.betik.write_text(SAHTE_ATK, encoding="utf-8")
        self.gunluk = self.dizin / "gunluk.txt"
        self.ev = self.dizin / "ev"
        self.ev.mkdir()
        self.kimlik = ayar.OkxKimlik("misafir", "test-key", "test-secret", "test-pass", "env", self.ev)

    def _atk(self, perm, **k):
        komut = [sys.executable, str(self.betik), perm, str(self.gunluk)]
        p = mock.patch("veri.atk.sunucu_komutu", return_value=komut)
        p.start()
        self.addCleanup(p.stop)
        return Atk(self.kimlik, None, "test-misafir", **k)

    def _araclar(self):
        satirlar = self.gunluk.read_text(encoding="utf-8").splitlines() if self.gunluk.exists() else []
        return [s.split(" ", 1)[1] for s in satirlar if s.startswith("arac ")]

    def test_yazma_yetkisi_hicbir_okumadan_once_reddedilir(self):
        with self.assertRaises(AtkHata) as e:
            self._atk("read_only,trade", yetki_zorunlu=True).baslat()
        self.assertEqual(e.exception.kod, "yazma_yetkili_anahtar")
        self.assertEqual(set(self._araclar()), {"account_get_config"})      # yetkiden başka araç çağrılmadı

    def test_yetki_okunamazsa_misafir_reddedilir(self):
        with self.assertRaises(AtkHata) as e:
            self._atk("tanimadi", yetki_zorunlu=True).baslat()
        self.assertIn("AuthenticationError", str(e.exception))
        self.assertNotIn("test-key", str(e.exception))
        self.assertEqual(set(self._araclar()), {"account_get_config"})

    def test_yetki_bos_gelirse_misafir_reddedilir(self):
        with self.assertRaises(AtkHata) as e:
            self._atk("", yetki_zorunlu=True).baslat()
        self.assertEqual(e.exception.kod, "yetki_okunamadi")

    def test_sahibin_kosusu_bugunku_gibi_gecici_hatada_durmaz(self):
        atk = self._atk("tanimadi").baslat()                     # öntanımlı: yetki_zorunlu=False
        self.addCleanup(atk.kapat)
        self.assertEqual(atk.yetki, "bilinmiyor")

    def test_okuma_yetkisiyle_acilir_ev_dizini_ayri(self):
        with self._atk("read_only", yetki_zorunlu=True) as atk:
            self.assertEqual(atk.yetki, "read_only")
        ortam = json.loads(next(s for s in self.gunluk.read_text(encoding="utf-8").splitlines()
                                if s.startswith("ortam "))[6:])
        self.assertEqual((ortam["ev"], ortam["home"]), (str(self.ev), str(self.ev)))   # sahibin ~/.okx'i okunmaz
        self.assertTrue(ortam["anahtar_var"])                                        # anahtar ortamda, diskte değil

    def test_sahibin_env_anahtarinda_ev_dizini_degismez(self):
        ortam = Atk(ayar.OkxKimlik("alt", "k", "s", "p"))._ortam()
        self.assertEqual(ortam.get("USERPROFILE"), os.environ.get("USERPROFILE"))
        self.assertEqual(ortam["OKX_API_KEY"], "k")


@canli
class CanliYetki(unittest.TestCase):
    def test_iki_hesabin_anahtari_yalniz_okuma(self):
        from veri.atk import Atk
        for hesap in ("alt", "ana"):
            with Atk(ayar.okx_kimlik(hesap), canli_db(), "test-yetki") as atk:
                self.assertEqual(atk.yetki, "read_only", hesap)


if __name__ == "__main__":
    unittest.main()
