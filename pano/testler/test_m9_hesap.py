"""M9 kabul: kendi OKX TR hesabını panodan bağlama (salt okuma anahtarı, yalnız bu bilgisayardan).

Gerçek tarama (calistir.sabah) burada sahtesiyle değiştirilir; tarama tarafı veri/testler/test_b8_sabah.py ve
test_yetki.py'de sınanır. Anahtar değeri hiçbir cevapta, iletide ya da dosyada görünmez.
"""
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from unittest import mock

from calistir.sabah import ILERLEME
from pano import hesap, sunucu, veri
from veri.atk import AtkHata
from veri.okx_imzali import OkxHata

KOK = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"
YAZMA = "Bu anahtarın işlem ya da çekim yetkisi var. proof1 yalnız “Okuma” yetkili anahtarla çalışır."
TANIMADI = "OKX anahtarı tanımadı: anahtar, gizli anahtar ya da parola yanlış."
ANAHTAR = {"api_key": "test-key", "secret_key": "test-secret", "passphrase": "test-pass"}
ATK_KIMLIK_HATASI = ('{\n  "tool": "account_get_config",\n  "error": true,\n  "type": "AuthenticationError",\n'
                     '  "message": "Invalid OK-ACCESS-KEY"')


class SahteTarama:
    """calistir.sabah yerine: adımları bildirir, örnek veriyi yazar ya da istenen hatayı yükseltir."""

    def __init__(self, hata=None, bekle=None, cumle_sil=False):
        self.hata, self.bekle, self.cumle_sil = hata, bekle, cumle_sil
        self.kimlikler, self.evler = [], []

    def __call__(self, kimlik, db_yolu, ilerleme):
        self.kimlikler.append((kimlik.api_key, kimlik.secret_key, kimlik.passphrase, kimlik.kaynak))
        self.evler.append((kimlik.profil_dizini, Path(kimlik.profil_dizini).is_dir()))
        for etiket in ILERLEME[:5]:
            ilerleme(etiket)
        if self.bekle is not None:
            self.bekle.wait(10)
        shutil.copy(ORNEK_DB, db_yolu)                     # hata olsa da yarım dosya kalır: silinmeli
        if self.hata is not None:
            raise self.hata
        if self.cumle_sil:
            with closing(sqlite3.connect(db_yolu)) as db:
                db.execute("DROP TABLE IF EXISTS cumle")
                db.commit()


class Sunucu(unittest.TestCase):
    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dizin, True)
        self.db = self.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, self.db)
        self.hesap_dizini = self.dizin / "hesaplar"
        self.kur(SahteTarama())

    def kur(self, tarama):
        self.tarama = tarama
        self.hesaplar = hesap.Hesaplar(self.hesap_dizini, tarama)
        httpd = sunucu.kur(self.db, "127.0.0.1", 0, hesaplar=self.hesaplar)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.adres = f"http://127.0.0.1:{httpd.server_address[1]}"

    def al(self, yol):
        try:
            with urllib.request.urlopen(self.adres + yol, timeout=10) as y:
                return y.status, json.loads(y.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read() or b"{}")

    def gonder(self, yol, govde, basliklar=None):
        veri_ = govde if isinstance(govde, bytes) else json.dumps(govde).encode()
        istek = urllib.request.Request(self.adres + yol, data=veri_, method="POST",
                                       headers={"content-type": "application/json", **(basliklar or {})})
        try:
            with urllib.request.urlopen(istek, timeout=10) as y:
                return y.status, json.loads(y.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read() or b"{}")

    def bagla(self, govde=None, basliklar=None):
        return self.gonder("/api/hesap/bagla", govde or ANAHTAR, basliklar)

    def bekle(self, kimlik, kosul=lambda d: d["bitti"]):
        bitis = time.monotonic() + 10
        while time.monotonic() < bitis:
            durum, d = self.al(f"/api/hesap/durum?hesap={kimlik}")
            self.assertEqual(durum, 200)
            if kosul(d):
                return d
            time.sleep(0.05)
        self.fail("tarama bitmedi")

    def baglanmis(self):
        durum, c = self.bagla()
        self.assertEqual(durum, 202)
        self.assertEqual(self.bekle(c["hesap"])["hata"], None)
        return c["hesap"]

    def soketsiz(self, istemci: str, govde: bytes) -> tuple[int, dict]:
        """İsteği gerçek soket olmadan işler: istemci adresi seçilebilir, okunmayan gövde bağlantıyı koparmaz."""
        ham = (b"POST /api/hesap/bagla HTTP/1.1\r\nHost: 192.168.1.5:3003\r\nContent-Type: application/json\r\n"
               b"Content-Length: " + str(len(govde)).encode() + b"\r\n\r\n" + govde)
        baglanti = _SahteBaglanti(ham)
        sunucu.isleyici(self.db, self.hesaplar)(baglanti, (istemci, 50000), None)
        bas, govde_ = baglanti.cikti.getvalue().split(b"\r\n\r\n", 1)
        return int(bas.split(b" ")[1]), json.loads(govde_)


