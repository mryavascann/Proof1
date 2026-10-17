"""Türkçe sayı biçimi (olgular ve sayı denetimi bunu kullanır). Örnekler devir metninden."""
import unittest
from decimal import Decimal

from veri import bicim


class Bicim(unittest.TestCase):
    def test_devir_ornekleri(self):
        self.assertEqual(bicim.miktar(Decimal("0.98280221"), "AVAX"), "0,9828 AVAX")
        self.assertEqual(bicim.miktar(Decimal("46.15"), "PIEVERSE"), "46,15 PIEVERSE")
        self.assertEqual(bicim.miktar(Decimal("1587"), "MOCA"), "1.587 MOCA")
        self.assertEqual(bicim.miktar(Decimal("0.000129"), "ETH"), "0,000129 ETH")
        self.assertEqual(bicim.miktar(Decimal("0.000211981558"), "AVAX"), "0,000212 AVAX")
        self.assertEqual(bicim.miktar(Decimal("0.1"), "AVAX"), "0,1 AVAX")
        self.assertEqual(bicim.miktar(Decimal("5653"), "MOCA"), "5.653 MOCA")
        self.assertEqual(bicim.miktar(Decimal("38508"), "CHZ"), "38.508 CHZ")
        self.assertEqual(bicim.sayi(Decimal("-0.99780221")), "-0,9978")

    def test_para(self):
        self.assertEqual(bicim.dolar(Decimal("47987.4")), "47.987 $")
        self.assertEqual(bicim.dolar(Decimal("11.7749")), "11,77 $")
        self.assertEqual(bicim.dolar(Decimal("360")), "360 $")
        self.assertEqual(bicim.tl(Decimal("99.891"), isaretli=True), "+99,89 TL")
        self.assertEqual(bicim.tl(Decimal("-0.2203")), "-0,22 TL")
        self.assertEqual(bicim.tl(Decimal("300")), "300,00 TL")
        self.assertEqual(bicim.yuzde(Decimal("33.296")), "%33,3")

    def test_tarih_istanbul(self):
        self.assertEqual(bicim.tarih(1791721943000), "11 Ekim 2026 15:32")
        self.assertEqual(bicim.tarih("2026-04-09T10:00:00Z", saat=False), "9 Nisan 2026")
        self.assertEqual(bicim.gun("2026-10-16T21:30:00Z"), "2026-10-17")


if __name__ == "__main__":
    unittest.main()
