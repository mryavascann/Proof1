"""Yetki ve sınırlar: proof1 yalnız okuma yetkili OKX anahtarıyla çalışır; işlem/çekim yetkili anahtarı reddeder."""
import unittest

from veri import ayar
from veri.atk import AtkHata, yetki_denetle
from veri.testler.ortak import canli, canli_db


class YetkiDenetimi(unittest.TestCase):
    def test_yalniz_okuma_gecer(self):
        yetki_denetle("read_only")
        yetki_denetle(" read_only ")

    def test_islem_ya_da_cekim_yetkisi_reddedilir(self):
        for perm in ("read_only,trade", "trade", "read_only,withdraw", "read_only,trade,withdraw"):
            with self.assertRaises(AtkHata) as e:
                yetki_denetle(perm)
            self.assertEqual(e.exception.kod, "yazma_yetkili_anahtar", perm)


@canli
class CanliYetki(unittest.TestCase):
    def test_iki_hesabin_anahtari_yalniz_okuma(self):
        from veri.atk import Atk
        for hesap in ("alt", "ana"):
            with Atk(ayar.okx_kimlik(hesap), canli_db(), "test-yetki") as atk:
                self.assertEqual(atk.yetki, "read_only", hesap)


if __name__ == "__main__":
    unittest.main()
