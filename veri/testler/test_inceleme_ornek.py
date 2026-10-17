"""İnceleme bulgu 3–4: örnek veritabanı beyaz listeyle kurulur; bakiye/seviye ve kimlik taşımaz."""
import json
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from veri import db as dbm
from veri.kopru import kopru_kur
from veri.ornek import IZINLI_TABLOLAR, canlidan


def _kaynak() -> Path:
    yol = Path(tempfile.mkdtemp()) / "canli.db"
    db = dbm.baglan(yol)
    db.execute("INSERT INTO adres (adres, etiket, kisa, ag, katman, tahmin, kanit, cekim_sayisi, gezgin_url) VALUES "
               "('0x" + "ab" * 20 + "', 'BENIM_1', '0xabab…abab', 'chiliz', 3, 'benim', 'k', 1, 'https://x/0x" + "ab" * 20 + "')")
    db.execute("INSERT INTO hareket (zaman, kaynak, hesap, adres_id, ag, varlik, miktar, tur, islem_kimligi, kaynak_okuma, ham_kimlik) "
               "VALUES ('2026-10-16T10:00:00.000Z', 'zincir', 'cuzdan', 1, 'chiliz', 'CHZ', '5', 'giris', '0x" + "cd" * 32 + "', 'r', 'h1')")
    db.execute("INSERT INTO olgu VALUES ('sabah-2026-10-17', 'o1', 'bot_uyusmazlik', '{\"x\": \"1 TL\"}', 0, "
               "'[\"account_get_bills:alt:4014896115148492803\", \"grid:4014895767398817792\"]')")
    db.execute("INSERT INTO olgu VALUES ('sabah-2026-10-17', 'o2', 'kalan_ozet', '{\"dolar\": \"360 $\"}', 1, '[]')")
    db.execute("INSERT INTO olgu VALUES ('sabah-2026-10-17', 'o3', 'kopru', '{\"kalem\": \"fiyat\", \"coin\": \"1.018,7 USDC\", \"tutar\": \"0,2 $\"}', 0, '[]')")
    db.execute("INSERT INTO cagri (zaman, kaynak, ad, parametreler, sure_ms, sonuc) VALUES ('z', 'Telegram', 'sendMessage', '{\"chat_id\": \"123456\"}', 5, 'ok')")
    db.execute("INSERT INTO fotograf VALUES ('2026-10-17', 'z', 'borsa:ana', 'TRY', '90000', NULL, NULL)")
    db.execute("CREATE TABLE _kapanis (adres_id, ag, varlik, defter, zincir, fark, zaman)")
    db.execute("INSERT INTO _kapanis VALUES (1, 'chiliz', 'CHZ', '57.5', '45.8', '-11.7', 'z')")
    db.execute("CREATE TABLE _defter (kimlik, bal)")
    db.execute("INSERT INTO _defter VALUES ('b', '154.05')")
    db.execute("CREATE TABLE isaret (adres_etiket, ag, sahip, zaman)")                # Merve'nin
    db.execute("INSERT INTO isaret VALUES ('BENIM_1', 'chiliz', 'benim', 'z')")
    db.commit()
    db.close()
    return yol


class OrnekBeyazListe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hedef = Path(tempfile.mkdtemp()) / "ornek.db"
        canlidan(_kaynak(), cls.hedef, gecmis=False)
        cls.db = sqlite3.connect(cls.hedef)
        cls.db.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_yalniz_izinli_tablolar(self):
        tablolar = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertLessEqual(tablolar, set(IZINLI_TABLOLAR))
        self.assertNotIn("_kapanis", tablolar)
        self.assertNotIn("_defter", tablolar)
        self.assertNotIn("isaret", tablolar)

    def test_seviye_ve_kimlik_yok(self):
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fotograf").fetchone()[0], 0)
        for (kaynak,) in self.db.execute("SELECT kaynak FROM olgu"):
            self.assertEqual(kaynak, "[]")
        fiyat = [json.loads(r[0]) for r in self.db.execute("SELECT alanlar FROM olgu WHERE tur='kopru'")]
        self.assertTrue(all("coin" not in a for a in fiyat if a.get("kalem") == "fiyat"))
        self.assertEqual(json.loads(self.db.execute("SELECT alanlar FROM olgu WHERE no='o2'").fetchone()[0]), {"dolar": "gizli"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cagri WHERE parametreler LIKE '%chat_id%'").fetchone()[0], 0)
        r = self.db.execute("SELECT adres, kisa, gezgin_url FROM adres").fetchone()
        self.assertEqual((r["adres"], r["kisa"], r["gezgin_url"]), ("BENIM_1", "BENIM_1", None))
        self.assertTrue(self.db.execute("SELECT islem_kimligi FROM hareket").fetchone()[0].startswith("TX_"))


class FiyatKalemiSeviyesiz(unittest.TestCase):
    def test_fiyat_kalemi_coin_miktari_tasimaz(self):
        db = dbm.baglan(":memory:")
        fotolar = {"bas": {"borsa:alt": {"AVAX": Decimal(2)}}, "bit": {"borsa:alt": {"AVAX": Decimal(2)}}}
        k = kopru_kur(db, "g", 0, 1, lambda v, ts: Decimal(10) if ts == 0 else Decimal(12), fotolar=fotolar)
        fiyat = next(x for x in k["borsa"] if x.kalem == "fiyat")
        self.assertEqual((fiyat.dolar, fiyat.varlik), (Decimal(4), {}))


class TelegramKaydiSohbetKimligiTasimaz(unittest.TestCase):
    def test_chat_id_maskeli(self):
        from calistir.telegram import Telegram
        from veri.testler.test_b8_sabah import SahteHttp
        db = dbm.baglan(":memory:")
        Telegram("1:A", "987654321", db=db, http=SahteHttp()).gonder("x")
        self.assertNotIn("987654321", db.execute("SELECT parametreler FROM cagri").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