class Bagla(Sunucu):
    def test_bagla_durum_ve_hesap_listesi(self):
        durum, c = self.bagla({"api_key": "  test-key ", "secret_key": "test-secret\n", "passphrase": "\ttest-pass "})
        self.assertEqual(durum, 202)
        self.assertEqual(c["durum"], "basladi")
        self.assertRegex(c["hesap"], r"^[0-9a-f]{12}$")
        d = self.bekle(c["hesap"])
        self.assertEqual(d, {"hesap": c["hesap"], "adim": "Hazır", "sira": 6, "toplam": 6, "bitti": True, "hata": None})
        self.assertEqual(self.tarama.kimlikler, [("test-key", "test-secret", "test-pass", "env")])   # boşluklar atıldı
        ev, vardi = self.tarama.evler[0]
        self.assertTrue(vardi)
        self.assertFalse(Path(ev).exists(), "ATK'nın geçici ev dizini tarama bitince silinmeli")
        self.assertEqual([p.name for p in self.hesap_dizini.iterdir()], [f"{c['hesap']}.db"])    # yarım dosya yok
        self.assertEqual(self.al("/api/hesaplar"), (200, [{"hesap": "ana", "ad": "Ana hesap"},
                                                         {"hesap": c["hesap"], "ad": "Hesap " + c["hesap"][:4]}]))

    def test_adim_adim_ve_ayni_anda_tek_tarama(self):
        olay = threading.Event()
        self.kur(SahteTarama(bekle=olay))
        durum, c = self.bagla()
        self.assertEqual(durum, 202)
        d = self.bekle(c["hesap"], lambda d: d["sira"] == 5)
        self.assertEqual((d["adim"], d["toplam"], d["bitti"], d["hata"]), ("Botlar ve köprü", 6, False, None))
        self.assertEqual(self.al(f"/api/rapor?hesap={c['hesap']}")[0], 404)       # bitmeden rapor yok
        self.assertEqual(self.al("/api/hesaplar")[1], [{"hesap": "ana", "ad": "Ana hesap"}])
        self.assertEqual(self.bagla(), (409, {"hata": "Bir tarama zaten sürüyor."}))
        olay.set()
        self.assertEqual(self.bekle(c["hesap"])["adim"], "Hazır")
        durum, c2 = self.bagla()                                                 # bitince yenisi başlar
        self.assertEqual(durum, 202)
        self.assertNotEqual(c2["hesap"], c["hesap"])
        self.bekle(c2["hesap"])

    def test_alanlar_eksikse_400(self):
        for govde in ({}, {"api_key": "a", "secret_key": "b"}, {"api_key": "a", "secret_key": "b", "passphrase": "  "},
                      {"api_key": 1, "secret_key": "b", "passphrase": "c"}, ["test-key"]):
            with self.subTest(govde=govde):
                self.assertEqual(self.gonder("/api/hesap/bagla", govde), (400, {"hata": "Üç alan da gerekli."}))
        durum, c = self.gonder("/api/hesap/bagla", b'{"api_key": "test-key", bozuk')
        self.assertEqual((durum, c), (400, {"hata": "geçersiz istek"}))
        durum, c = self.soketsiz("127.0.0.1", json.dumps({**ANAHTAR, "x": "y" * 5000}).encode())   # 4096 bayttan uzun
        self.assertEqual((durum, c), (400, {"hata": "geçersiz istek"}))
        self.assertEqual(self.tarama.kimlikler, [])

    def test_baska_siteden_gonderilemez(self):
        for koken in ("https://kotu.example", "http://localhost.kotu.example:3003", "null"):
            with self.subTest(koken=koken):
                self.assertEqual(self.bagla(basliklar={"Origin": koken}),
                                 (403, {"hata": "Yalnız bu bilgisayardan bağlanılabilir."}))
        self.assertEqual(self.tarama.kimlikler, [])
        durum, c = self.bagla(basliklar={"Origin": "http://localhost:3003"})
        self.assertEqual(durum, 202)
        self.bekle(c["hesap"])

    def test_yalniz_bu_bilgisayardan(self):
        """İstemci adresi 127.0.0.1 / ::1 değilse (ör. --host 0.0.0.0 ile telefondan) anahtar kabul edilmez."""
        for istemci in ("192.168.1.20", "10.0.0.7", "::ffff:192.168.1.20"):
            with self.subTest(istemci=istemci):
                self.assertEqual(self.soketsiz(istemci, json.dumps(ANAHTAR).encode()),
                                 (403, {"hata": "Yalnız bu bilgisayardan bağlanılabilir."}))
        self.assertEqual(self.tarama.kimlikler, [])
        durum, c = self.soketsiz("::1", json.dumps(ANAHTAR).encode())
        self.assertEqual(durum, 202)
        self.bekle(c["hesap"])


