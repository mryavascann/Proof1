"""M5 kabul: araştıran anlatıcı ve iz kaydı. Kayıtlı ATK yanıtlarıyla (16 Ekim USDT/TRY botu)."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from anlatim import arastir, butce

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"


def arac_cagrisi(ad, girdi, kimlik):
    return SimpleNamespace(type="tool_use", name=ad, input=girdi, id=kimlik)


def yanit(bloklar, stop="tool_use"):
    return SimpleNamespace(content=bloklar, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=900, output_tokens=120, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0))


class SahteIstemci:
    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.istekler = []

    def with_options(self, **_):
        return self

    @property
    def messages(self):
        return self

    def create(self, **istek):
        self.istekler.append(dict(istek, messages=list(istek["messages"])))  # çağrı anındaki görüntü
        return self.yanitlar.pop(0)


class Arastir(unittest.TestCase):
    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.db = self.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, self.db)
        self.araclar = arastir.KayitliAraclar(KOK / "anlatim" / "kayit" / "bot_16_ekim.json")

    def tearDown(self):
        shutil.rmtree(self.dizin)

    def iz(self, iz_no):
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM iz WHERE iz_no=? ORDER BY sira", (iz_no,))]

    def test_plan_ile_iz_hedef_arac_gozlem_karar_sonuc(self):
        iz_no = arastir.arastir(self.db, OTURUM, self.araclar, istemci=None)
        adimlar = self.iz(iz_no)
        self.assertIn("tutuyor mu", adimlar[0]["hedef"])
        araclar = [a["arac"] for a in adimlar]
        self.assertEqual(araclar[:3], ["grid_get_order_details [kayıt]", "grid_get_sub_orders [kayıt]",
                                       "account_get_bills [kayıt]"])
        detay, alt, defter, son = adimlar[0], adimlar[1], adimlar[2], adimlar[-1]
        self.assertIn("+99,89 TL", detay["gozlem"])
        self.assertIn("coinleri tut", detay["gozlem"])
        self.assertTrue(alt["sonuc"].startswith("hata"))          # başarısız çağrı da kayıtta
        self.assertIn("devam", alt["karar"])                       # ve sonrasında ne yapıldığı
        self.assertIn("−300 TL", defter["gozlem"])
        self.assertIn("199,6673813 TL", defter["gozlem"])
        self.assertIn("2,02782894 USDT", defter["gozlem"])
        self.assertIn("iki kez sayılmış gibi", son["karar"])
        self.assertIn("+99,89 TL diyor", son["sonuc"])
        self.assertIn("-0,22 TL", son["sonuc"])

    def test_iz_sozlesme_sutunlari(self):
        arastir.arastir(self.db, OTURUM, self.araclar, istemci=None)
        with closing(sqlite3.connect(self.db)) as db:
            sutunlar = [r[1] for r in db.execute("PRAGMA table_info(iz)")]
        self.assertEqual(sutunlar, ["iz_no", "oturum", "hedef", "sira", "dusunce", "arac", "gozlem", "karar", "sonuc",
                                    "zaman"])

    def test_yalniz_okuma_araclari(self):
        for ad in ("grid_stop_order", "grid_create_order", "account_transfer", "spot_place_order"):
            with self.assertRaises(arastir.AracYasak):
                self.araclar.cagir(ad, {})

    def test_canli_araclar_yasak_araci_atkya_iletmez(self):
        cagrilan = []
        sahte_atk = SimpleNamespace(cagir=lambda ad, arg=None, alanlar=None: cagrilan.append(ad) or {"data": []})
        canli = arastir.CanliAraclar(sahte_atk)
        with self.assertRaises(arastir.AracYasak):
            canli.cagir("grid_stop_order", {"algoId": "1"})
        self.assertEqual(cagrilan, [])
        canli.cagir("grid_get_order_details", {"algoId": "1"})
        self.assertEqual(cagrilan, ["grid_get_order_details"])

    def test_model_dongusu(self):
        istemci = SahteIstemci([
            yanit([arac_cagrisi("grid_get_order_details", {"gerekce": "Önce botun kaydının ne dediğine bakıyorum."}, "t1")]),
            yanit([arac_cagrisi("account_get_bills", {"gerekce": "Bota giren ve hesaba dönen parayı defterden okuyorum."}, "t2")]),
            yanit([arac_cagrisi("karar_ver", {"karar": "iki_kez_sayilmis",
                                              "gerekce": "Kayıttaki kâr, elde kalan coinin değerine denk geliyor."}, "t3")]),
        ])
        iz_no = arastir.arastir(self.db, OTURUM, self.araclar, istemci=istemci, kullanici="bugra", ay="2026-10")
        adimlar = self.iz(iz_no)
        self.assertEqual(adimlar[0]["dusunce"], "Önce botun kaydının ne dediğine bakıyorum.")
        self.assertEqual(adimlar[1]["arac"], "account_get_bills [kayıt]")
        self.assertIn("iki kez sayılmış gibi", adimlar[-1]["karar"])
        araclar = {t["name"] for t in istemci.istekler[0]["tools"]}
        self.assertEqual(araclar, set(arastir.IZINLI) | {"karar_ver"})
        self.assertNotIn("tool_choice", istemci.istekler[0])
        # Araç sonucu modele kodun özeti olarak döner; sayılar koddan.
        sonuc = istemci.istekler[1]["messages"][-1]["content"][0]
        self.assertEqual(sonuc["type"], "tool_result")
        self.assertIn("+99,89 TL", sonuc["content"])

    def test_model_kararini_kod_dogrular(self):
        istemci = SahteIstemci([
            yanit([arac_cagrisi("account_get_bills", {"gerekce": "Defteri okuyorum."}, "t1")]),
            yanit([arac_cagrisi("karar_ver", {"karar": "tutuyor", "gerekce": "Kayıt doğru görünüyor."}, "t2")]),
        ])
        iz_no = arastir.arastir(self.db, OTURUM, self.araclar, istemci=istemci, kullanici="bugra", ay="2026-10")
        son = self.iz(iz_no)[-1]
        self.assertIn("kodla doğrulanamadı", son["karar"])
        self.assertIn("iki kez sayılmış gibi", son["karar"])

    def test_sayili_gerekce_gosterilmez(self):
        istemci = SahteIstemci([
            yanit([arac_cagrisi("grid_get_order_details", {"gerekce": "Kayıt 99,89 TL kâr diyor."}, "t1")]),
            yanit([arac_cagrisi("karar_ver", {"karar": "iki_kez_sayilmis", "gerekce": "Fark var."}, "t2")]),
        ])
        iz_no = arastir.arastir(self.db, OTURUM, self.araclar, istemci=istemci, kullanici="bugra", ay="2026-10")
        self.assertNotIn("99,89", self.iz(iz_no)[0]["dusunce"])

    def test_yasak_araci_isteyen_model_reddedilir(self):
        istemci = SahteIstemci([
            yanit([arac_cagrisi("grid_stop_order", {"gerekce": "Botu durdurayım."}, "t1")]),
            yanit([arac_cagrisi("karar_ver", {"karar": "belirsiz", "gerekce": "Okuyamadım."}, "t2")]),
        ])
        iz_no = arastir.arastir(self.db, OTURUM, self.araclar, istemci=istemci, kullanici="bugra", ay="2026-10")
        ilk = self.iz(iz_no)[0]
        self.assertEqual(ilk["sonuc"], "reddedildi: salt okuma dışı araç")

    def test_tavan_doluysa_plan(self):
        with closing(sqlite3.connect(self.db)) as db:
            butce.yaz(db, "bugra", "2026-10", butce.SONNET, 0, 0, Decimal("35"), "ok")
        istemci = SahteIstemci([])
        iz_no = arastir.arastir(self.db, OTURUM, self.araclar, istemci=istemci, kullanici="bugra", ay="2026-10")
        self.assertEqual(istemci.istekler, [])
        self.assertIn("plan", self.iz(iz_no)[0]["dusunce"].lower())

    def bos_araclar(self):
        bos = arastir.KayitliAraclar.__new__(arastir.KayitliAraclar)
        bos.algo_id, bos.yanitlar, bos.etiket = None, {}, "kayıt"
        return bos

    def test_bot_kimligi_yoksa_durust(self):
        with closing(sqlite3.connect(self.db)) as db:  # örnek veride artık algoId var; yokluğu canlandırılır
            db.execute("UPDATE olgu SET alanlar=json_remove(alanlar, '$.algoId') WHERE tur='bot_uyusmazlik'")
            db.commit()
        iz_no = arastir.arastir(self.db, OTURUM, self.bos_araclar(), istemci=None)
        adimlar = self.iz(iz_no)
        self.assertEqual(len(adimlar), 1)
        self.assertIn("bot kimliği", adimlar[0]["sonuc"])

    def test_olgudaki_algoId_kullanilir(self):
        with closing(sqlite3.connect(self.db)) as db:
            r = db.execute("SELECT json_extract(alanlar, '$.algoId') FROM olgu WHERE oturum=? AND tur='bot_uyusmazlik'",
                           (OTURUM,)).fetchone()
        if not r or not r[0]:
            self.skipTest("örnek olguda algoId yok")
        araclar, gelen = self.bos_araclar(), []
        araclar.cagir = lambda arac, arg: gelen.append(arg) or (_ for _ in ()).throw(arastir.AracHatasi("kayit_yok", "kayıtlı yanıt yok"))
        iz_no = arastir.arastir(self.db, OTURUM, araclar, istemci=None)
        self.assertNotIn("bot kimliği", self.iz(iz_no)[0]["sonuc"] or "")
        grid = [a for a in gelen if a.get("algoOrdType") == "grid"]  # account_get_bills bot kimliği almaz
        self.assertTrue(grid and all(a["algoId"] == r[0] for a in grid))


if __name__ == "__main__":
    unittest.main()


class AnlaticiyaBagli(unittest.TestCase):
    def test_proof1_arastir_kayit_ile_anlatici_izi_de_yazar(self):
        import os
        from anlatim import anlat
        dizin = Path(tempfile.mkdtemp())
        try:
            db = dizin / "proof1.db"
            shutil.copy(ORNEK_DB, db)
            eski = {k: os.environ.get(k) for k in ("PROOF1_DB", "PROOF1_ARASTIR", "ANTHROPIC_API_KEY")}
            os.environ.update(PROOF1_DB=str(db), PROOF1_ARASTIR="kayit", ANTHROPIC_API_KEY="")
            try:
                anlat.ana(["--oturum", OTURUM])
            finally:
                for k, v in eski.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            with closing(sqlite3.connect(db)) as c:
                self.assertGreater(c.execute("SELECT count(*) FROM iz WHERE oturum=?", (OTURUM,)).fetchone()[0], 0)
                self.assertEqual(c.execute("SELECT count(*) FROM cumle WHERE yer='telegram'").fetchone()[0], 1)
        finally:
            shutil.rmtree(dizin)
