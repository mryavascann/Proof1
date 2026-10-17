"""Bot uyuşmazlığı kalıbı durdurma zamanını söyler: aynı sonuçlu iki bot panoda tekrar gibi görünmesin
(17 Ekim: 16 Ekim botu ve prova botu ikisi de "+99,89 TL / -0,22 TL" idi)."""
import unittest

from anlatim import kalip
from anlatim.anlat import Olgu


def bot(durdurma):
    return Olgu("o1", "bot_uyusmazlik", {"bot": "USDT/TRY spot grid", "kayit_sonuc": "+99,89 TL",
                                        "gercek_sonuc": "-0,22 TL", "durdurma": durdurma})


class BotTarihi(unittest.TestCase):
    def test_iki_botun_metni_farkli(self):
        a = kalip.olgu_cumlesi(bot("16 Ekim 2026 16:00"))
        b = kalip.olgu_cumlesi(bot("17 Ekim 2026 15:45"))
        self.assertNotEqual(a, b)
        self.assertIn("16 Ekim 2026 16:00", a)
        self.assertIn("+99,89 TL", a)

    def test_calisan_botta_tarih_yok(self):
        self.assertNotIn("Durdurma", kalip.olgu_cumlesi(bot("çalışıyor")))


if __name__ == "__main__":
    unittest.main()
