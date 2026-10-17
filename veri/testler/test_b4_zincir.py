"""B4 kabul: zincir okuyucu ve çözücü. Adrese giren/çıkan + ağ ücreti; verdi/aldı/ücret; şüpheli ve tanınmayan."""
import unittest
from decimal import Decimal

from veri import ayar
from veri.aglar import AGLAR
from veri.testler.ortak import DEVIR_KESIM_MS, canli, canli_db
from veri.zincir.cozucu import Baglam, coz, supheli_token_mu, zehirleme_mi
from veri.zincir.evm import bacaklar

A = "0x" + "aa" * 20      # kullanıcının adresi (yer tutucu)
B = "0x" + "bb" * 20      # ikinci hesap
R = "0x" + "cc" * 20      # takas yönlendiricisi
OKX = "0x" + "dd" * 20    # borsanın sıcak cüzdanı
YABANCI = "0x" + "ee" * 20
USDC = "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e"   # Avalanche'ın resmi USDC sözleşmesi (herkese açık)
GWEI = 10**9


def tx(h, ts, frm, to, deger, gas_used=21000, gas_price=25 * GWEI, fn="", err="0"):
    return {"hash": h, "timeStamp": str(ts), "blockNumber": "1", "from": frm, "to": to, "value": str(deger),
            "gasUsed": str(gas_used), "gasPrice": str(gas_price), "functionName": fn, "isError": err}


def tok(h, ts, frm, to, deger, sembol="USDC", ondalik=6, sozlesme=USDC, ad="USD Coin"):
    return {"hash": h, "timeStamp": str(ts), "blockNumber": "1", "from": frm, "to": to, "value": str(deger),
            "tokenSymbol": sembol, "tokenDecimal": str(ondalik), "contractAddress": sozlesme, "tokenName": ad}


# 11 Ekim 2026 Avalanche günü (yapı gerçek kayıttan; adresler yer tutucu).
GUN = {
    "txlist": [
        tx("0xc1", 1791722030, OKX, A, 982802210000000000),
        tx("0xs1", 1791723170, A, R, 10**17, gas_used=70937, gas_price=25000000785),
        tx("0xu1", 1791723221, YABANCI, A, 211981558425000, gas_used=21000, gas_price=5 * GWEI),
        tx("0xg1", 1791723222, A, B, 10**17, gas_used=21000, gas_price=5000000157),
        tx("0xg2", 1791723235, A, USDC, 0, gas_used=62159, gas_price=5000080000, fn="transfer(address to, uint256 value)"),
    ],
    "txlistinternal": [],
    "tokentx": [
        tok("0xs1", 1791723170, R, A, 1039211),
        tok("0xg2", 1791723235, A, B, 1000000),
    ],
}


class Cozucu(unittest.TestCase):
    def setUp(self):
        self.ag = AGLAR["Avalanche C-Chain"]
        self.b = Baglam(benim={A, B}, cekim_tx={"0xc1"}, yatirma_tx=set(), borsa_adresleri={OKX})
        self.olaylar = coz(A, self.ag, bacaklar(A, self.ag, GUN), self.b)
        self.tur = {o.tx: o.tur for o in self.olaylar}

    def test_turler(self):
        self.assertEqual(self.tur, {"0xc1": "giris", "0xs1": "takas", "0xu1": "taninmadi", "0xg1": "gonderim", "0xg2": "gonderim"})

    def test_takas_verdi_aldi_ucret(self):
        o = next(o for o in self.olaylar if o.tx == "0xs1")
        self.assertEqual(o.verdi, {"AVAX": Decimal("0.1")})
        self.assertEqual(o.aldi, {"USDC": Decimal("1.039211")})
        self.assertEqual(o.ucret.quantize(Decimal("0.000001")), Decimal("0.001773"))

    def test_giriste_ucret_yok_ve_karsi_borsa(self):
        o = next(o for o in self.olaylar if o.tx == "0xc1")
        self.assertEqual((o.ucret, o.karsi), (Decimal(0), "ana"))

    def test_gonderim_alicisi_benim(self):
        o = next(o for o in self.olaylar if o.tx == "0xg2")
        self.assertEqual(o.verdi, {"USDC": Decimal("1")})
        self.assertEqual(o.karsi_adres, B)
        self.assertEqual(o.ucret.quantize(Decimal("0.000001")), Decimal("0.000311"))

    def test_defter_kapanir(self):
        bakiye = Decimal(0)
        for o in self.olaylar:
            bakiye += o.aldi.get("AVAX", 0) - o.verdi.get("AVAX", 0) - o.ucret
        self.assertEqual(bakiye.quantize(Decimal("0.000001")), Decimal("0.780825"))

    def test_hareket_satirlari(self):
        from veri.zincir.cozucu import hareketlere
        h = hareketlere(self.olaylar, adres_id=7, ag="avalanche", kaynak="routescan", etiketle=lambda a: "BENIM_2" if a == B else None)
        ucretler = [x for x in h if x["tur"] == "ucret"]
        self.assertEqual(len(ucretler), 3)          # yalnız kullanıcının başlattığı işlemler
        self.assertTrue(all(x["hesap"] == "cuzdan" and x["adres_id"] == 7 for x in h))
        self.assertEqual(sum(Decimal(x["miktar"]) for x in h if x["varlik"] == "AVAX").quantize(Decimal("0.000001")), Decimal("0.780825"))
        self.assertIn("BENIM_2", {x["karsi"] for x in h})