class Hatalar(Sunucu):
    def test_hata_iletileri_ve_yarim_dosya_silinir(self):
        for hata, metin in ((AtkHata("yazma_yetkili_anahtar", "anahtar şu yetkileri taşıyor: trade"), YAZMA),
                            (AtkHata("hata", ATK_KIMLIK_HATASI), TANIMADI),
                            (OkxHata("50111", "Invalid OK-ACCESS-KEY"), TANIMADI),
                            (RuntimeError("test-key test-secret test-pass"), "Tarama yarıda kaldı (RuntimeError).")):
            with self.subTest(hata=type(hata).__name__, kod=getattr(hata, "kod", None)):
                self.tarama.hata = hata
                durum, c = self.bagla()
                self.assertEqual(durum, 202)
                d = self.bekle(c["hesap"])
                self.assertEqual((d["bitti"], d["hata"]), (True, metin))
                self.assertNotIn("test-", json.dumps(d))
                self.assertEqual(list(self.hesap_dizini.iterdir()), [])           # yarım veri dosyası kalmadı
                self.assertFalse(Path(self.tarama.evler[-1][0]).exists())
                self.assertEqual(self.al(f"/api/rapor?hesap={c['hesap']}")[0], 404)
        self.assertEqual(self.al("/api/hesaplar")[1], [{"hesap": "ana", "ad": "Ana hesap"}])

    def test_hata_metni(self):
        for hata, metin in ((AtkHata("yazma_yetkili_anahtar"), YAZMA),
                            (AtkHata("hata", ATK_KIMLIK_HATASI), TANIMADI),
                            (AtkHata("50105", "OK-ACCESS-PASSPHRASE incorrect"), TANIMADI),
                            (AtkHata("401", "HTTP 401 from OKX"), TANIMADI),
                            (OkxHata("50113", "Invalid Sign"), TANIMADI),
                            (OkxHata("http401", "json değil"), TANIMADI),
                            (OkxHata("baglanti", "ConnectionError"), "Tarama yarıda kaldı (OkxHata)."),
                            (AtkHata("yetki_okunamadi"), "Tarama yarıda kaldı (AtkHata)."),
                            (FileNotFoundError("node"), "Tarama yarıda kaldı (FileNotFoundError).")):
            with self.subTest(hata=str(hata)):
                self.assertEqual(hesap.hata_metni(hata), metin)

    def test_bilinmeyen_hesap_404(self):
        bulunamadi = {"hata": "hesap bulunamadı"}
        for yol in ("/api/hesap/durum?hesap=yok", "/api/hesap/durum", "/api/hesap/durum?hesap=0123456789ab",
                    "/api/rapor?hesap=0123456789ab", "/api/rapor?hesap=../proof1", "/api/rapor?hesap=ABCDEF012345",
                    "/api/ayrinti?hesap=0123456789ab", "/api/oturumlar?hesap=x",
                    "/api/muhur-dogrula?gun=2026-10-17&hesap=0123456789ab"):
            with self.subTest(yol=yol):
                self.assertEqual(self.al(yol), (404, bulunamadi))
        (self.dizin / "hesaplar").mkdir()
        (self.hesap_dizini / "0123456789ab.yaziliyor.db").write_bytes(b"")
        (self.hesap_dizini / "notlar.db").write_bytes(b"")
        self.assertEqual(self.al("/api/rapor?hesap=0123456789ab"), (404, bulunamadi))
        self.assertEqual(self.gonder("/api/isaret?hesap=0123456789ab", {"adres_etiket": "BENIM_1", "ag": "x",
                                                                        "sahip": "benim"}), (404, bulunamadi))
        self.assertEqual(self.al("/api/hesaplar")[1], [{"hesap": "ana", "ad": "Ana hesap"}])


