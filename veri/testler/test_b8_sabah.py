"""B8 kabul: sabah işinin son adımı. Cümle `cumle` tablosundan ya da kalıptan; anlatıcı 5 sn'de dönmezse kalıp;
gizli değer mesaja girmez; mesaj tek cümle + “Panoyu aç”."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from calistir.sabah import mesaj_hazirla
from calistir.telegram import Telegram
from veri import db as dbm
from veri.olgu import OlguYazici


class SahteHttp:
    def __init__(self, durum=200):
        self.istekler = []
        self.durum = durum

    def post(self, url, json=None, timeout=None):
        self.istekler.append((url, json))
        sahte = self

        class C:
            status_code = sahte.durum if len(sahte.istekler) == 1 else 200
            ok = status_code == 200

            def json(self_):
                return {"ok": self_.ok, "result": {"message_id": 7}} if self_.ok else {"ok": False, "description": "Bad Request"}
        return C()


def _db():
    db = dbm.baglan(":memory:")
    y = OlguYazici(db, "sabah-x")
    y.ekle("kopru_ozet", {"kapsam": "servet", "ad": "toplam servet", "degisim": "-0,19 $", "donem": "dün 09:00 → bugün 09:00"})
    y.ekle("kalan_ozet", {"adres_sayisi": "10", "dolar": "360 $"}, gizli=True)
    return db


SAHTE_ANLATICI = '''import sqlite3, sys
d = sqlite3.connect(sys.argv[1])
d.execute("CREATE TABLE IF NOT EXISTS cumle (id INTEGER PRIMARY KEY, oturum, olgular, metin, model, denetim, yer, zaman)")
d.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer) VALUES (?,?,?,?,?,?)",
          (sys.argv[2], '["o1"]', "Dünden bugüne servetin -0,19 $ değişti; ücretler yüzünden.", "claude-sonnet-5-5", "gecti", "telegram"))
d.commit()
'''


class Mesaj(unittest.TestCase):
    def test_anlatici_yoksa_kalip(self):
        db = _db()
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut="", pano_url="http://localhost:3003")
        self.assertEqual(m.kaynak, "kalip")
        self.assertIn("-0,19 $", m.metin)
        self.assertIn("http://localhost:3003/?oturum=sabah-x", m.baglanti)

    def test_anlatici_cumlesi_kullanilir(self):
        import tempfile
        dizin = tempfile.mkdtemp()
        yol = os.path.join(dizin, "t.db")
        betik = os.path.join(dizin, "anlatici.py")
        with open(betik, "w", encoding="utf-8") as f:
            f.write(SAHTE_ANLATICI)
        db = dbm.baglan(yol)
        OlguYazici(db, "sabah-x").ekle("kopru_ozet", {"kapsam": "servet", "degisim": "-0,19 $"})
        komut = f'"{sys.executable}" "{betik}" "{yol}" {{oturum}}'
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut=komut, pano_url="http://p")
        self.assertEqual(m.kaynak, "claude-sonnet-5-5")
        self.assertTrue(m.metin.startswith("Dünden bugüne"))

    def test_anlatici_gec_kalirsa_kalip(self):
        db = _db()
        yavas = f'"{sys.executable}" -c "import time; time.sleep(8)"'
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut=yavas, pano_url="http://p", zaman_asimi=1)
        self.assertEqual(m.kaynak, "kalip")

    def test_gizli_deger_sizarsa_kalip(self):
        db = _db()
        db.execute("CREATE TABLE IF NOT EXISTS cumle (id INTEGER PRIMARY KEY, oturum TEXT, olgular TEXT, metin TEXT, model TEXT, denetim TEXT, yer TEXT, zaman TEXT)")
        db.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer) VALUES ('sabah-x','[\"o2\"]','10 adreste 360 $ duruyor.','m','gecti','telegram')")
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut="", pano_url="http://p")
        self.assertEqual(m.kaynak, "kalip")
        self.assertNotIn("360", m.metin)


ONCE_TELEGRAM_SONRA_PANO = '''import sqlite3, sys, time
d = sqlite3.connect(sys.argv[1])
d.execute("CREATE TABLE IF NOT EXISTS cumle (id INTEGER PRIMARY KEY, oturum, olgular, metin, model, denetim, yer, zaman)")
time.sleep(0.3)
d.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer) VALUES (?,?,?,?,?,?)",
          (sys.argv[2], '["o1"]', "Telegram cümlesi.", "claude-sonnet-5-5", sys.argv[3], "telegram")); d.commit()
time.sleep(1.5)
d.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer) VALUES (?,?,?,?,?,?)",
          (sys.argv[2], '["o1"]', "Pano cümlesi.", "claude-sonnet-5-5", "gecti", "pano")); d.commit()
'''


class AnlaticiZamanlama(unittest.TestCase):
    def _hazirla(self, denetim="gecti"):
        import tempfile
        import time
        dizin = tempfile.mkdtemp()
        yol, betik = os.path.join(dizin, "t.db"), os.path.join(dizin, "a.py")
        with open(betik, "w", encoding="utf-8") as f:
            f.write(ONCE_TELEGRAM_SONRA_PANO)
        db = dbm.baglan(yol)
        OlguYazici(db, "s").ekle("kopru_ozet", {"kapsam": "servet", "degisim": "1 $"})
        bas = time.monotonic()
        m = mesaj_hazirla(db, "s", f'"{sys.executable}" "{betik}" "{yol}" {{oturum}} {denetim}', "http://p")
        return db, m, time.monotonic() - bas

    def test_telegram_cumlesi_gelince_beklemeden_devam(self):
        import time
        db, m, sure = self._hazirla()
        self.assertEqual(m.metin, "Telegram cümlesi.")
        self.assertLess(sure, 1.5)                                   # pano cümlesini beklemedi
        time.sleep(2.5)
        pano = db.execute("SELECT COUNT(*) FROM cumle WHERE yer='pano'").fetchone()[0]
        self.assertEqual(pano, 1, "anlatıcı öldürülmemeli; pano cümleleri sonra da yazılabilmeli")

    def test_anlaticinin_kalibi_yerine_bizim_kalip(self):
        # Anlatıcının modeli denetimden geçemeyip kalıba düştüyse kendi kalıbımız (devir metnindeki biçim) gider.
        db, m, _ = self._hazirla(denetim="kalip")
        self.assertEqual(m.kaynak, "kalip")
        self.assertNotEqual(m.metin, "Telegram cümlesi.")


class YalnizGonder(unittest.TestCase):
    def test_hazir_olgulardan_gonderir(self):
        from calistir.sabah import hazir_gonder

        class T:
            hazir = True
            gonderilen = []

            def gonder_pano(self, metin, baglanti):
                self.gonderilen.append((metin, baglanti))
                return {"message_id": 3}
        db = _db()
        t = T()
        m, ok = hazir_gonder(db, "sabah-x", t, anlatici_komut="", pano_url="http://localhost:3003")
        self.assertTrue(ok)
        self.assertIn("0,19 $", t.gonderilen[0][0])
        self.assertTrue(t.gonderilen[0][1].endswith("oturum=sabah-x"))


class TelegramGonder(unittest.TestCase):
    def test_html_baglanti_reddedilirse_duz_metin(self):
        http = SahteHttp(durum=400)
        t = Telegram("123:ABC", "42", http=http)
        sonuc = t.gonder_pano("Merhaba.", "http://localhost:3003/?oturum=x")
        self.assertTrue(sonuc)
        self.assertEqual(len(http.istekler), 2)
        self.assertIn("parse_mode", http.istekler[0][1])
        self.assertNotIn("parse_mode", http.istekler[1][1])
        self.assertIn("Panoyu aç: http://localhost:3003/?oturum=x", http.istekler[1][1]["text"])

    def test_cagri_kaydinda_token_yok(self):
        db = dbm.baglan(":memory:")
        Telegram("123:GIZLITOKEN", "42", db=db, http=SahteHttp()).gonder("x")
        r = db.execute("SELECT ad, parametreler FROM cagri").fetchone()
        self.assertEqual(r["ad"], "sendMessage")
        self.assertNotIn("GIZLITOKEN", r["parametreler"])


# ---------------------------------------------------------------- sabah işinin tamamı (sahte OKX ve ATK ile)
GUN = "2026-10-17"
BIT_MS = 1792216800000                     # 17 Ekim 2026 09:00 İstanbul
FATURA = {"billId": "b1", "ts": str(BIT_MS - 3_600_000), "ccy": "USDT", "balChg": "1", "bal": "5", "type": "1"}


class SahteOkx:
    olaylar: list = []
    hatali_uc: str | None = None

    def __init__(self, kimlik, db=None, oturum=None, oturum_http=None):
        self.k = kimlik
        self.olaylar.append(("okx", kimlik.hesap))

    def oku(self, yol, parametreler=None, alanlar=None):
        from veri.okx_imzali import OkxHata
        self.olaylar.append(("okx_oku", yol))
        if yol == self.hatali_uc:
            raise OkxHata("50111", "Invalid OK-ACCESS-KEY")
        return {"/api/v5/asset/balances": [{"ccy": "USDT", "bal": "10"}],
                "/api/v5/account/balance": [{"details": [{"ccy": "USDT", "cashBal": "5"}]}]}.get(yol, [])

    def sayfala(self, yol, parametreler=None, alanlar=None, **_):
        return self.oku(yol, parametreler, alanlar)


class SahteAtk:
    """veri.atk.Atk yerine: başlarken (gerçekte account_get_config → yetki_denetle) istenirse reddeder."""
    olaylar: list = []
    reddet = False

    def __init__(self, kimlik, db=None, oturum=None, yetki_denetimi=True, yetki_zorunlu=False):
        self.k = kimlik
        self.olaylar.append(("atk", kimlik.hesap, yetki_zorunlu))
        self.araclar = ["account_get_config"]

    def __enter__(self):
        from veri.atk import AtkHata
        self.olaylar.append(("atk_baslat", self.k.hesap))
        if self.reddet:
            raise AtkHata("yazma_yetkili_anahtar", "anahtar şu yetkileri taşıyor: trade")
        return self

    def __exit__(self, *a):
        self.olaylar.append(("atk_kapat", self.k.hesap))

    def cagir(self, arac, argumanlar=None, alanlar=None):
        self.olaylar.append(("atk_cagir", arac))
        return {"data": {"account_get_bills": [FATURA],
                         "account_get_asset_balance": [{"ccy": "USDT", "bal": "1"}],
                         "account_get_balance": [{"details": [{"ccy": "USDT", "cashBal": "2"}]}]}.get(arac, [])}


class SabahIsi(unittest.TestCase):
    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.olaylar = []
        SahteOkx.olaylar = SahteAtk.olaylar = self.olaylar
        SahteOkx.hatali_uc, SahteAtk.reddet = None, False
        self.isaret = self.dizin / "anlatici_calisti.txt"
        betik = self.dizin / "anlatici.py"
        betik.write_text(f"open(r'{self.isaret}', 'w').close()\n", encoding="utf-8")
        for hedef, deger in (("veri.atk.Atk", SahteAtk), ("veri.okx_imzali.OkxTr", SahteOkx),
                             ("veri.ayar.env_yukle", lambda *a: None)):
            p = mock.patch(hedef, deger)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"ANLATICI_KOMUT": f'"{sys.executable}" "{betik}"'})
        p.start()
        self.addCleanup(p.stop)
        from veri import ayar
        self.misafir = ayar.OkxKimlik("misafir", "test-key", "test-secret", "test-pass")

    def tearDown(self):
        shutil.rmtree(self.dizin, ignore_errors=True)

    def _misafir(self, **k):
        from calistir import sabah
        etiketler = []
        k = {"gun": GUN, "gonder": False, "hafta": False, "kimlik": self.misafir, "db_yolu": self.dizin / "m.db",
             "anlatici": False, "ilerleme": etiketler.append, **k}
        return sabah.calistir(**k), etiketler

    def test_misafir_tek_hesap_iki_kez_sayilmaz(self):
        from calistir import sabah

        class TelegramYok:
            def __init__(self, *a, **k):
                raise AssertionError("misafir taraması Telegram'a yazmamalı")
        with mock.patch("calistir.telegram.Telegram", TelegramYok):
            sonuc, etiketler = self._misafir()
        self.assertEqual(etiketler, list(sabah.ILERLEME[:5]))
        self.assertEqual([o for o in self.olaylar if o[0] == "atk"], [("atk", "misafir", True)])   # tek ATK, yetki zorunlu
        ilk_okuma = next(i for i, o in enumerate(self.olaylar) if o[0] in ("okx_oku", "atk_cagir"))
        self.assertLess(self.olaylar.index(("atk_baslat", "misafir")), ilk_okuma)               # önce yetki denetimi
        cagrilan = {o[1] for o in self.olaylar if o[0] == "atk_cagir"}
        self.assertFalse(cagrilan & {"account_get_balance", "account_get_asset_balance"})       # borsa:alt okunmadı
        self.assertEqual((sonuc["kaynak"], sonuc["gonderildi"]), ("kalip", False))
        self.assertFalse(self.isaret.exists(), "ücretli anlatıcı (ANLATICI_KOMUT) çalışmamalı")
        db = sqlite3.connect(self.dizin / "m.db")
        self.addCleanup(db.close)
        self.assertEqual(db.execute("SELECT hesap, ham_kimlik FROM hareket WHERE kaynak_okuma='account_get_bills'").fetchall(),
                         [("ana", "account_get_bills:ana:b1")])                                 # bir kez, ana adıyla
        self.assertEqual(db.execute("SELECT yer, miktar FROM fotograf WHERE gun=?", (GUN,)).fetchall(),
                         [("borsa:ana", "15")])

    def test_misafir_dosyasi_kapanir(self):
        self._misafir()
        (self.dizin / "m.db").rename(self.dizin / "tasindi.db")                 # açık bağlantı kalsaydı Windows'ta düşerdi
        self.assertFalse((self.dizin / "m.db-wal").exists())

    def test_yazma_yetkili_anahtar_hicbir_sey_okunmadan_durur(self):
        from veri.atk import AtkHata
        SahteAtk.reddet = True
        with self.assertRaises(AtkHata) as e:
            self._misafir()
        self.assertEqual(e.exception.kod, "yazma_yetkili_anahtar")
        self.assertFalse([o for o in self.olaylar if o[0] in ("okx_oku", "atk_cagir")])
        (self.dizin / "m.db").unlink()                                           # bağlantı kapandı

    def test_misafirde_borsa_okunamazsa_hata_yukselir(self):
        from veri.okx_imzali import OkxHata
        SahteOkx.hatali_uc = "/api/v5/asset/withdrawal-history"
        with self.assertRaises(OkxHata) as e:
            self._misafir()
        self.assertEqual(e.exception.kod, "50111")

    def test_misafir_telegram_ya_da_anlatici_isteyemez(self):
        for k in ({"gonder": True}, {"anlatici": True}):
            with self.subTest(k=k), self.assertRaises(ValueError):
                self._misafir(**k)
        self.assertEqual(self.olaylar, [])
        self.assertFalse((self.dizin / "m.db").exists())

    def test_sahibin_kosusu_bugunku_gibi(self):
        from calistir import sabah
        from veri import ayar
        gercek = dbm.baglan
        acilan = []

        def baglan(yol=None):
            acilan.append(yol)
            return gercek(":memory:" if yol is None else yol)

        class TelegramHazirDegil:
            kuruldu = 0
            hazir = False

            def __init__(self, *a, **k):
                TelegramHazirDegil.kuruldu += 1
        with mock.patch("veri.ayar.okx_kimlik", lambda hesap: ayar.OkxKimlik(hesap, f"k-{hesap}", "s", "p")), \
                mock.patch("veri.db.baglan", baglan), mock.patch("calistir.telegram.Telegram", TelegramHazirDegil):
            s = sabah.calistir(GUN, gonder=True, hafta=False)
        self.assertEqual(acilan, [None])                                         # öntanımlı veri dosyası
        self.assertEqual([o for o in self.olaylar if o[0] == "atk"], [("atk", "alt", False), ("atk", "ana", False)])
        self.assertIn(("okx", "ana"), self.olaylar)
        self.assertIn(("atk_cagir", "account_get_balance"), self.olaylar)        # borsa:alt okunur
        self.assertEqual(TelegramHazirDegil.kuruldu, 1)
        self.assertTrue(self.isaret.exists(), "sahibin anlatıcısı çalışmalı")
        self.assertIn("alt hesap defteri: 1 satır, bakiye farkı 0", s["gunluk"])


if __name__ == "__main__":
    unittest.main()
