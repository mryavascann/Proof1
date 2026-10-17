"""M3 kabul: sayı ve olgu denetimi. Devirdeki gerçek tuzaklar ve örnek veritabanı olguları."""
import unittest

from anlatim.denetim import Olgu, denetle, sayilari_ayikla

# ornek-2026-10-12 ve sabah-2026-10-17 oturumlarından (ortak/ornek/proof1_ornek.db)
O1 = Olgu("o1", "cekim", {"tarih": "11 Ekim 2026 15:32", "miktar": "0,9828 AVAX", "ag": "Avalanche",
                          "ucret": "0,015 AVAX", "adres": "BENIM_1"})
O3 = Olgu("o3", "taninmadi", {"tarih": "11 Ekim 2026 15:53", "miktar": "0,000212 AVAX", "adres": "BENIM_1"})
O9 = Olgu("o9", "moca_takas", {"tarih": "9 Nisan 2026", "verilen": "46,15 PIEVERSE", "alinan": "1.587 MOCA",
                               "ag_ucreti": "0,000129 ETH", "verilen_dolar": "bilinmiyor", "adres": "ADRES_MOCA"})
O3A = Olgu("o3", "ag_payi", {"ag": "Arbitrum", "cekim_sayisi": "17", "dolar": "20.889 $", "pay": "%43,2"})
O4A = Olgu("o4", "ag_payi", {"ag": "Ethereum", "cekim_sayisi": "14", "dolar": "16.244 $", "pay": "%34,1"})
O11 = Olgu("o11", "bot_uyusmazlik", {"bot": "USDT/TRY spot grid", "kayit_sonuc": "+99,89 TL",
                                     "gercek_sonuc": "-0,22 TL", "donen_kote": "199,67 TL", "donen_coin": "2,03 USDT"})
GIZLI = Olgu("o20", "bakiye", {"yer": "borsa", "miktar": "4.321,00 TL"}, gizli=True)


def cevap(metin, olgular):
    return {"id": "g1", "metin": metin, "olgular": olgular}


class DevirTuzaklari(unittest.TestCase):
    def test_kendi_hesapladigi_yuzde_duser(self):
        s = denetle(cevap("Paranın %77,3'ü Arbitrum ve Ethereum'a gitti.", ["o3", "o4"]), [O3A, O4A])
        self.assertFalse(s.gecti)

    def test_gizli_bakiye_duser(self):
        s = denetle(cevap("Borsadaki bakiye 4.321,00 TL.", ["o20"]), [GIZLI, O1])
        self.assertFalse(s.gecti)
        s = denetle(cevap("Borsadaki bakiye 4.321,00 TL.", ["o1"]), [GIZLI, O1])
        self.assertFalse(s.gecti)

    def test_taninmayan_giris_gecer(self):
        s = denetle(cevap("0,000212 AVAX'lık bir giriş geldi; kaynağını tanıyamadım.", ["o3"]), [O3])
        self.assertTrue(s.gecti, s.neden)

    def test_cekim_cumlesi_gecer(self):
        s = denetle(cevap("11.10.2026 15:32'de 0,9828 AVAX çektin; çekim ücreti 0,015 AVAX.", ["o1"]), [O1])
        self.assertTrue(s.gecti, s.neden)

    def test_baska_gorevin_saati_duser(self):
        # o3'ün saati (15:53) o1 görevinde kullanılıyor.
        s = denetle(cevap("11.10.2026 15:53'te 0,9828 AVAX çektin.", ["o1"]), [O1])
        self.assertFalse(s.gecti)
        # o3'e atıf yapsa bile o3 bu görevin olgusu değil.
        s = denetle(cevap("11.10.2026 15:53'te 0,9828 AVAX çektin.", ["o1", "o3"]), [O1])
        self.assertFalse(s.gecti)


class Kurallar(unittest.TestCase):
    def test_moca_cumlesi_gecer(self):
        s = denetle(cevap("09.04.2026: 46,15 PIEVERSE verip 1.587 MOCA aldın; ağ ücreti 0,000129 ETH.", ["o9"]), [O9])
        self.assertTrue(s.gecti, s.neden)

    def test_verilen_alinan_yer_degistirince_duser(self):
        s = denetle(cevap("1.587 MOCA verip 46,15 PIEVERSE aldın.", ["o9"]), [O9])
        self.assertFalse(s.gecti)

    def test_isaret_esdeger_degil(self):
        self.assertFalse(denetle(cevap("Gerçek sonuç +0,22 TL.", ["o11"]), [O11]).gecti)
        self.assertFalse(denetle(cevap("Gerçek sonuç 0,22 TL.", ["o11"]), [O11]).gecti)
        self.assertTrue(denetle(cevap("Gerçek sonuç -0,22 TL.", ["o11"]), [O11]).gecti)
        self.assertTrue(denetle(cevap("Gerçek sonuç −0,22 TL.", ["o11"]), [O11]).gecti)

    def test_birim_dogrulanir(self):
        self.assertFalse(denetle(cevap("Çekim ücreti 0,015 ETH.", ["o1"]), [O1]).gecti)
        self.assertFalse(denetle(cevap("Çekim ücreti 0,015.", ["o1"]), [O1]).gecti)

    def test_yuvarlama_duser(self):
        self.assertFalse(denetle(cevap("0,98 AVAX çektin.", ["o1"]), [O1]).gecti)

    def test_birimsiz_sayilar(self):
        s = denetle(cevap("Arbitrum'a 17 çekimle 20.889 $ gitti.", ["o3"]), [O3A])
        self.assertTrue(s.gecti, s.neden)
        self.assertFalse(denetle(cevap("Arbitrum'a 18 çekimle 20.889 $ gitti.", ["o3"]), [O3A]).gecti)

    def test_olgu_kimligi_sayi_sayilmaz(self):
        s = denetle(cevap("0,000212 AVAX'lık bir giriş geldi (o3).", ["o3"]), [O3])
        self.assertTrue(s.gecti, s.neden)

    def test_atifsiz_cevap_duser(self):
        self.assertFalse(denetle(cevap("0,000212 AVAX geldi.", []), [O3]).gecti)

    def test_yanlis_tarih_duser(self):
        self.assertFalse(denetle(cevap("12 Ekim'de 0,9828 AVAX çektin.", ["o1"]), [O1]).gecti)
        self.assertTrue(denetle(cevap("11 Ekim'de 0,9828 AVAX çektin.", ["o1"]), [O1]).gecti)

    def test_bos_metin_duser(self):
        self.assertFalse(denetle(cevap("  ", ["o1"]), [O1]).gecti)


class Ayiklama(unittest.TestCase):
    def test_turkce_sayi_ve_birim(self):
        sayilar = [(str(s.deger), s.birim) for s in sayilari_ayikla("1.587 MOCA, 46,15 PIEVERSE ve 12.611,90 $ ile %43,2")]
        self.assertEqual(sayilar, [("1587", "MOCA"), ("46.15", "PIEVERSE"), ("12611.90", "$"), ("43.2", "%")])


if __name__ == "__main__":
    unittest.main()
