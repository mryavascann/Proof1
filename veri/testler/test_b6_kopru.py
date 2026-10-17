"""B6 kabul: dünle karşılaştırma (köprü). dünkü toplam + kalemler = bugünkü toplam; kapanmazsa “açıklanamayan”."""
import json
import unittest
from decimal import Decimal

from veri import db as dbm
from veri.adres import AdresKarti, yaz as adres_yaz
from veri.borsa import Kayit
from veri.defter import cekim_hareketleri, yaz as hyaz
from veri.kopru import kopru_kur, kopruyu_yaz
from veri.testler.test_b4_zincir import A, B, GUN, OKX
from veri.zincir.tara import tara
from veri.testler.test_b4_tara import SahteOkuyucu
from veri.testler.ortak import canli, canli_db

BAS = 1791698400000    # 11 Ekim 2026 09:00 İstanbul
BIT = 1791784800000    # 12 Ekim 2026 09:00 İstanbul
FIYAT = {"AVAX": Decimal("10.5"), "USDC": Decimal(1), "USDT": Decimal(1)}


def sabit_fiyat(varlik, ts):
    return FIYAT.get(varlik)


class Kopru11Ekim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = dbm.baglan(":memory:")
        cek = [Kayit("cekim", "w1", 1791721943000, "AVAX", "AVAX-Avalanche C-Chain", Decimal("0.98280221"),
                     Decimal("0.015"), "AVAX", A, "0xc1", "2")]
        hyaz(db, cekim_hareketleri(cek))
        adres_yaz(db, [AdresKarti(A, "avalanche", ["avalanche"], 3, "benim", "k", 1, 1, 2, 1, "BENIM_1", ["w1"])], cek)
        tara(db, SahteOkuyucu(), cek, [], borsa_adresleri={OKX})
        # ikinci hesap: kullanıcı “benim” dedi (isaret, Merve'nin tablosu) ve okundu
        db.execute("CREATE TABLE isaret (adres_etiket TEXT, ag TEXT, sahip TEXT, zaman TEXT)")
        db.execute("INSERT INTO isaret VALUES ('KARSI_1', 'avalanche', 'benim', '2026-10-12T08:00:00Z')")
        kid = db.execute("SELECT id FROM adres WHERE etiket='KARSI_1'").fetchone()[0]
        hyaz(db, [{"zaman": "2026-10-11T12:53:22.000Z", "kaynak": "zincir", "hesap": "cuzdan", "adres_id": kid, "ag": "avalanche",
                   "varlik": v, "miktar": m, "dolar": None, "tur": "giris", "islem_kimligi": tx, "karsi": "BENIM_1",
                   "supheli": 0, "durum": "ok", "kaynak_okuma": "sahte", "ham_kimlik": f"k:{tx}"}
                  for v, m, tx in (("AVAX", "0.1", "0xg1"), ("USDC", "1", "0xg2"))])
        cls.db = db
        cls.k = kopru_kur(db, "2026-10-12", BAS, BIT, sabit_fiyat)

    def _kalem(self, kapsam, kalem):
        return next((x for x in self.k[kapsam] if x.kalem == kalem), None)

    def test_borsa_eksi_0998_avax(self):
        toplam = sum((x.varlik.get("AVAX", 0) for x in self.k["borsa"] if x.kalem not in ("baslangic", "bitis")), Decimal(0))
        self.assertEqual(toplam, Decimal("-0.99780221"))
        self.assertEqual(self._kalem("borsa", "aktarim").varlik, {"AVAX": Decimal("-0.98280221")})
        self.assertEqual(self._kalem("borsa", "ucret").varlik, {"AVAX": Decimal("-0.015")})

    def test_servet_yalniz_ucretler_ve_aciklanamayan(self):
        self.assertEqual(self._kalem("servet", "ucret").varlik["AVAX"].quantize(Decimal("0.000001")), Decimal("-0.017189"))
        self.assertEqual(self._kalem("servet", "aciklanamayan").varlik["AVAX"].quantize(Decimal("0.000001")), Decimal("0.000212"))
        akt = self._kalem("servet", "aktarim")
        self.assertTrue(akt is None or all(v == 0 for v in akt.varlik.values()))
        servet_avax = sum((x.dolar for x in self.k["servet"] if x.kalem not in ("baslangic", "bitis")), Decimal(0)) / FIYAT["AVAX"]
        self.assertTrue(Decimal("-0.019") < servet_avax < Decimal("-0.016"), servet_avax)

    def test_kopru_kapanir(self):
        for kapsam in ("borsa", "servet"):
            bas = self._kalem(kapsam, "baslangic").dolar
            bit = self._kalem(kapsam, "bitis").dolar
            ara = sum((x.dolar for x in self.k[kapsam] if x.kalem not in ("baslangic", "bitis")), Decimal(0))
            self.assertEqual(bas + ara, bit, kapsam)

    def test_yaz(self):
        kopruyu_yaz(self.db, "2026-10-12", self.k)
        r = self.db.execute("SELECT kalem, tutar, varlik_tutar FROM kopru WHERE kapsam='servet' AND kalem='aciklanamayan'").fetchone()
        self.assertEqual(json.loads(r["varlik_tutar"])["AVAX"][:8], "0.000211")
        self.assertEqual(self.db.execute("SELECT COUNT(DISTINCT kapsam) FROM kopru").fetchone()[0], 2)


