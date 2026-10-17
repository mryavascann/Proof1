"""Gerçek koşuda bulunan hataların testleri: gezgin sayfalaması, defter–zincir kapanışı, TL banka yatırması ve faiz."""
import unittest
from decimal import Decimal

from veri import db as dbm
from veri.aglar import AGLAR
from veri.defter import fonlama_hareketleri
from veri.kopru import kategori
from veri.zincir.evm import GezginApi

A = "0x" + "aa" * 20


class SahteCevap:
    def __init__(self, j):
        self._j = j
        self.status_code = 200
        self.ok = True

    def json(self):
        return self._j


class SayfaliHttp:
    """txlist: 1. sayfa 1000 satır, 2. sayfa 5 satır; diğerleri boş."""

    def __init__(self):
        self.sayfalar = []

    def get(self, url, params=None, timeout=None):
        if params.get("action") == "txlist":
            self.sayfalar.append(params["page"])
            n = 1000 if params["page"] == 1 else 5
            sonuc = [{"hash": f"0x{params['page']}{i:05d}", "timeStamp": str(1_700_000_000 + i), "from": A, "to": "0x" + "bb" * 20,
                      "value": "0", "gasUsed": "21000", "gasPrice": "1000000000", "isError": "0"} for i in range(n)]
            return SahteCevap({"status": "1", "result": sonuc})
        return SahteCevap({"status": "0", "message": "No transactions found", "result": []})


class Sayfalama(unittest.TestCase):
    def test_bin_satirdan_fazlasi_okunur(self):
        http = SayfaliHttp()
        b = GezginApi("routescan", http=http).islemler(A, AGLAR["Chiliz Chain"])
        self.assertEqual(http.sayfalar, [1, 2])
        self.assertEqual(len(b.meta), 1005)


class Fonlama(unittest.TestCase):
    def _satir(self, tip, ccy, chg, bill="1"):
        return {"billId": bill, "ts": "1792131483000", "type": tip, "ccy": ccy, "balChg": chg}

    def test_tl_banka_yatirmasi_ve_faiz(self):
        h = {x["ham_kimlik"].rsplit(":", 1)[1]: x for x in fonlama_hareketleri([
            self._satir("1", "TRY", "90000", "y"), self._satir("131", "TRY", "-90000", "a"),
            self._satir("525", "TRY", "13.11", "f"), self._satir("526", "TRY", "-2.3", "v"),
            self._satir("1", "USDT", "100", "k"), self._satir("2", "TRY", "-500", "c")])}
        self.assertEqual((h["y"]["tur"], h["y"]["karsi"]), ("yatirma", "banka"))
        self.assertEqual(h["a"]["tur"], "aktarim")
        self.assertEqual(h["f"]["tur"], "giris")
        self.assertEqual(h["v"]["tur"], "ucret")
        self.assertNotIn("k", h)                       # kripto yatırma ayrıntılı kayıttan gelir
        self.assertEqual((h["c"]["tur"], h["c"]["karsi"]), ("cekim", "banka"))

    def test_kopru_kategorileri(self):
        satir = lambda tur, karsi=None: {"tur": tur, "karsi": karsi, "supheli": 0, "islem_kimligi": "x", "kaynak": "borsa", "ag": None}
        self.assertEqual(kategori(satir("yatirma", "banka"), "servet", set(), set(), set()), "iceri")
        self.assertEqual(kategori(satir("giris"), "borsa", set(), set(), set()), "iceri")
        self.assertEqual(kategori(satir("cekim", "banka"), "servet", set(), set(), set()), "disari")


class YenidenYazma(unittest.TestCase):
    def test_tur_guncellenir_dolar_ve_karsi_korunur(self):
        from veri.defter import yaz
        db = dbm.baglan(":memory:")
        satir = {"zaman": "2026-10-16T06:42:57.000Z", "kaynak": "borsa", "hesap": "ana", "adres_id": None, "ag": None,
                 "varlik": "TRY", "miktar": "13.11", "dolar": None, "tur": "taninmadi", "islem_kimligi": "b", "karsi": None,
                 "supheli": 0, "durum": "ok", "kaynak_okuma": "asset/bills", "ham_kimlik": "asset/bills:ana:b"}
        yaz(db, [satir])
        db.execute("UPDATE hareket SET dolar='0.27', karsi='BENIM_1'")
        yaz(db, [dict(satir, tur="giris")])
        r = db.execute("SELECT tur, dolar, karsi, COUNT(*) n FROM hareket").fetchone()
        self.assertEqual((r["tur"], r["dolar"], r["karsi"], r["n"]), ("giris", "0.27", "BENIM_1", 1))


class KopruOzet(unittest.TestCase):
    def test_kalip_yon_soyler(self):
        from veri.olgu import OlguYazici, kalip_cumle
        db = dbm.baglan(":memory:")
        OlguYazici(db, "s").ekle("kopru_ozet", {"kapsam": "servet", "degisim": "1.851 $", "miktar": "1.851 $", "yon": "arttı"})
        cumle, _ = kalip_cumle(db, "s")
        self.assertIn("1.851 $ arttı", cumle)


class TazeOkuma(unittest.TestCase):
    def test_onbellek_atlanir(self):
        from veri.zincir.okuyucu import ZincirOkuyucu
        db = dbm.baglan(":memory:")
        z = ZincirOkuyucu(db, onbellek=False)
        db.execute("INSERT INTO _zincir_ham VALUES ('0xa', 'chiliz', 'routescan', ?, '{\"bacak\": [], \"meta\": []}')", (__import__("time").time(),))
        self.assertIsNone(z._bellek("0xa", AGLAR["Chiliz Chain"]) if z.onbellek else None)
        self.assertFalse(z.onbellek)


class Kapanis(unittest.TestCase):
    def test_defter_zincirle_kapanmazsa_kaydedilir(self):
        from veri.adres import AdresKarti, yaz as adres_yaz
        from veri.borsa import Kayit
        from veri.defter import cekim_hareketleri, yaz as hyaz
        from veri.testler.test_b4_tara import SahteOkuyucu
        from veri.testler.test_b4_zincir import A as AA, OKX
        from veri.zincir.tara import kapanislar, tara

        class BakiyeliOkuyucu(SahteOkuyucu):
            def bakiye(self, adres, ag):
                return Decimal("0.5") if ag.anahtar == "avalanche" else None

        db = dbm.baglan(":memory:")
        cek = [Kayit("cekim", "w1", 1791722000000, "AVAX", "AVAX-Avalanche C-Chain", Decimal("0.98280221"), Decimal("0.015"),
                     "AVAX", AA, "0xc1", "2")]
        hyaz(db, cekim_hareketleri(cek))
        adres_yaz(db, [AdresKarti(AA, "avalanche", ["avalanche"], 3, "benim", "k", 1, 1, 2, 1, "BENIM_1", ["w1"])], cek)
        tara(db, BakiyeliOkuyucu(), cek, [], borsa_adresleri={OKX})
        k = {(x["etiket"], x["ag"]): x for x in kapanislar(db)}
        x = k[("BENIM_1", "avalanche")]
        self.assertEqual(Decimal(x["zincir"]), Decimal("0.5"))
        self.assertEqual(Decimal(x["fark"]).quantize(Decimal("0.000001")), Decimal("-0.280825"))


if __name__ == "__main__":
    unittest.main()
