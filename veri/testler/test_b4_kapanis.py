"""Chiliz kapanışı: yeniden taramada işlemin neti değişirse eski hareket satırı kalmaz (defter zincirle kapanır).

Gerçek koşuda bulundu: sayfalama gelmeden önceki taramada takasın txlist bacağı görünmemiş, yalnız iç işlemdeki CHZ
iadesi görünmüştü → `…:CHZ:al` satırı yazıldı. Tam veriyle aynı işlem `…:CHZ:ver` oldu; eski `al` satırı silinmediği için
defter zincirden fazla çıktı. Adresler yer tutucu.
"""
import unittest
from decimal import Decimal

from veri import db as dbm
from veri.adres import AdresKarti, yaz as adres_yaz
from veri.borsa import Kayit
from veri.defter import cekim_hareketleri, yaz as hyaz
from veri.testler.test_b4_zincir import A, GWEI, OKX, R, tok, tx
from veri.zincir.evm import Bacaklar, bacaklar
from veri.zincir.tara import kapanislar, tara

E18 = 10**18
FAN = "0x" + "ef" * 20                    # taraftar tokenı sözleşmesi (yer tutucu)
GIRIS = tx("0xc1", 1791722030, OKX, A, 200 * E18, gas_price=2500 * GWEI)
TAKAS = tx("0xs1", 1791723170, A, R, 100 * E18, gas_used=200000, gas_price=2500 * GWEI)      # ücret 0,5 CHZ
IADE = {"hash": "0xs1", "timeStamp": "1791723170", "from": R, "to": A, "value": str(E18), "isError": "0"}
TOKEN = tok("0xs1", 1791723170, R, A, 62, sembol="BAR", ondalik=0, sozlesme=FAN, ad="FC Barcelona Fan Token")
TAM = {"txlist": [GIRIS, TAKAS], "txlistinternal": [IADE], "tokentx": [TOKEN]}
ZINCIR = Decimal("100.5")                 # 200 − 100 + 1 − 0,5


class ChilizOkuyucu:
    """Yalnız Chiliz'i okur; `veri` taramalar arasında değiştirilir."""

    def __init__(self, veri):
        self.veri = veri

    def okuyucular(self, ag):
        return ["sahte"] if ag.anahtar == "chiliz" else []

    def oku(self, adres, ag, onbellek=True):
        b = bacaklar(adres, ag, self.veri) if ag.anahtar == "chiliz" else Bacaklar()
        b.kaynak = "sahte"
        return b

    def bakiye(self, adres, ag):
        return ZINCIR if ag.anahtar == "chiliz" else None


class YenidenTarama(unittest.TestCase):
    def setUp(self):
        self.db = dbm.baglan(":memory:")
        self.cek = [Kayit("cekim", "w1", 1791722000000, "CHZ", "CHZ-Chiliz Chain", Decimal("200"), Decimal("1"),
                          "CHZ", A, "0xc1", "2")]
        hyaz(self.db, cekim_hareketleri(self.cek))
        adres_yaz(self.db, [AdresKarti(A, "chiliz", ["chiliz"], 3, "benim", "k", 1, 1, 2, 1, "BENIM_1", ["w1"])], self.cek)

    def _tara(self, veri):
        tara(self.db, ChilizOkuyucu(veri), self.cek, [], borsa_adresleri={OKX})

    def _kapanis(self):
        return next(x for x in kapanislar(self.db) if x["ag"] == "chiliz")

    def _zincir_satirlari(self):
        return {r["ham_kimlik"].split(":", 3)[3]: Decimal(r["miktar"]) for r in self.db.execute(
            "SELECT ham_kimlik, miktar FROM hareket WHERE kaynak='zincir' AND ag='chiliz'")}

    def test_tam_veri_kapanir(self):
        self._tara(TAM)
        self.assertEqual(Decimal(self._kapanis()["fark"]), 0)

    def test_yon_degisen_islemin_eski_satiri_silinir(self):
        self._tara({"txlist": [GIRIS], "txlistinternal": [IADE], "tokentx": [TOKEN]})     # takasın txlist'i eksik
        self.assertEqual(self._zincir_satirlari()["0xs1:CHZ:al"], Decimal(1))
        self._tara(TAM)
        s = self._zincir_satirlari()
        self.assertNotIn("0xs1:CHZ:al", s)
        self.assertEqual(s["0xs1:CHZ:ver"], Decimal(-99))
        self.assertEqual(Decimal(self._kapanis()["fark"]), 0)
        olay = self.db.execute("SELECT tur FROM _olay WHERE tx='0xs1'").fetchall()
        self.assertEqual([r["tur"] for r in olay], ["takas"])

    def test_tutari_degisen_satir_guncellenir(self):
        self._tara({"txlist": [GIRIS, TAKAS], "txlistinternal": [], "tokentx": []})       # iade eksik
        self.assertEqual(self._zincir_satirlari()["0xs1:CHZ:ver"], Decimal(-100))
        self.db.execute("UPDATE hareket SET dolar='-5' WHERE ham_kimlik LIKE '%0xs1:CHZ:ver'")
        self._tara(TAM)
        r = self.db.execute("SELECT miktar, dolar FROM hareket WHERE ham_kimlik LIKE '%0xs1:CHZ:ver'").fetchone()
        self.assertEqual((Decimal(r["miktar"]), r["dolar"]), (Decimal(-99), None))    # eski dolar yeni tutara ait değil
        self.assertEqual(Decimal(self._kapanis()["fark"]), 0)

    def test_borsa_satirlarina_dokunulmaz(self):
        once = self.db.execute("SELECT COUNT(*) FROM hareket WHERE kaynak!='zincir'").fetchone()[0]
        self._tara(TAM)
        self._tara({"txlist": [GIRIS], "txlistinternal": [], "tokentx": []})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM hareket WHERE kaynak!='zincir'").fetchone()[0], once)


if __name__ == "__main__":
    unittest.main()