class MisafirVerisi(Sunucu):
    def test_hesap_verilmezse_ya_da_ana_ise_sahibin_dosyasi(self):
        sahibin = self.al("/api/rapor")
        self.assertEqual(sahibin[0], 200)
        for yol in ("/api/rapor?hesap=ana", "/api/rapor?hesap="):
            with self.subTest(yol=yol):
                self.assertEqual(self.al(yol), sahibin)

    def test_misafir_raporu_ve_isaret_kendi_dosyasina(self):
        kimlik = self.baglanmis()
        misafir_db = self.hesap_dizini / f"{kimlik}.db"
        with closing(sqlite3.connect(misafir_db)) as db:
            db.execute("UPDATE olgu SET oturum='sabah-2026-10-18' WHERE oturum=?", (OTURUM,))   # ayırt edilebilsin
            db.commit()
            etiket, ag = db.execute("SELECT etiket, ag FROM adres WHERE tahmin='benim' ORDER BY id LIMIT 1").fetchone()
        self.assertEqual(self.al(f"/api/oturumlar?hesap={kimlik}")[1][0], "sabah-2026-10-18")
        self.assertEqual(self.al(f"/api/rapor?hesap={kimlik}")[1]["oturum"], "sabah-2026-10-18")
        self.assertEqual(self.al("/api/rapor")[1]["oturum"], OTURUM)
        self.assertEqual(self.al(f"/api/ayrinti?hesap={kimlik}")[1]["oturum"], "sabah-2026-10-18")
        self.assertEqual(self.gonder(f"/api/isaret?hesap={kimlik}", {"adres_etiket": etiket, "ag": ag, "sahip": "benim"}),
                         (200, {"durum": "kaydedildi"}))
        with closing(sqlite3.connect(misafir_db)) as db:
            self.assertEqual(db.execute("SELECT sahip FROM isaret WHERE adres_etiket=?", (etiket,)).fetchone(), ("benim",))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertFalse(veri._tablo_var(db, "isaret") and db.execute("SELECT 1 FROM isaret").fetchone())

    def test_misafir_muhur_iddia_etmez(self):
        kimlik = self.baglanmis()
        with mock.patch.dict(os.environ, {"PROOF1_AGENT_ID": "263",
                                          "PROOF1_SEAL_ADDRESS": "0x7C5aB869e8d972885673f19B848084279AAD0d48"}):
            sahibin = self.al("/api/ayrinti")[1]["muhur"]
            misafir = self.al(f"/api/ayrinti?hesap={kimlik}")[1]["muhur"]
            dogrula = self.al(f"/api/muhur-dogrula?gun=2026-10-17&hesap={kimlik}")
        self.assertEqual(sahibin["agent_id"], "263")
        self.assertEqual((misafir["agent_id"], misafir["sozlesme"], misafir["kimlik"]), ("", "", ""))
        self.assertIsNone(misafir["kimlik_gezgin"])
        self.assertIsNone(misafir["sozlesme_gezgin"])
        self.assertEqual(dogrula, (200, {"durum": "ayar_yok"}))

    def test_anlatici_hic_calismamis_misafir_raporu(self):
        self.kur(SahteTarama(cumle_sil=True))
        kimlik = self.baglanmis()
        durum, r = self.al(f"/api/rapor?hesap={kimlik}")
        self.assertEqual(durum, 200)
        self.assertEqual(r["ozet"], [])
        self.assertEqual(self.al(f"/api/ayrinti?hesap={kimlik}")[0], 200)


