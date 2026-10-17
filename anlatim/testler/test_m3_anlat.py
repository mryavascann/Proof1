"""M3 kabul: oturum → görevler → model (sahte istemci) → denetim → cumle ve butce tabloları."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2 as httpx  # anthropic 1.x HTTP katmanı

from anlatim import anlat, butce, kalip

ORNEK_DB = Path(__file__).resolve().parents[2] / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


def yanit(cevaplar, stop="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps({"cevaplar": cevaplar}, ensure_ascii=False))],
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=0,
                              cache_creation_input_tokens=0),
        stop_reason=stop)


def kaliptan_cevaplar(istek):
    """Her görev için olgulardan kurulan (geçerli) cevaplar üretir."""
    girdi = json.loads(istek["messages"][0]["content"])
    olgular = {o["no"]: anlat.Olgu(o["no"], o["tur"], o["alanlar"]) for o in girdi["olgular"]}
    cevaplar = []
    for g in girdi["gorevler"]:
        metin, dayanak = kalip.ozet([olgular[n] for n in g["olgular"]], g["cumle_sayisi"])
        cevaplar.append({"id": g["id"], "metin": metin, "olgular": dayanak})
    return cevaplar


class SahteIstemci:
    def __init__(self, cevapla):
        self.cevapla = cevapla
        self.cagrilar = []
        self._secenek = {}

    def with_options(self, **secenek):
        self._secenek = secenek
        return self

    @property
    def messages(self):
        return self

    def create(self, **istek):
        self.cagrilar.append((dict(self._secenek), istek))
        return self.cevapla(istek)


class Anlat(unittest.TestCase):
    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.db = self.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, self.db)

    def tearDown(self):
        shutil.rmtree(self.dizin)

    def cumleler(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM cumle WHERE oturum=? ORDER BY id", (OTURUM,))]

    def butce_satirlari(self):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute("SELECT model, girdi_parca, cikti_parca, tutar_tl, durum FROM butce").fetchall()

    def test_gecerli_cevaplar_yazilir(self):
        istemci = SahteIstemci(lambda i: yanit(kaliptan_cevaplar(i)))
        anlat.anlat(self.db, OTURUM, istemci, kullanici="bugra", ay="2026-10")
        satirlar = self.cumleler()
        self.assertTrue(satirlar)
        self.assertTrue(all(s["denetim"] == "gecti" and s["model"] == "claude-sonnet-5-5" for s in satirlar))
        yerler = [s["yer"] for s in satirlar]
        self.assertEqual(yerler.count("telegram"), 1)
        self.assertEqual(yerler.count("pano"), 1)
        self.assertIn("bant:ADRES_MOCA", yerler)
        self.assertIn("bant:Arbitrum", yerler)
        # İlk çağrı Telegram cümlesi: kısa zaman aşımı, yeniden deneme yok.
        self.assertEqual(istemci.cagrilar[0][0], {"timeout": anlat.TELEGRAM_ZAMAN_ASIMI, "max_retries": 0})
        self.assertLessEqual(anlat.TELEGRAM_ZAMAN_ASIMI, 5)
        b = self.butce_satirlari()
        self.assertEqual(len(b), 2)
        self.assertTrue(all(Decimal(r[3]) > 0 and r[4] == "ok" for r in b))

    def test_istek_bicimi(self):
        istemci = SahteIstemci(lambda i: yanit(kaliptan_cevaplar(i)))
        anlat.anlat(self.db, OTURUM, istemci, kullanici="bugra", ay="2026-10")
        istek = istemci.cagrilar[0][1]
        self.assertEqual(istek["model"], "claude-sonnet-5-5")
        self.assertEqual(istek["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(istek["thinking"], {"type": "between_tools"})
        self.assertEqual(istek["output_config"]["effort"], "low")
        self.assertEqual(istek["output_config"]["format"]["type"], "json_schema")
        self.assertNotIn("temperature", istek)

    def test_gizli_olgu_modele_gitmez(self):
        istemci = SahteIstemci(lambda i: yanit(kaliptan_cevaplar(i)))
        anlat.anlat(self.db, OTURUM, istemci, kullanici="bugra", ay="2026-10")
        for _, istek in istemci.cagrilar:
            govde = istek["messages"][0]["content"]
            self.assertNotIn("360 $", govde)
            self.assertNotIn("kalan_ozet", govde)
            self.assertNotIn('"o2"', govde)

    def test_yanlis_sayi_kaliba_doner_ve_saklanmaz(self):
        def cevapla(i):
            c = kaliptan_cevaplar(i)
            for x in c:
                if x["id"] == "telegram":
                    x["metin"] = "Paranın %77,3'ü Arbitrum ve Ethereum'a gitti."
            return yanit(c)
        anlat.anlat(self.db, OTURUM, SahteIstemci(cevapla), kullanici="bugra", ay="2026-10")
        tg = [s for s in self.cumleler() if s["yer"] == "telegram"][0]
        self.assertEqual((tg["model"], tg["denetim"]), ("kalip", "kalip"))
        self.assertIn("+99,89 TL", tg["metin"])
        self.assertFalse(any("77,3" in s["metin"] for s in self.cumleler()))

    def test_zaman_asimi_kalip(self):
        def cevapla(i):
            if "telegram" in i["messages"][0]["content"] and '"pano"' not in i["messages"][0]["content"]:
                raise anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com"))
            return yanit(kaliptan_cevaplar(i))
        anlat.anlat(self.db, OTURUM, SahteIstemci(cevapla), kullanici="bugra", ay="2026-10")
        tg = [s for s in self.cumleler() if s["yer"] == "telegram"][0]
        self.assertEqual(tg["denetim"], "kalip")
        self.assertIn(("zaman_asimi",), [(r[4],) for r in self.butce_satirlari()])

    def test_ret_kalip(self):
        istemci = SahteIstemci(lambda i: yanit(kaliptan_cevaplar(i), stop="refusal"))
        anlat.anlat(self.db, OTURUM, istemci, kullanici="bugra", ay="2026-10")
        self.assertTrue(all(s["denetim"] == "kalip" for s in self.cumleler()))

    def test_tavan_doluysa_model_cagrilmaz(self):
        with closing(sqlite3.connect(self.db)) as db:
            butce.yaz(db, "bugra", "2026-10", "claude-sonnet-5-5", 0, 0, Decimal("35"), "ok")
        istemci = SahteIstemci(lambda i: self.fail("model çağrılmamalı"))
        anlat.anlat(self.db, OTURUM, istemci, kullanici="bugra", ay="2026-10")
        self.assertEqual(istemci.cagrilar, [])
        satirlar = self.cumleler()
        self.assertTrue(satirlar and all(s["model"] == "kalip" for s in satirlar))
        self.assertIn("tavan", [r[4] for r in self.butce_satirlari()])

    def test_istemci_yoksa_kalip(self):
        anlat.anlat(self.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        self.assertTrue(all(s["model"] == "kalip" for s in self.cumleler()))

    def test_ayni_banttaki_iki_olgu_korunur(self):
        anlat.anlat(self.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        moca = [s["metin"] for s in self.cumleler() if s["yer"] == "bant:ADRES_MOCA"]
        self.assertEqual(len(moca), 2)
        self.assertTrue(any("46,15 PIEVERSE verip 1.587 MOCA aldın; ağ ücreti 0,000129 ETH" in m for m in moca))

    def test_tekrar_calisinca_cogaltmaz(self):
        for _ in range(2):
            anlat.anlat(self.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        yerler = [s["yer"] for s in self.cumleler()]
        self.assertEqual(yerler.count("telegram"), 1)


if __name__ == "__main__":
    unittest.main()
