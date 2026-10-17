"""B3 kabul: çekim kaydından adres ve sahiplik (çekim yapılan adres hesaba para da yatırmışsa “büyük olasılıkla senin”)."""
import unittest
from decimal import Decimal

from veri import ayar, db as dbm
from veri.adres import adresleri_cikar, normal, yaz
from veri.borsa import Kayit
from veri.testler.ortak import DEVIR_KESIM_MS, canli, canli_db
from veri.zincir.tx import tron_base58, tron_hex

A1 = "0x" + "a1" * 20
A2 = "0x" + "b2" * 20


def k(tur, adres, ccy="USDT", chain="USDT-Arbitrum One", ts=1_760_000_000_000, tx="t"):
    return Kayit(tur, f"{tur}{ts}", ts, ccy, chain, Decimal(10), Decimal("0.1"), ccy, adres, tx, "2")


class Sahiplik(unittest.TestCase):
    def test_hem_cekim_hem_yatirma_benim(self):
        cek = [k("cekim", A1), k("cekim", A1.upper().replace("0X", "0x"), ts=1_760_000_100_000), k("cekim", A2, ts=1_760_000_200_000)]
        yat = [k("yatirma", "", tx="d1")]
        adr = adresleri_cikar(cek, yat, gonderen=lambda ag, tx: A1)
        self.assertEqual(len(adr), 2)                       # büyük/küçük harf aynı adres
        a1 = next(a for a in adr if a.adres == A1)
        self.assertEqual((a1.tahmin, a1.etiket, a1.cekim_sayisi), ("benim", "BENIM_1", 2))
        self.assertIn("1 kez", a1.kanit)
        a2 = next(a for a in adr if a.adres == A2)
        self.assertEqual((a2.tahmin, a2.etiket), ("belli_degil", "ADRES_1"))

    def test_gonderen_okunamazsa_tahmin_yok(self):
        adr = adresleri_cikar([k("cekim", A1)], [k("yatirma", "", tx="d1")], gonderen=lambda ag, tx: None)
        self.assertEqual(adr[0].tahmin, "belli_degil")

    def test_yatirma_from_dolu_ise_zincire_gerek_yok(self):
        adr = adresleri_cikar([k("cekim", A1)], [k("yatirma", A1)], gonderen=lambda ag, tx: self.fail("çağrılmamalı"))
        self.assertEqual(adr[0].tahmin, "benim")

    def test_yaz_ve_hareket_karsi(self):
        db = dbm.baglan(":memory:")
        from veri.defter import cekim_hareketleri, yaz as hyaz
        cek = [k("cekim", A1)]
        hyaz(db, cekim_hareketleri(cek))
        yaz(db, adresleri_cikar(cek, [], gonderen=lambda ag, tx: None), cek)
        self.assertEqual(db.execute("SELECT karsi FROM hareket WHERE tur='cekim'").fetchone()[0], "ADRES_1")
        r = db.execute("SELECT kisa, gezgin_url, katman FROM adres").fetchone()
        self.assertEqual(r["kisa"], "0xa1a1…a1a1")
        self.assertTrue(r["gezgin_url"].startswith("https://arbiscan.io/address/"))

    def test_normal(self):
        self.assertEqual(normal("0xABCdef" + "0" * 34), "0xabcdef" + "0" * 34)
        self.assertEqual(normal("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"), "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")


class Tron(unittest.TestCase):
    def test_base58_usdt_sozlesmesi(self):
        self.assertEqual(tron_base58("41a614f803b6fd780986a42c78ec9c7f77e6ded13c"), "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        self.assertEqual(tron_hex("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"), "41a614f803b6fd780986a42c78ec9c7f77e6ded13c")


@canli
class CanliAdres(unittest.TestCase):
    def test_37_adres_3_benim(self):
        from veri.borsa import cekimler, tamamlanan, yatirmalar
        from veri.okx_imzali import OkxTr
        from veri.zincir.tx import TxOkuyucu
        db = canli_db()
        okx = OkxTr(ayar.okx_kimlik("ana"), db, "test-b3")
        cek = [c for c in tamamlanan(cekimler(okx)) if c.ts < DEVIR_KESIM_MS]
        yat = tamamlanan(yatirmalar(okx))
        adr = adresleri_cikar(cek, yat, gonderen=TxOkuyucu(db, "test-b3").gonderen)
        self.assertEqual(len(adr), 37)
        benim = [a for a in adr if a.tahmin == "benim"]
        self.assertEqual(len(benim), 3, [a.kanit for a in benim])


if __name__ == "__main__":
    unittest.main()
