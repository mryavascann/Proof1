"""OnchainOS (OKX'in kendi zincir aracı) cevabı → bacaklar; 11 Ekim Avalanche günü Routescan'le aynı çözülmeli."""
import unittest
from decimal import Decimal

from veri import ayar
from veri.aglar import AGLAR
from veri.testler.ortak import canli, canli_db
from veri.zincir.cozucu import Baglam, coz
from veri.zincir.onchainos import cevir

A = "0x" + "aa" * 20
R = "0x" + "cc" * 20
USDC = "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e"


def satir(tx, itype, kimden, kime, miktar, sembol="AVAX", sozlesme="", ucret="", zaman="1791723170000"):
    return {"chainIndex": "43114", "txHash": tx, "itype": itype, "methodId": "0x", "txTime": zaman,
            "from": [{"address": kimden, "amount": ""}], "to": [{"address": kime, "amount": ""}],
            "tokenContractAddress": sozlesme, "amount": miktar, "symbol": sembol, "txFee": ucret,
            "txStatus": "success", "hitBlacklist": False}


class Cevir(unittest.TestCase):
    def test_takas_yerel_ve_token_bacagi(self):
        b = cevir(A, AGLAR["Avalanche C-Chain"], [
            satir("0xs1", "0", A, R, "0.1", ucret="0.001773415055685231"),
            satir("0xs1", "2", R, A, "1.039211", sembol="USDC", sozlesme=USDC),
        ])
        self.assertEqual(len(b), 2)
        yerel = next(x for x in b if x.sozlesme is None)
        token = next(x for x in b if x.sozlesme)
        self.assertEqual((yerel.varlik, yerel.miktar), ("AVAX", Decimal("0.1")))
        self.assertEqual((token.varlik, token.miktar, token.sozlesme), ("USDC", Decimal("1.039211"), USDC))
        self.assertEqual(b.meta["0xs1"].ucret, Decimal("0.001773415055685231"))
        o = coz(A, AGLAR["Avalanche C-Chain"], b, Baglam(benim={A}))[0]
        self.assertEqual((o.tur, o.verdi, o.aldi), ("takas", {"AVAX": Decimal("0.1")}, {"USDC": Decimal("1.039211")}))

    def test_kara_liste_isareti(self):
        r = satir("0xp1", "2", R, A, "100", sembol="USDT", sozlesme="0x" + "77" * 20)
        r["hitBlacklist"] = True
        b = cevir(A, AGLAR["Avalanche C-Chain"], [r])
        self.assertEqual(b[0].token_adi, "kara liste")