class GercekTarama(unittest.TestCase):
    """pano.hesap.tara → calistir.sabah (tek hesap, Telegram'sız, anlatıcısız) → kalıp cümleler. OKX ve ATK sahte."""

    def test_tarama_tek_dosya_kalip_cumle_anahtar_yok(self):
        import contextlib
        import sys
        from veri.testler.test_b8_sabah import SahteAtk, SahteOkx

        class KayitliAtk(SahteAtk):
            evler = []

            def __init__(self, kimlik, *a, **k):
                super().__init__(kimlik, *a, **k)
                KayitliAtk.evler.append(kimlik.profil_dizini)
        dizin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dizin, True)
        SahteOkx.olaylar = SahteAtk.olaylar = []
        SahteOkx.hatali_uc, SahteAtk.reddet = None, False
        isaret = dizin / "anlatici_calisti.txt"
        (dizin / "a.py").write_text(f"open(r'{isaret}', 'w').close()\n", encoding="utf-8")
        hesaplar = hesap.Hesaplar(dizin / "hesaplar")                     # gerçek tarayıcı: hesap.tara
        cikti = io.StringIO()
        with mock.patch("veri.atk.Atk", KayitliAtk), mock.patch("veri.okx_imzali.OkxTr", SahteOkx), \
                mock.patch("veri.ayar.env_yukle", lambda *a: None), \
                mock.patch.dict(os.environ, {"ANLATICI_KOMUT": f'"{sys.executable}" "{dizin / "a.py"}"',
                                             "PROOF1_ANLATICI_GUNLUK": str(dizin / "gunluk.jsonl")}), \
                contextlib.redirect_stdout(cikti), contextlib.redirect_stderr(cikti):
            kimlik = hesaplar.bagla("test-key-9", "test-secret-9", "test-pass-9")
            bitis = time.monotonic() + 30
            while not hesaplar.durum(kimlik)["bitti"] and time.monotonic() < bitis:
                time.sleep(0.05)
        d = hesaplar.durum(kimlik)
        self.assertEqual((d["adim"], d["bitti"], d["hata"]), ("Hazır", True, None))
        self.assertEqual(sorted(p.name for p in (dizin / "hesaplar").iterdir()), [f"{kimlik}.db"])   # tek dosya
        yol = dizin / "hesaplar" / f"{kimlik}.db"
        with closing(sqlite3.connect(yol)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            modeller = {r[0] for r in db.execute("SELECT model FROM cumle")}
            hesaplar_ = db.execute("SELECT DISTINCT hesap FROM hareket").fetchall()
        self.assertEqual(modeller, {"kalip"})                                    # cümleler var, hepsi kalıp
        self.assertEqual(hesaplar_, [("ana",)])
        self.assertFalse(isaret.exists(), "ücretli anlatıcı çalışmamalı")
        ham = yol.read_bytes()
        for deger in ("test-key-9", "test-secret-9", "test-pass-9"):
            self.assertNotIn(deger.encode(), ham)
            self.assertNotIn(deger, cikti.getvalue())
        self.assertEqual(len(KayitliAtk.evler), 1)
        self.assertFalse(Path(KayitliAtk.evler[0]).exists())                    # ATK'nın geçici evi silindi


class CumleTablosuYok(unittest.TestCase):
    def test_rapor_cumle_tablosu_olmadan(self):
        dizin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dizin, True)
        yol = dizin / "misafir.db"
        shutil.copy(ORNEK_DB, yol)
        with closing(sqlite3.connect(yol)) as db:
            db.execute("DROP TABLE IF EXISTS cumle")
            db.commit()
            r = veri.rapor(db, OTURUM)
        self.assertEqual(r["oturum"], OTURUM)
        self.assertEqual(r["ozet"], [])
        self.assertTrue(r["akis"]["gruplar"])


class _SahteBaglanti:
    """Soket yerine: isteği bayttan okur, cevabı bayta yazar (istemci adresi testte seçilebilsin)."""

    def __init__(self, ham: bytes):
        self.girdi, self.cikti = io.BytesIO(ham), io.BytesIO()

    def makefile(self, kip, *a, **k):
        return self.girdi if "r" in kip else self.cikti

    def sendall(self, veri_):
        self.cikti.write(veri_)

    def settimeout(self, *_):
        pass

    def setsockopt(self, *_):
        pass


if __name__ == "__main__":
    unittest.main()