class Supheli(unittest.TestCase):
    def test_sahte_token(self):
        self.assertTrue(supheli_token_mu("USDC​", "USD Coin", "0x" + "99" * 20, "avalanche"))
        self.assertTrue(supheli_token_mu("USDC", "USD Coin", "0x" + "99" * 20, "avalanche"))   # resmi sözleşme değil
        self.assertTrue(supheli_token_mu("Visit claim-usdt.com", "x", "0x" + "98" * 20, "ethereum"))
        self.assertFalse(supheli_token_mu("MOCA", "Moca Coin", "0x" + "97" * 20, "ethereum"))

    def test_adres_zehirleme(self):
        hedef = "0xabcd" + "1" * 32 + "9876"
        taklit = "0xabcd" + "2" * 32 + "9876"
        self.assertTrue(zehirleme_mi(taklit, {hedef}))
        self.assertFalse(zehirleme_mi(hedef, {hedef}))
        self.assertFalse(zehirleme_mi("0x" + "3" * 40, {hedef}))

    def test_supheli_token_girisi_isaretlenir(self):
        ag = AGLAR["ERC20"]
        veri = {"txlist": [], "txlistinternal": [],
                "tokentx": [tok("0xp1", 1, YABANCI, A, 10**6, sembol="USDT", sozlesme="0x" + "77" * 20, ad="Tether USD")]}
        o = coz(A, ag, bacaklar(A, ag, veri), Baglam(benim={A}))[0]
        self.assertTrue(o.supheli)
        self.assertEqual(o.tur, "taninmadi")

    def test_zehirleme_uyarir_ama_yerel_coin_defterde_kalir(self):
        from veri.zincir.cozucu import hareketlere
        ag = AGLAR["Polygon"]
        taklit = A[:6] + "9" * 32 + A[-4:]            # ilk/son 4 karakter tanıdık adresle aynı (42 karakter)
        veri = {"txlist": [tx("0xz1", 1, taklit, A, 10**18)], "txlistinternal": [], "tokentx": []}
        o = coz(A, ag, bacaklar(A, ag, veri), Baglam(benim={A}, bilinen={A}))[0]
        self.assertEqual((o.supheli, o.neden), (True, "adres_zehirleme"))
        h = hareketlere([o], 1, "polygon", "t")
        self.assertEqual([(x["varlik"], x["supheli"]) for x in h], [("POL", 0)])    # gerçek coin: bakiyede var

    def test_sahte_token_bacagi_supheli_yerel_bacak_degil(self):
        from veri.zincir.cozucu import hareketlere
        ag = AGLAR["ERC20"]
        veri = {"txlist": [tx("0xm1", 1, YABANCI, A, 10**17)], "txlistinternal": [],
                "tokentx": [tok("0xm1", 1, YABANCI, A, 10**6, sembol="USDT", sozlesme="0x" + "77" * 20, ad="Tether USD")]}
        o = coz(A, ag, bacaklar(A, ag, veri), Baglam(benim={A}))[0]
        h = {x["varlik"]: x["supheli"] for x in hareketlere([o], 1, "ethereum", "t")}
        self.assertEqual(h, {"ETH": 0, "USDT": 1})

    def test_okunamayan_bacak_atlanir(self):
        ag = AGLAR["ERC20"]
        veri = {"txlist": [{"hash": "0x1", "timeStamp": "x", "from": A, "to": B, "value": "abc"}], "txlistinternal": [], "tokentx": []}
        self.assertEqual(bacaklar(A, ag, veri), [])


