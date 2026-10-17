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
        self.assertIn("bant:Ethereum", yerler)
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
        with closing(sqlite3.connect(self.db)) as db:
            gizliler = [no for (no,) in db.execute("SELECT no FROM olgu WHERE oturum=? AND gizli=1", (OTURUM,))]
        self.assertTrue(gizliler)
        for _, istek in istemci.cagrilar:
            govde = istek["messages"][0]["content"]
            self.assertNotIn("kalan_ozet", govde)
            for no in gizliler:
                self.assertNotIn(f'"{no}"', govde)

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
        eth = [s["metin"] for s in self.cumleler() if s["yer"] == "bant:Ethereum"]
        self.assertGreaterEqual(len(eth), 2)
        self.assertTrue(any("46,15 PIEVERSE verip 1.587 MOCA aldın" in m for m in eth))

    def test_tekrar_calisinca_cogaltmaz(self):
        for _ in range(2):
            anlat.anlat(self.db, OTURUM, None, kullanici="bugra", ay="2026-10")
        yerler = [s["yer"] for s in self.cumleler()]
        self.assertEqual(yerler.count("telegram"), 1)


if __name__ == "__main__":
    unittest.main()


class GorevSecimi(unittest.TestCase):
    """Buğra'nın provası: Telegram cümlesi gerçek veride yavaştı ve kalıba düştü; pano başlığı bot ile ilgisiz bir
    girişi aynı cümlede birleştiriyordu. Telegram ve pano görevleri yalnız en önemli olguyu alır."""

    def olgu(self, no, tur, gizli=False, **alanlar):
        return anlat.Olgu(no, tur, alanlar, gizli)

    def test_bot_varsa_telegram_ve_pano_yalniz_bot(self):
        olgular = [self.olgu("o1", "cekim_ozet", donem="x", borsa="OKX TR", adres_sayisi="3", cekim_sayisi="4",
                             toplam_dolar="5 $"),
                   self.olgu("o2", "taninmadi", tarih="25 Şubat 2025 10:29", miktar="1 USDT0"),
                   self.olgu("o3", "bot_uyusmazlik", bot="USDT/TRY spot grid", kayit_sonuc="+99,89 TL",
                             gercek_sonuc="-0,22 TL")]
        g = {x["id"]: x for x in anlat.gorevler(olgular)}
        self.assertEqual(g["telegram"]["olgular"], ["o3"])
        self.assertEqual(g["pano"]["olgular"], ["o3"])
        self.assertEqual(g["pano"]["cumle_sayisi"], 1)

    def test_bot_yoksa_ozet_olgulari(self):
        olgular = [self.olgu("o1", "cekim_ozet", donem="x", borsa="OKX TR", adres_sayisi="3", cekim_sayisi="4",
                             toplam_dolar="5 $"),
                   self.olgu("o2", "taninmadi", tarih="25 Şubat 2025 10:29", miktar="1 USDT0"),
                   self.olgu("o4", "supheli", tarih="1 Mart 2025", miktar="1 X")]
        g = {x["id"]: x for x in anlat.gorevler(olgular)}
        self.assertEqual(g["telegram"]["olgular"], ["o1"])
        self.assertNotIn("o2", g["pano"]["olgular"])

    def test_telegram_istegi_kucuk(self):
        dizin = Path(tempfile.mkdtemp())
        try:
            db = dizin / "proof1.db"
            shutil.copy(ORNEK_DB, db)
            istemci = SahteIstemci(lambda i: yanit(kaliptan_cevaplar(i)))
            anlat.anlat(db, OTURUM, istemci, kullanici="bugra", ay="2026-10")
            girdi = json.loads(istemci.cagrilar[0][1]["messages"][0]["content"])
            self.assertLessEqual(len(girdi["olgular"]), 3)
            self.assertEqual([g["id"] for g in girdi["gorevler"]], ["telegram"])
        finally:
            shutil.rmtree(dizin)

    def test_denetim_nedeni_gunluge_ham_cumle_yok(self):
        import os
        dizin = Path(tempfile.mkdtemp())
        try:
            db, gunluk = dizin / "proof1.db", dizin / "anlatici.jsonl"
            shutil.copy(ORNEK_DB, db)

            def cevapla(i):
                c = kaliptan_cevaplar(i)
                for x in c:
                    x["metin"] = "Paranın %77,3'ü bir yere gitti."
                return yanit(c)
            os.environ["PROOF1_ANLATICI_GUNLUK"] = str(gunluk)
            try:
                anlat.anlat(db, OTURUM, SahteIstemci(cevapla), kullanici="bugra", ay="2026-10")
            finally:
                os.environ.pop("PROOF1_ANLATICI_GUNLUK", None)
            satirlar = [json.loads(s) for s in gunluk.read_text(encoding="utf-8").splitlines()]
            tg = next(s for s in satirlar if s["gorev"] == "telegram")
            self.assertEqual(tg["sonuc"], "kalip")
            self.assertIn("olgularda yok", tg["neden"])
            self.assertIn("sure_ms", tg)
            self.assertNotIn("77,3", gunluk.read_text(encoding="utf-8").replace(tg["neden"], ""))
        finally:
            shutil.rmtree(dizin)