class KopruFiyatVeOlcum(unittest.TestCase):
    def test_fiyat_etkisi_ve_olculen_fark(self):
        db = dbm.baglan(":memory:")
        fotolar = {"bas": {"borsa:alt": {"USDT": Decimal(100), "AVAX": Decimal(2)}},
                   "bit": {"borsa:alt": {"USDT": Decimal(100), "AVAX": Decimal("2.5")}}}
        fiyat = lambda v, ts: {"AVAX": Decimal(10) if ts == BAS else Decimal(12), "USDT": Decimal(1)}[v]
        k = kopru_kur(db, "2026-10-12", BAS, BIT, fiyat, fotolar=fotolar)
        kal = {x.kalem: x for x in k["borsa"]}
        self.assertEqual(kal["fiyat"].dolar, Decimal(4))                     # 2 AVAX × (12 − 10)
        self.assertEqual(kal["aciklanamayan"].varlik, {"AVAX": Decimal("0.5")})   # defterde olmayan 0,5 AVAX
        self.assertEqual(kal["baslangic"].dolar + sum(x.dolar for x in k["borsa"][1:-1]), kal["bitis"].dolar)

    def test_fiyati_olmayan_varlik_coin_cinsinden(self):
        db = dbm.baglan(":memory:")
        fotolar = {"bas": {"borsa:alt": {"MOCA": Decimal(10)}}, "bit": {"borsa:alt": {"MOCA": Decimal(12)}}}
        k = kopru_kur(db, "2026-10-12", BAS, BIT, lambda v, ts: None, fotolar=fotolar)
        kal = {x.kalem: x for x in k["borsa"]}
        self.assertEqual(kal["fiyatsiz"].varlik, {"MOCA": Decimal(2)})     # dolar uydurulmaz
        self.assertEqual((kal["baslangic"].dolar, kal["bitis"].dolar), (0, 0))


@canli
class CanliKopru(unittest.TestCase):
    def test_bugunun_koprusu_16_ekim_botunu_icerir(self):
        from veri import ayar
        from veri.atk import Atk
        from veri.defter import alt_defteri, hareketlere, zincirle
        from veri.fiyat import Fiyatci
        from veri.fotograf import borsa_bakiyeleri
        from veri.okx_imzali import OkxTr
        db = dbm.baglan(":memory:")
        canli = canli_db()
        with Atk(ayar.okx_kimlik("alt"), canli, "test-b6") as atk:
            s = alt_defteri(atk)
            zincirle(s)
            hyaz(db, hareketlere(s))
            foto = borsa_bakiyeleri(OkxTr(ayar.okx_kimlik("ana"), canli, "test-b6"), atk)
            f = Fiyatci(atk, canli)
            k = kopru_kur(db, "2026-10-17", 1792130400000, 1792216800000, f.dolar, fotolar={"bit": foto})
        self.assertEqual(set(foto), {"borsa:ana", "borsa:alt"})
        self.assertTrue(all(isinstance(q, Decimal) for d in foto.values() for q in d.values()))
        bot = next(x for x in k["borsa"] if x.kalem == "bot")
        self.assertEqual(bot.varlik["TRY"].quantize(Decimal("0.01")), Decimal("-100.33"))
        self.assertEqual(bot.varlik["USDT"].quantize(Decimal("0.0001")), Decimal("2.0278"))
        self.assertLess(abs(bot.dolar), Decimal("0.05"))                 # −0,22 TL ≈ −0,0045 $
        bas = k["borsa"][0].dolar
        kurus = Decimal("0.0001")                                        # TL→$ bölmesinin 28. basamağı
        self.assertEqual((bas + sum(x.dolar for x in k["borsa"][1:-1])).quantize(kurus), k["borsa"][-1].dolar.quantize(kurus))


if __name__ == "__main__":
    unittest.main()
