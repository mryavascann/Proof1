"""B8 kabul: sabah işinin son adımı. Cümle `cumle` tablosundan ya da kalıptan; anlatıcı 5 sn'de dönmezse kalıp;
gizli değer mesaja girmez; mesaj tek cümle + “Panoyu aç”."""
import json
import os
import sys
import unittest

from calistir.sabah import mesaj_hazirla
from calistir.telegram import Telegram
from veri import db as dbm
from veri.olgu import OlguYazici


class SahteHttp:
    def __init__(self, durum=200):
        self.istekler = []
        self.durum = durum

    def post(self, url, json=None, timeout=None):
        self.istekler.append((url, json))
        sahte = self

        class C:
            status_code = sahte.durum if len(sahte.istekler) == 1 else 200
            ok = status_code == 200

            def json(self_):
                return {"ok": self_.ok, "result": {"message_id": 7}} if self_.ok else {"ok": False, "description": "Bad Request"}
        return C()


def _db():
    db = dbm.baglan(":memory:")
    y = OlguYazici(db, "sabah-x")
    y.ekle("kopru_ozet", {"kapsam": "servet", "ad": "toplam servet", "degisim": "-0,19 $", "donem": "dün 09:00 → bugün 09:00"})
    y.ekle("kalan_ozet", {"adres_sayisi": "10", "dolar": "360 $"}, gizli=True)
    return db


SAHTE_ANLATICI = '''import sqlite3, sys
d = sqlite3.connect(sys.argv[1])
d.execute("CREATE TABLE IF NOT EXISTS cumle (id INTEGER PRIMARY KEY, oturum, olgular, metin, model, denetim, yer, zaman)")
d.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer) VALUES (?,?,?,?,?,?)",
          (sys.argv[2], '["o1"]', "Dünden bugüne servetin -0,19 $ değişti; ücretler yüzünden.", "claude-sonnet-5-5", "gecti", "telegram"))
d.commit()
'''


class Mesaj(unittest.TestCase):
    def test_anlatici_yoksa_kalip(self):
        db = _db()
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut="", pano_url="http://localhost:3003")
        self.assertEqual(m.kaynak, "kalip")
        self.assertIn("-0,19 $", m.metin)
        self.assertIn("http://localhost:3003/?oturum=sabah-x", m.baglanti)

    def test_anlatici_cumlesi_kullanilir(self):
        import tempfile
        dizin = tempfile.mkdtemp()
        yol = os.path.join(dizin, "t.db")
        betik = os.path.join(dizin, "anlatici.py")
        with open(betik, "w", encoding="utf-8") as f:
            f.write(SAHTE_ANLATICI)
        db = dbm.baglan(yol)
        OlguYazici(db, "sabah-x").ekle("kopru_ozet", {"kapsam": "servet", "degisim": "-0,19 $"})
        komut = f'"{sys.executable}" "{betik}" "{yol}" {{oturum}}'
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut=komut, pano_url="http://p")
        self.assertEqual(m.kaynak, "claude-sonnet-5-5")
        self.assertTrue(m.metin.startswith("Dünden bugüne"))

    def test_anlatici_gec_kalirsa_kalip(self):
        db = _db()
        yavas = f'"{sys.executable}" -c "import time; time.sleep(8)"'
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut=yavas, pano_url="http://p", zaman_asimi=1)
        self.assertEqual(m.kaynak, "kalip")

    def test_gizli_deger_sizarsa_kalip(self):
        db = _db()
        db.execute("CREATE TABLE IF NOT EXISTS cumle (id INTEGER PRIMARY KEY, oturum TEXT, olgular TEXT, metin TEXT, model TEXT, denetim TEXT, yer TEXT, zaman TEXT)")
        db.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer) VALUES ('sabah-x','[\"o2\"]','10 adreste 360 $ duruyor.','m','gecti','telegram')")
        m = mesaj_hazirla(db, "sabah-x", anlatici_komut="", pano_url="http://p")
        self.assertEqual(m.kaynak, "kalip")
        self.assertNotIn("360", m.metin)


class TelegramGonder(unittest.TestCase):
    def test_html_baglanti_reddedilirse_duz_metin(self):
        http = SahteHttp(durum=400)
        t = Telegram("123:ABC", "42", http=http)
        sonuc = t.gonder_pano("Merhaba.", "http://localhost:3003/?oturum=x")
        self.assertTrue(sonuc)
        self.assertEqual(len(http.istekler), 2)
        self.assertIn("parse_mode", http.istekler[0][1])
        self.assertNotIn("parse_mode", http.istekler[1][1])
        self.assertIn("Panoyu aç: http://localhost:3003/?oturum=x", http.istekler[1][1]["text"])

    def test_cagri_kaydinda_token_yok(self):
        db = dbm.baglan(":memory:")
        Telegram("123:GIZLITOKEN", "42", db=db, http=SahteHttp()).gonder("x")
        r = db.execute("SELECT ad, parametreler FROM cagri").fetchone()
        self.assertEqual(r["ad"], "sendMessage")
        self.assertNotIn("GIZLITOKEN", r["parametreler"])


if __name__ == "__main__":
    unittest.main()
