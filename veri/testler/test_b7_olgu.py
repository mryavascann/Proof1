"""B7 kabul: olgular. Sayıları kod hesaplar (Türkçe metin), gizli alanlar işaretli, adres yok; kalıp cümle denetimden geçer."""
import json
import re
import unittest
from decimal import Decimal

from veri import db as dbm
from veri.adres import AdresKarti, yaz as adres_yaz
from veri.borsa import Kayit
from veri.bot import karsilastir
from veri.defter import ayristir, cekim_hareketleri, hareketlere as dh, yaz as hyaz, zincirle
from veri.kopru import kopru_kur
from veri.olgu import OlguYazici, kalip_cumle, olgulari_kur
from veri.testler.test_b2_defter import BOT_16_EKIM
from veri.testler.test_b4_tara import SahteOkuyucu
from veri.testler.test_b4_zincir import A, OKX
from veri.testler.test_b5_bot import BOT_16
from veri.testler.test_b6_kopru import BAS, BIT, sabit_fiyat
from veri.zincir.tara import tara

SAYI = re.compile(r"[-+]?\d[\d.,]*")
TURKCE = re.compile(r"^[-+]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")
GERCEK_ADRES = re.compile(r"0x[0-9a-fA-F]{40}|\bT[1-9A-HJ-NP-Za-km-z]{33}\b")


def sayilar(metin: str) -> list[str]:
    return [s.rstrip(".,") for s in SAYI.findall(metin)]


class Olgular(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = dbm.baglan(":memory:")
        cek = [Kayit("cekim", "w1", 1791721943000, "AVAX", "AVAX-Avalanche C-Chain", Decimal("0.98280221"),
                     Decimal("0.015"), "AVAX", A, "0xc1", "2"),
               Kayit("cekim", "w2", 1791000000000, "USDT", "USDT-Arbitrum One", Decimal("2310"), Decimal("0.57"),
                     "USDT", A, "0xa1", "2")]
        hyaz(db, cekim_hareketleri(cek))
        adres_yaz(db, [AdresKarti(A, "avalanche", ["arbitrum", "avalanche"], 3, "benim", "k", 2, 1, 2, 1, "BENIM_1", ["w1", "w2"])], cek)
        tara(db, SahteOkuyucu(), cek, [], borsa_adresleri={OKX})
        s = ayristir(BOT_16_EKIM, "alt", "account_get_bills")
        zincirle(s)
        hyaz(db, dh(s))
        bot = karsilastir(BOT_16, dh(s), lambda c, t: Decimal("49.367"))
        kopru = kopru_kur(db, "2026-10-12", BAS, BIT, sabit_fiyat)
        cls.db = db
        cls.oturum = "sabah-2026-10-12"
        olgulari_kur(db, cls.oturum, "2026-10-12", kopru=kopru, botlar=[bot], pencere=(BAS, BIT),
                     fiyat=lambda v, ts: sabit_fiyat(v, ts) or (Decimal("0.0203") if v == "TRY" else None))
        cls.olgular = {r["no"]: dict(r) for r in db.execute("SELECT * FROM olgu WHERE oturum=?", (cls.oturum,))}
        for o in cls.olgular.values():
            o["alanlar"] = json.loads(o["alanlar"])

    def test_turler_var(self):
        turler = {o["tur"] for o in self.olgular.values()}
        for t in ("cekim_ozet", "ag_payi", "kopru", "bot_uyusmazlik", "okunamayan_ag", "taninmadi", "takas"):
            self.assertIn(t, turler)

    def test_sayilar_turkce_metin(self):
        for no, o in self.olgular.items():
            for k, v in o["alanlar"].items():
                self.assertIsInstance(v, str, f"{no}.{k}")
                for s in sayilar(v):
                    if re.fullmatch(r"\d{1,2}", s) or re.fullmatch(r"20\d\d", s):
                        continue                            # gün, saat, dakika, yıl
                    self.assertRegex(s, TURKCE, f"{no}.{k}={v}")

    def test_adres_yok(self):
        for o in self.olgular.values():
            self.assertIsNone(GERCEK_ADRES.search(json.dumps(o["alanlar"], ensure_ascii=False)))

    def test_seviyeler_gizli(self):
        for o in self.olgular.values():
            if o["tur"] == "kopru" and o["alanlar"]["kalem"] in ("baslangic", "bitis"):
                self.assertEqual(o["gizli"], 1)
            if o["tur"] == "kalan_ozet":
                self.assertEqual(o["gizli"], 1)
            if not o["gizli"]:
                self.assertNotIn("bakiye", o["alanlar"])

    def test_uyarilar_olgulara_dayanir(self):
        uyarilar = self.db.execute("SELECT tur, onem, olgular FROM uyari WHERE oturum=?", (self.oturum,)).fetchall()
        self.assertIn(("bot_uyusmazlik", "acil"), [(u["tur"], u["onem"]) for u in uyarilar])
        self.assertIn("okunamayan_ag", [u["tur"] for u in uyarilar])
        for u in uyarilar:
            for no in json.loads(u["olgular"]):
                self.assertIn(no, self.olgular)

    def test_bot_olgusu(self):
        o = next(o for o in self.olgular.values() if o["tur"] == "bot_uyusmazlik")["alanlar"]
        self.assertEqual((o["kayit_sonuc"], o["gercek_sonuc"]), ("+99,89 TL", "-0,22 TL"))

    def test_kalip_cumle_denetimden_gecer(self):
        cumle, dayanak = kalip_cumle(self.db, self.oturum)
        self.assertTrue(cumle)
        metinler = " ".join(v for no in dayanak for v in self.olgular[no]["alanlar"].values())
        for s in sayilar(cumle):
            self.assertIn(s, metinler, cumle)
        for no in dayanak:
            self.assertEqual(self.olgular[no]["gizli"], 0, "kalıp cümle gizli olgu kullanmaz")

    def test_banka_cekimi_ozete_girmez(self):
        db = dbm.baglan(":memory:")
        cek = [Kayit("cekim", "w1", 1791721943000, "AVAX", "AVAX-Avalanche C-Chain", Decimal("1"), Decimal("0"), "AVAX", A, "0xc1", "2")]
        hyaz(db, cekim_hareketleri(cek))
        db.execute("UPDATE hareket SET karsi='BENIM_1'")
        from veri.defter import fonlama_hareketleri
        hyaz(db, fonlama_hareketleri([{"billId": "b", "ts": "1791721943000", "type": "2", "ccy": "TRY", "balChg": "-500"}]))
        olgulari_kur(db, "x", "2026-10-12", fiyat=lambda v, ts: Decimal(1))
        o = json.loads(db.execute("SELECT alanlar FROM olgu WHERE oturum='x' AND tur='cekim_ozet'").fetchone()[0])
        self.assertEqual((o["cekim_sayisi"], o["adres_sayisi"]), ("1", "1"))
        aglar = [json.loads(r[0])["ag"] for r in db.execute("SELECT alanlar FROM olgu WHERE oturum='x' AND tur='ag_payi'")]
        self.assertEqual(aglar, ["Avalanche"])

    def test_sayi_alan_reddedilir(self):
        y = OlguYazici(dbm.baglan(":memory:"), "x")
        with self.assertRaises(TypeError):
            y.ekle("deneme", {"miktar": Decimal("1.5")})


if __name__ == "__main__":
    unittest.main()
