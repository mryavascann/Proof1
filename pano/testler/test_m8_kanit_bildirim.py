"""Kanıt paneli: 'salt okunur' OKX TR / ATK / OnchainOS / zincir çağrıları üzerinden hesaplanır.
Telegram mesajı proof1'ın kendi botuna bildirimdir; borsaya yazmaz. Ayrı satırda gösterilir (17 Ekim: panel
Telegram yüzünden 'salt okunur olmayan çağrı var' diyordu)."""
import sqlite3
import unittest

from pano import veri


def _db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE cagri (id INTEGER PRIMARY KEY, oturum TEXT, zaman TEXT, kaynak TEXT, ad TEXT, parametreler TEXT,"
               " sure_ms INTEGER, alanlar TEXT, satir INTEGER, sonuc TEXT, kod TEXT, salt_okunur INTEGER)")
    satirlar = [("s", "z", "ATK", "account_get_bills", "{}", 400, '["balChg"]', 8, "ok", None, 1),
                ("s", "z", "OKX TR", "GET /api/v5/asset/withdrawal-history", "{}", 600, '["amt"]', 87, "ok", None, 1),
                ("s", "z", "Telegram", "sendMessage", "{}", 450, '["message_id"]', 1, "ok", "200", 0)]
    db.executemany("INSERT INTO cagri (oturum, zaman, kaynak, ad, parametreler, sure_ms, alanlar, satir, sonuc, kod, salt_okunur)"
                   " VALUES (?,?,?,?,?,?,?,?,?,?,?)", satirlar)
    return db


class KanitBildirim(unittest.TestCase):
    def test_telegram_salt_okunur_hesabini_bozmaz(self):
        k = veri._kanit(_db(), "s")
        self.assertTrue(k["salt_okunur_hepsi"])
        self.assertNotIn("Telegram", {g["kaynak"] for g in k["gruplar"]})
        self.assertEqual(k["bildirim"]["cagri"], 1)
        self.assertEqual(k["toplam"], 2)

    def test_gercek_yazma_hala_yakalanir(self):
        db = _db()
        db.execute("INSERT INTO cagri (oturum, zaman, kaynak, ad, parametreler, sure_ms, alanlar, satir, sonuc, kod, salt_okunur)"
                   " VALUES ('s','z','ATK','x','{}',1,'[]',0,'ok',NULL,0)")
        self.assertFalse(veri._kanit(db, "s")["salt_okunur_hepsi"])


if __name__ == "__main__":
    unittest.main()
