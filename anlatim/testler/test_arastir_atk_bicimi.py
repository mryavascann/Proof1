"""Araştırma gözlemleri ATK'nın gerçek (iç içe) cevap biçimini okur.

Canlı provada (17 Ekim 15:45) iz "Botun kaydı: None grid, yatırım 0", "0 alt emir", "bota giren bulunamadı" yazdı;
oysa çağrılar veri döndürmüştü. Gerçek cevap: {"tool", "ok", "data": {"endpoint", "requestTime", "data": [satırlar]}}.
"""
import unittest
from decimal import Decimal

from anlatim.arastir import gozlem_alt, gozlem_defter, gozlem_detay
from veri.testler.test_b2_defter import BOT_16_EKIM
from veri.testler.test_b5_bot import BOT_16


def gercek(satirlar: list) -> dict:
    return {"tool": "x", "ok": True, "data": {"endpoint": "GET /x", "requestTime": "2026-10-17T12:45:30Z", "data": satirlar},
            "capabilities": {}, "timestamp": "2026-10-17T12:45:30Z"}


class GercekBicim(unittest.TestCase):
    def test_emir_ayrintisi(self):
        bulgu = {}
        metin = gozlem_detay(gercek([BOT_16]), bulgu)
        self.assertIn("USDT-TRY grid", metin)
        self.assertEqual(bulgu["yatirim"], Decimal("300"))
        self.assertEqual(bulgu["kayit_pnl"].quantize(Decimal("0.01")), Decimal("99.89"))

    def test_alt_emirler(self):
        bulgu = {}
        self.assertEqual(gozlem_alt(gercek([{"ordId": "1"}, {"ordId": "2"}]), bulgu), "2 alt emir okundu.")

    def test_defter_bota_giren_ve_donen(self):
        bulgu = {"cTime": int(BOT_16["cTime"]), "uTime": int(BOT_16["uTime"])}
        metin = gozlem_defter(gercek(list(reversed(BOT_16_EKIM))), bulgu)
        self.assertNotIn("bulunamadı", metin)
        self.assertEqual(bulgu["giris"]["TRY"], Decimal("-300.00000000000"))
        self.assertEqual(bulgu["donus"]["USDT"], Decimal("2.027828940000000"))

    def test_duz_liste_ve_eski_kayit_bicimi_de_okunur(self):
        self.assertEqual(gozlem_alt([{"a": 1}], {}), "1 alt emir okundu.")
        self.assertEqual(gozlem_alt({"data": [{"a": 1}, {"a": 2}]}, {}), "2 alt emir okundu.")


if __name__ == "__main__":
    unittest.main()
