"""Arşiv onarımı: gezginin (Routescan) kaçırdığı işlem ve yanlış ücret, düğümdeki geçmiş bakiyeyle bulunup düzeltilir.

Gerçek koşuda bulundu (Chiliz): Routescan'in txlist'inde bir Eylül 2024 kümesinden 12 işlem yok (nonce boşluğu; biri
kullanıcının iki adresi arasında 29 CHZ), bir EIP-1559 işleminde `gasPrice` makbuzdakinin yarısı. Gezgin verisiyle defter
zincirle kapanmıyordu. Düğümle bulunamayan değişim uydurulmaz, “açıklanamayan” kalır. Adresler yer tutucu.
"""
import unittest
from decimal import Decimal

from veri import db as dbm
from veri.hiz import Sinir
from veri.aglar import AGLAR
from veri.testler.ortak import canli, canli_db
from veri.testler.test_b4_zincir import A, B, GWEI, OKX, R, tx
from veri.zincir.evm import bacaklar
from veri.zincir.onar import Arsiv, defter_bakiyesi, onar

E18 = 10**18
HIZSIZ = Sinir(0)
CHZ = AGLAR["Chiliz Chain"]


class SahteDugum:
    """Arşiv düğümü: bloklar, makbuzlar ve geçmiş bakiye (wei) olaylardan hesaplanır."""

    def __init__(self, tepe=600):
        self.tepe = tepe
        self.olaylar = []          # (blok, adres, wei)
        self.bloklar = {}          # blok → [tx]
        self.makbuzlar = {}
        self.cagrilar = []

    def islem(self, h, blok, kimden, kime, deger, gas_used=21000, gas_price=5000 * GWEI, durum=1):
        self.bloklar.setdefault(blok, []).append({"hash": h, "from": kimden, "to": kime, "value": hex(deger),
                                                  "input": "0x8cc7104f", "nonce": "0x0", "gasPrice": hex(gas_price)})
        self.makbuzlar[h] = {"status": hex(durum), "gasUsed": hex(gas_used), "effectiveGasPrice": hex(gas_price)}
        self.olaylar.append((blok, kimden, -gas_used * gas_price))
        if durum == 1 and deger:
            self.olaylar += [(blok, kimden, -deger), (blok, kime, deger)]

    def ic(self, blok, kimden, kime, deger):            # iç işlem: top-level işlemde görünmez
        self.olaylar += [(blok, kimden, -deger), (blok, kime, deger)]

    def post(self, url, json=None, timeout=None):
        y, p = json["method"], json["params"]
        self.cagrilar.append(y)
        if y == "eth_blockNumber":
            s = hex(self.tepe)
        elif y == "eth_getBalance":
            n = int(p[1], 16)
            s = hex(sum(w for b, ad, w in self.olaylar if ad == p[0].lower() and b <= n))
        elif y == "eth_getBlockByNumber":
            n = int(p[0], 16)
            s = {"number": p[0], "timestamp": hex(1_726_000_000 + n), "transactions": self.bloklar.get(n, [])}
        elif y == "eth_getTransactionReceipt":
            s = self.makbuzlar.get(p[0])
        else:
            raise AssertionError(y)
        return _Cevap({"jsonrpc": "2.0", "id": 1, "result": s})


class _Cevap:
    def __init__(self, j):
        self._j, self.status_code, self.ok = j, 200, True

    def json(self):
        return self._j


def _satir(h, blok, kimden, kime, deger, gas_used=21000, gas_price=5000 * GWEI):
    r = tx(h, 1_726_000_000 + blok, kimden, kime, deger, gas_used=gas_used, gas_price=gas_price)
    return dict(r, blockNumber=str(blok))


