"""B1 kabul: OKX TR okuyucu (imzalı uçlar + ATK salt okuma) ve çağrı kaydı."""
import base64
import hashlib
import hmac
import json
import unittest
from collections import Counter
from decimal import Decimal

from veri import ayar, db as dbm
from veri.aglar import ag_bul
from veri.atk import Atk, yazma_araci_mi
from veri.borsa import _kayit, cekimler, dolar_degeri, tamamlanan
from veri.kayit import cagri_kaydi, maskele
from veri.okx_imzali import IZINLI_UCLAR, OkxTr, imza
from veri.testler.ortak import DEVIR_KESIM_MS, canli, canli_db


class Imza(unittest.TestCase):
    def test_okx_v5_imzasi(self):
        beklenen = base64.b64encode(hmac.new(b"gizli", b"2026-10-17T09:00:00.000ZGET/api/v5/asset/bills?limit=1",
                                             hashlib.sha256).digest()).decode()
        self.assertEqual(imza("gizli", "2026-10-17T09:00:00.000Z", "get", "/api/v5/asset/bills?limit=1"), beklenen)

    def test_izinli_olmayan_uc_reddedilir(self):
        okx = OkxTr(ayar.OkxKimlik("ana", "k", "s", "p"))
        for yol in ["/api/v5/asset/withdrawal", "/api/v5/trade/order", "/api/v5/asset/transfer"]:
            with self.assertRaises(PermissionError):
                okx.oku(yol)
        self.assertTrue(all("withdrawal-history" in u or "deposit" in u or "bills" in u or "balance" in u
                            for u in IZINLI_UCLAR))

    def test_kimlik_yazdirilinca_sir_gorunmez(self):
        k = ayar.OkxKimlik("ana", "ANAHTAR123", "SIR456", "PAROLA789")
        self.assertNotIn("ANAHTAR123", repr(k))
        self.assertNotIn("SIR456", repr(k))


class SaltOkuma(unittest.TestCase):
    def test_yazma_araclari_taninir(self):
        for ad in ["spot_place_order", "spot_cancel_order", "grid_create_order", "grid_stop_order",
                   "account_transfer", "asset_withdraw"]:
            self.assertTrue(yazma_araci_mi(ad), ad)
        for ad in ["account_get_bills", "grid_get_orders", "market_get_candles", "trade_get_history"]:
            self.assertFalse(yazma_araci_mi(ad), ad)


class CagriKaydi(unittest.TestCase):
    def test_maskeli_ve_sureli(self):
        db = dbm.baglan(":memory:")
        with cagri_kaydi(db, "OKX TR", "GET /x", {"address": "0x" + "ab" * 20, "apiKey": "x", "limit": 5}) as c:
            c.satir, c.alanlar = 3, ["amt"]
        r = db.execute("SELECT * FROM cagri").fetchone()
        p = json.loads(r["parametreler"])
        self.assertEqual(p, {"address": "0xabab…abab", "limit": 5})
        self.assertEqual((r["sonuc"], r["satir"], r["salt_okunur"]), ("ok", 3, 1))
        self.assertGreaterEqual(r["sure_ms"], 0)

    def test_hata_kaydedilir(self):
        db = dbm.baglan(":memory:")
        with self.assertRaises(ValueError):
            with cagri_kaydi(db, "ATK", "account_get_bills"):
                raise ValueError("bozuk")
        self.assertEqual(db.execute("SELECT sonuc, kod FROM cagri").fetchone()[:], ("hata", "ValueError"))

    def test_maskele_tron_ve_tx(self):
        m = maskele({"q": "TQ" + "a" * 32, "tx": "0x" + "1" * 64, "tron_tx": "ab" * 32})
        self.assertEqual(m["q"], "TQaaaa…aaaa")
        self.assertTrue(m["tx"].startswith("0x1111…"))
        self.assertEqual(m["tron_tx"], "ababab…abab")


class Ayristirma(unittest.TestCase):
    def test_eksik_alan_okunamadi_olur(self):
        k = _kayit("cekim", {"ts": "x", "ccy": "AVAX", "chain": "AVAX-Avalanche C-Chain", "amt": "abc", "to": "BENIM_1"})
        self.assertTrue(k.okunamadi)
        k = _kayit("cekim", {"ts": "1760189543000", "ccy": "AVAX", "chain": "AVAX-Avalanche C-Chain",
                             "amt": "0.98280221", "fee": "0.015", "to": "BENIM_1", "state": "2"})
        self.assertFalse(k.okunamadi)
        self.assertEqual(k.miktar, Decimal("0.98280221"))
        self.assertEqual(k.ag.anahtar, "avalanche")

    def test_bilinmeyen_ag_katman_1(self):
        ag = ag_bul("XYZ-Bilinmez Ağı")
        self.assertEqual(ag.katman, 1)
        self.assertEqual(ag_bul("CHZ-Chiliz Chain").katman, 3)


@canli
class CanliOkx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = canli_db()
        cls.okx = OkxTr(ayar.okx_kimlik("ana"), cls.db, "test-b1")
        cls.cekim = tamamlanan(cekimler(cls.okx))
        cls.devir = [k for k in cls.cekim if k.ts < DEVIR_KESIM_MS]

    def test_85_cekim_ve_ag_dagilimi(self):
        self.assertEqual(len(self.devir), 85)
        ag = Counter(k.ag.anahtar for k in self.devir)
        self.assertEqual(dict(ag), {"arbitrum": 17, "ethereum": 14, "chiliz": 49, "polygon": 2, "tron": 2, "avalanche": 1})

    def test_11_ekim_avax_cekimi(self):
        avax = [k for k in self.devir if k.ccy == "AVAX"]
        self.assertEqual(len(avax), 1)
        k = avax[0]
        self.assertEqual((k.miktar, k.ucret, k.ag_adi), (Decimal("0.98280221"), Decimal("0.015"), "Avalanche C-Chain"))
        self.assertEqual(k.ts // 60000 * 60000, 1791721920000)  # 11.10.2026 15:32 İstanbul

    def test_toplam_dolar_yaklasik_47987(self):
        with Atk(ayar.okx_kimlik("alt"), self.db, "test-b1") as atk:
            from veri.fiyat import Fiyatci
            toplam, fiyatsiz = dolar_degeri(self.devir, Fiyatci(atk, self.db))
        self.assertEqual(fiyatsiz, [])
        self.assertAlmostEqual(float(toplam), 47987, delta=47987 * 0.01)

    def test_cagrilar_kayitli(self):
        r = self.db.execute("SELECT COUNT(*), MIN(salt_okunur) FROM cagri WHERE oturum='test-b1' AND sonuc='ok'").fetchone()
        self.assertGreater(r[0], 0)
        self.assertEqual(r[1], 1)


@canli
class CanliAtk(unittest.TestCase):
    def test_43_arac_hicbiri_yazmaz(self):
        with Atk(ayar.okx_kimlik("alt"), canli_db(), "test-b1") as atk:
            self.assertEqual(len(atk.araclar), 43)
            self.assertEqual([a for a in atk.araclar if yazma_araci_mi(a)], [])
            for a in ["account_get_bills", "account_get_bills_archive", "grid_get_orders", "grid_get_order_details",
                      "grid_get_sub_orders", "spot_get_fills", "account_get_balance_all", "account_get_asset_balance",
                      "market_get_ticker", "market_get_candles", "trade_get_history"]:
                self.assertIn(a, atk.araclar)


if __name__ == "__main__":
    unittest.main()