class OkuyucuSirasi(unittest.TestCase):
    def test_tam_gecmis_gezginden_onchainos_yedek(self):
        for ag in ("ERC20", "Arbitrum One", "Polygon", "Avalanche C-Chain", "TRC20"):
            sira = AGLAR[ag].okuyucu
            self.assertNotEqual(sira[0], "onchainos", ag)     # OnchainOS yalnız 6 ay geriye gider
            self.assertIn("onchainos", sira, ag)
        for ag in ("BSC", "Base", "Optimism"):
            self.assertEqual(AGLAR[ag].okuyucu, ("onchainos",))

    def test_yalniz_onchainos_aginda_yalniz_benim_ve_cekim_adresleri(self):
        from veri import db as dbm
        from veri.adres import AdresKarti, yaz as adres_yaz
        from veri.borsa import Kayit
        from veri.testler.test_b4_tara import SahteOkuyucu
        from veri.zincir.tara import tara

        class Okuyucu(SahteOkuyucu):
            def okuyucular(self, ag):
                return ["onchainos"] if ag.anahtar in ("bnb", "base", "optimism") else ["sahte"]
        db = dbm.baglan(":memory:")
        benim, yabanci = "0x" + "aa" * 20, "0x" + "bb" * 20
        cek = [Kayit("cekim", "w1", 1, "AVAX", "AVAX-Avalanche C-Chain", Decimal(1), Decimal(0), "AVAX", benim, "0xc1", "2"),
               Kayit("cekim", "w2", 2, "AVAX", "AVAX-Avalanche C-Chain", Decimal(1), Decimal(0), "AVAX", yabanci, "0xc2", "2")]
        adres_yaz(db, [AdresKarti(benim, "avalanche", ["avalanche"], 3, "benim", "k", 1, 1, 1, 1, "BENIM_1", ["w1"]),
                       AdresKarti(yabanci, "avalanche", ["avalanche"], 3, "belli_degil", "k", 1, 2, 2, 0, "ADRES_1", ["w2"])], cek)
        ok = Okuyucu()
        okunan = []
        ok.oku = lambda a, ag, onbellek=True: (okunan.append((a, ag.anahtar)), SahteOkuyucu.oku(ok, a, ag))[1]
        tara(db, ok, cek, [])
        self.assertIn((benim, "base"), okunan)
        self.assertNotIn((yabanci, "base"), okunan)
        self.assertIn((yabanci, "ethereum"), okunan)

    def test_kota_dolunca_onchainos_kapanir(self):
        from veri.zincir.okuyucu import Okunamadi, ZincirOkuyucu
        from veri.zincir.onchainos import KotaDoldu
        z = ZincirOkuyucu()

        class Kotali:
            hazir = True
            n = 0

            def islemler(self, adres, ag):
                Kotali.n += 1
                raise KotaDoldu("quota")
        z._onchainos = Kotali()
        for _ in range(3):
            with self.assertRaises(Okunamadi):
                z.oku("0x" + "aa" * 20, AGLAR["Base"], onbellek=False)
        self.assertEqual(Kotali.n, 1)                           # ilk kota hatasından sonra bir daha çağrılmaz


@canli
@unittest.skipUnless(not ayar.eksikler(["ONCHAINOS_API_KEY", "ONCHAINOS_SECRET_KEY", "ONCHAINOS_PASSPHRASE"]), "OnchainOS anahtarı yok")
class CanliOnchainOS(unittest.TestCase):
    def test_11_ekim_avalanche_routescan_ile_ayni(self):
        from veri.borsa import cekimler, tamamlanan, yatirmalar
        from veri.okx_imzali import OkxTr
        from veri.zincir.onchainos import OnchainOS
        db = canli_db()
        okx = OkxTr(ayar.okx_kimlik("ana"), db, "test-onchainos")
        cek, yat = tamamlanan(cekimler(okx)), tamamlanan(yatirmalar(okx))
        c = next(k for k in cek if k.ccy == "AVAX")
        b = OnchainOS(db, "test-onchainos").islemler(c.adres, c.ag)
        self.assertEqual(b.kaynak, "onchainos")
        baglam = Baglam(benim={c.adres.lower()}, cekim_tx={k.tx.lower() for k in cek}, yatirma_tx={y.tx.lower() for y in yat})
        gun = [o for o in coz(c.adres.lower(), c.ag, b, baglam) if 1791676800000 <= o.ts < 1791763200000]
        self.assertEqual([o.tur for o in gun], ["giris", "takas", "taninmadi", "gonderim", "gonderim"])
        self.assertEqual((gun[1].verdi, gun[1].aldi), ({"AVAX": Decimal("0.1")}, {"USDC": Decimal("1.039211")}))
        self.assertEqual(gun[1].ucret.quantize(Decimal("0.000001")), Decimal("0.001773"))
        self.assertEqual(gun[2].aldi["AVAX"].quantize(Decimal("0.000001")), Decimal("0.000212"))
        net = sum((o.aldi.get("AVAX", 0) - o.verdi.get("AVAX", 0) - o.ucret for o in gun), Decimal(0))
        self.assertEqual(net.quantize(Decimal("0.000001")), Decimal("0.780825"))


if __name__ == "__main__":
    unittest.main()