def _senaryo():
    """Zincirde: giriş 200, takas (ücret 0,5; gezgin 0,25 diyor) + 1 iade, gezginde olmayan çağrı (ücret 1,1) ve
    B'den 29 CHZ, gönderim 10. Zincirdeki bakiye 118,295."""
    d = SahteDugum()
    d.islem("0xc1", 100, OKX, A, 200 * E18)
    d.islem("0xs1", 200, A, R, 100 * E18, gas_used=200000, gas_price=2500 * GWEI)
    d.ic(200, R, A, E18)
    d.islem("0xm1", 300, A, R, 0, gas_used=440000, gas_price=2500 * GWEI)
    d.islem("0xm2", 400, B, A, 29 * E18)
    d.islem("0xg1", 500, A, B, 10 * E18, gas_used=21000, gas_price=5000 * GWEI)
    gezgin = {"txlist": [_satir("0xc1", 100, OKX, A, 200 * E18),
                         _satir("0xs1", 200, A, R, 100 * E18, gas_used=200000, gas_price=1250 * GWEI),
                         _satir("0xg1", 500, A, B, 10 * E18)],
              "txlistinternal": [{"hash": "0xs1", "timeStamp": str(1_726_000_200), "blockNumber": "200", "from": R, "to": A,
                                  "value": str(E18), "isError": "0"}],
              "tokentx": []}
    return d, bacaklar(A, CHZ, gezgin)