@canli
class CanliZincir(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from veri.borsa import cekimler, tamamlanan, yatirmalar
        from veri.okx_imzali import OkxTr
        from veri.zincir.okuyucu import ZincirOkuyucu
        cls.db = canli_db()
        okx = OkxTr(ayar.okx_kimlik("ana"), cls.db, "test-b4")
        cls.cek = tamamlanan(cekimler(okx))
        cls.yat = tamamlanan(yatirmalar(okx))
        cls.okuyucu = ZincirOkuyucu(cls.db, "test-b4")

    def _olaylar(self, adres, ag):
        b = Baglam(benim={adres.lower()}, cekim_tx={c.tx.lower() for c in self.cek},
                   yatirma_tx={y.tx.lower() for y in self.yat})
        return coz(adres.lower(), ag, self.okuyucu.oku(adres, ag), b)

    def test_11_ekim_avalanche(self):
        c = next(k for k in self.cek if k.ccy == "AVAX")
        olaylar = self._olaylar(c.adres, c.ag)
        gun = [o for o in olaylar if 1791676800 <= o.ts // 1000 < 1791763200]
        turler = [o.tur for o in gun]
        self.assertEqual(turler, ["giris", "takas", "taninmadi", "gonderim", "gonderim"])
        takas = gun[1]
        self.assertEqual((takas.verdi, takas.aldi), ({"AVAX": Decimal("0.1")}, {"USDC": Decimal("1.039211")}))
        self.assertEqual(takas.ucret.quantize(Decimal("0.000001")), Decimal("0.001773"))
        self.assertEqual(gun[2].aldi["AVAX"].quantize(Decimal("0.000001")), Decimal("0.000212"))
        self.assertEqual([o.ucret.quantize(Decimal("0.000001")) for o in gun[3:]], [Decimal("0.000105"), Decimal("0.000311")])
        net = lambda ol: sum((o.aldi.get("AVAX", 0) - o.verdi.get("AVAX", 0) - o.ucret for o in ol), Decimal(0))
        # Günün akışı 0,780825 AVAX (adreste Ağustos'tan 0,000007 AVAX toz vardı).
        self.assertEqual(net(gun).quantize(Decimal("0.000001")), Decimal("0.780825"))
        # Defter (bütün geçmiş) zincirdeki bakiyeye toz farkıyla kapanır.
        zincir = self.okuyucu.gezginler["routescan"].bakiye(c.adres, c.ag)
        self.assertLess(abs(net(olaylar) - zincir), Decimal("0.00001"))

    def test_moca_ethereum(self):
        # MOCA adresi Chiliz/Polygon çekimlerinin gittiği bir EVM adresi: EVM adresleri her ağda okunur.
        adresler = {k.adres.lower() for k in self.cek if k.adres.startswith("0x")}
        bulunan = None
        for a in sorted(adresler):
            olaylar = self._olaylar(a, AGLAR["ERC20"])
            if any("PIEVERSE" in o.verdi for o in olaylar):
                bulunan = olaylar
                break
        self.assertIsNotNone(bulunan, "MOCA adresi bulunamadı")
        moca = sum((o.aldi.get("MOCA", 0) - o.verdi.get("MOCA", 0) for o in bulunan), Decimal(0))
        self.assertEqual(moca.quantize(Decimal(1)), Decimal(5653))
        takas = [o for o in bulunan if o.tur == "takas" and "PIEVERSE" in o.verdi]
        self.assertEqual(len(takas), 1)
        self.assertEqual(takas[0].verdi["PIEVERSE"], Decimal("46.15"))
        self.assertEqual(takas[0].aldi["MOCA"].quantize(Decimal(1)), Decimal("1587"))
        self.assertEqual(takas[0].ucret.quantize(Decimal("0.000001")), Decimal("0.000129"))
        stake = [o for o in bulunan if "MOCA" in o.verdi and "stake" in (o.islev or "").lower()]
        self.assertEqual(len(stake), 1)
        self.assertEqual(stake[0].verdi["MOCA"], Decimal("100"))


if __name__ == "__main__":
    unittest.main()