class Onarim(unittest.TestCase):
    def test_eksik_islem_ve_yanlis_ucret_bulunur(self):
        d, b = _senaryo()
        self.assertEqual(defter_bakiyesi(A, CHZ, b), Decimal("90.645"))
        o = onar(A, CHZ, b, Arsiv(CHZ, http=d, urller=("sahte",), sinir=HIZSIZ))
        self.assertEqual((o.eksik_islem, o.ucret_duzeltme, o.aciklanamayan), (2, 1, Decimal(0)))
        self.assertTrue(o.kapandi)
        self.assertEqual(defter_bakiyesi(A, CHZ, b), Decimal("118.295"))
        self.assertEqual(b.meta["0xs1"].ucret, Decimal("0.5"))
        self.assertEqual((b.meta["0xm1"].ucret, b.meta["0xm1"].baslatan, b.meta["0xm1"].blok), (Decimal("1.1"), A, 300))
        gelen = [x for x in b if x.tx == "0xm2"]
        self.assertEqual([(x.kimden, x.kime, x.varlik, x.miktar) for x in gelen], [(B, A, "CHZ", Decimal(29))])

    def test_onarilan_islem_cozulur(self):
        from veri.zincir.cozucu import Baglam, coz
        d, b = _senaryo()
        onar(A, CHZ, b, Arsiv(CHZ, http=d, urller=("sahte",), sinir=HIZSIZ))
        olay = {o.tx: o for o in coz(A, CHZ, b, Baglam(benim={A, B}, borsa_adresleri={OKX}))}
        self.assertEqual((olay["0xm1"].tur, olay["0xm1"].ucret), ("ucret", Decimal("1.1")))
        self.assertEqual((olay["0xm2"].tur, olay["0xm2"].aldi), ("giris", {"CHZ": Decimal(29)}))

    def test_kapanan_adreste_yalniz_iki_cagri(self):
        d = SahteDugum()
        d.islem("0xc1", 100, OKX, A, 200 * E18)
        b = bacaklar(A, CHZ, {"txlist": [_satir("0xc1", 100, OKX, A, 200 * E18)]})
        o = onar(A, CHZ, b, Arsiv(CHZ, http=d, urller=("sahte",), sinir=HIZSIZ))
        self.assertTrue(o.kapandi)
        self.assertEqual(d.cagrilar, ["eth_blockNumber", "eth_getBalance"])

    def test_dugumde_de_gorunmeyen_degisim_uydurulmaz(self):
        d, b = _senaryo()
        d.ic(450, R, A, 3 * E18)                       # iç işlemle gelen 3 CHZ: gezginde de blokta da yok
        n = len(b)
        o = onar(A, CHZ, b, Arsiv(CHZ, http=d, urller=("sahte",), sinir=HIZSIZ))
        self.assertEqual(o.aciklanamayan, Decimal(3))
        self.assertFalse(o.kapandi)
        self.assertEqual(len(b), n + 1)                 # yalnız 0xm2 eklendi; 3 CHZ için bacak yok
        self.assertEqual(defter_bakiyesi(A, CHZ, b), Decimal("118.295"))

    def test_blogu_bilinmeyen_veri_onarilmaz(self):
        d, b = _senaryo()
        for x in b:
            x.blok = 0
        o = onar(A, CHZ, b, Arsiv(CHZ, http=d, urller=("sahte",), sinir=HIZSIZ))
        self.assertEqual(d.cagrilar, [])
        self.assertFalse(o.kapandi)

    def test_onbellek_blogu_tasir_eskisi_acilir(self):
        from veri.zincir.okuyucu import _ac, _paketle
        _, b = _senaryo()
        geri = _ac(__import__("json").loads(__import__("json").dumps(_paketle(b))), "routescan")
        self.assertEqual([x.blok for x in geri], [x.blok for x in b])
        self.assertEqual(geri.meta["0xs1"].blok, 200)
        eski = _ac({"bacak": [["0xc1", 1, OKX, A, "CHZ", "200", None, ""]], "meta": [["0xc1", 1, OKX, A, "0", "", True]]}, "r")
        self.assertEqual((eski[0].blok, eski.meta["0xc1"].blok), (0, 0))

    def test_okuyucu_onarir_ve_saklar(self):
        from veri.zincir.okuyucu import ZincirOkuyucu
        d, b = _senaryo()
        db = dbm.baglan(":memory:")
        z = ZincirOkuyucu(db)

        class Gezgin:
            def destekler(self, ag):
                return ag.anahtar == "chiliz"

            def islemler(self, adres, ag):
                b.kaynak = "routescan"
                return b

        z.gezginler = {"etherscan": Gezgin(), "routescan": Gezgin()}
        import veri.zincir.onar as onar_mod
        eski = onar_mod.Arsiv
        onar_mod.Arsiv = lambda ag, db=None, oturum=None: eski(ag, db, oturum, http=d, urller=("sahte",), sinir=HIZSIZ)
        try:
            okunan = z.oku(A, CHZ)
        finally:
            onar_mod.Arsiv = eski
        self.assertEqual(defter_bakiyesi(A, CHZ, okunan), Decimal("118.295"))
        self.assertEqual(defter_bakiyesi(A, CHZ, z._bellek(A, CHZ)), Decimal("118.295"))
        self.assertTrue(db.execute("SELECT COUNT(*) FROM cagri WHERE ad LIKE '%arşiv%'").fetchone()[0] > 0)


@canli
class CanliChiliz(unittest.TestCase):
    def test_chiliz_cekim_adresleri_zincirle_kapanir(self):
        from veri.borsa import cekimler, tamamlanan
        from veri.okx_imzali import OkxTr
        from veri import ayar
        from veri.zincir.okuyucu import ZincirOkuyucu
        db = canli_db()
        okx = OkxTr(ayar.okx_kimlik("ana"), db, "test-b4-onar")
        adresler = sorted({c.adres.lower() for c in tamamlanan(cekimler(okx)) if c.ag and c.ag.anahtar == "chiliz"})
        self.assertTrue(adresler)
        z = ZincirOkuyucu(db, "test-b4-onar")
        farklar = []
        for a in adresler:
            b = z.oku(a, CHZ)
            zincir = z.bakiye(a, CHZ)
            farklar.append(abs(zincir - defter_bakiyesi(a, CHZ, b)))
        self.assertLess(max(farklar), Decimal("0.001"), [str(f.quantize(Decimal("0.000001"))) for f in farklar])


if __name__ == "__main__":
    unittest.main()
