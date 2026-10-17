"""Canlı bot izleyicisi (sahnenin canlı anı). Botu insan durdurur; proof1 yalnız izler ve yakalar.

Etkin botlar 3 saniyede bir okunur. Bir bot listeden düşünce: geçmişteki kaydı + hesaba dönen satırlar (en çok
10 sn beklenir) → karşılaştırma → olgu + acil uyarı → Telegram. Hedef: durdurmadan mesaja 15 saniyenin altı.

Çalıştır:  python -m calistir.izle              (bütün etkin botlar)
           python -m calistir.izle --algo <id>  (yalnız demo botu)
"""
import argparse
import time
from datetime import datetime, timezone

from veri.bot import karsilastir
from veri.defter import _h, ayristir
from veri.kayit import iso

DONUS_BEKLE_SN = 10


def donus_hareketleri(ham: list[dict], bot: dict) -> list[dict]:
    """Botun kurulduğu ve durduğu anlardaki strateji aktarımları: hesaptan çıkan (giriş) ve hesaba dönen."""
    olus, durus = int(bot["cTime"]), int(bot.get("uTime") or 0)
    sonuc = []
    for s in ayristir(ham, "alt", "account_get_bills"):
        if s.tip != "12":
            continue
        if s.chg > 0 and durus and -2_000 <= s.ts - durus <= 15_000:
            sonuc.append(_h(s, "bottan_donus", s.chg))
        elif s.chg < 0 and abs(s.ts - olus) <= 5_000:
            sonuc.append(_h(s, "bota_giris", s.chg))
    return sonuc


class Izleyici:
    def __init__(self, atk, db, telegram, pano_url: str, aralik: float = 3, algo: str | None = None,
                 anlatici_komut: str = "", uyku=time.sleep, saat=time.monotonic, yaz=lambda *_: None):
        self.atk, self.db, self.tg = atk, db, telegram
        self.pano_url = pano_url
        self.aralik = aralik
        self.algo = algo
        self.anlatici_komut = anlatici_komut
        self.uyku, self.saat, self.yaz = uyku, saat, yaz

    def etkinler(self) -> dict:
        from veri.atk import satirlar
        try:
            return {str(b["algoId"]): b for b in satirlar(self.atk.cagir("grid_get_orders", {"algoOrdType": "grid", "status": "active"}))}
        except Exception as e:                       # 504 vb.: bu turu atla, izlemeyi bırakma
            self.yaz(f"etkin bot listesi okunamadı ({type(e).__name__}); sonraki turda yeniden")
            return None

    def _gecmis(self, algo: str) -> dict | None:
        from veri.atk import satirlar
        for _ in range(3):
            for b in satirlar(self.atk.cagir("grid_get_orders", {"algoOrdType": "grid", "status": "history", "algoId": algo})):
                if str(b.get("algoId")) == algo:
                    return b
            self.uyku(1)
        return None

    def yakala(self, etkin: dict):
        from veri.atk import satirlar
        from veri.fiyat import Fiyatci
        from veri.olgu import OlguYazici, bot_olgusu, temizle
        from calistir.sabah import mesaj_hazirla
        algo = str(etkin["algoId"])
        bot = self._gecmis(algo) or etkin
        bas = self.saat()
        hareketler = []
        while True:
            ham = satirlar(self.atk.cagir("account_get_bills", {"begin": str(int(bot["cTime"]) - 10_000), "limit": 100}))
            hareketler = donus_hareketleri(ham, bot)
            if any(h["tur"] == "bottan_donus" for h in hareketler) or self.saat() - bas >= DONUS_BEKLE_SN:
                break
            self.uyku(2)
        b = karsilastir(bot, hareketler, Fiyatci(self.atk, self.db).aralik, esle=False)
        oturum = f"canli-{algo}"
        temizle(self.db, oturum)
        bot_olgusu(OlguYazici(self.db, oturum), b)
        m = mesaj_hazirla(self.db, oturum, self.anlatici_komut, self.pano_url)
        if self.tg is not None and self.tg.hazir and self.tg.gonder_pano(m.metin, m.baglanti):
            self.db.execute("UPDATE uyari SET gonderildi=? WHERE oturum=?", (iso(datetime.now(timezone.utc)), oturum))
            self.db.commit()
        self.yaz(f"[{b.inst} {algo}] {b.durum}: {m.metin}")
        return b

    def calis(self, en_cok_tur: int | None = None) -> list:
        onceki = self.etkinler() or {}
        self.yaz(f"izleniyor: {len(onceki)} etkin bot" + (f" (yalnız {self.algo})" if self.algo else ""))
        sonuclar, tur = [], 0
        while en_cok_tur is None or tur < en_cok_tur:
            tur += 1
            self.uyku(self.aralik)
            simdi = self.etkinler()
            if simdi is None:
                continue
            for algo, bot in onceki.items():
                if algo in simdi or (self.algo and algo != self.algo):
                    continue
                t0 = self.saat()
                b = self.yakala(bot)
                sonuclar.append((b, self.saat() - t0 + self.aralik))     # en kötü durum: bir tur önce durdurulmuş
            for algo, bot in simdi.items():
                if algo not in onceki:
                    self.yaz(f"yeni bot: {bot.get('instId')} {algo}")
            onceki = simdi
            if self.algo and sonuclar:
                break
        return sonuclar


def main():
    from veri import ayar, db as dbm
    from veri.atk import Atk
    from calistir.telegram import Telegram
    p = argparse.ArgumentParser(description="proof1 canlı bot izleyicisi (salt okuma)")
    p.add_argument("--algo")
    p.add_argument("--aralik", type=float, default=3)
    a = p.parse_args()
    ayar.env_yukle()
    db = dbm.baglan()
    oturum = f"canli-izle-{datetime.now():%H%M%S}"
    with Atk(ayar.okx_kimlik("alt"), db, oturum) as atk:
        tg = Telegram(db=db, oturum=oturum)
        if not tg.hazir:
            print("Uyarı: Telegram eksik (" + ", ".join(ayar.eksikler(["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])) + "); yalnız ekrana yazılacak.")
        iz = Izleyici(atk, db, tg, ayar.al("PANO_URL", "http://localhost:3003"), a.aralik, a.algo, ayar.al("ANLATICI_KOMUT"),
                      yaz=lambda s: print(f"{datetime.now():%H:%M:%S} {s}", flush=True))
        for b, sure in iz.calis():
            print(f"yakalandı: {b.algo_id} · {sure:.1f} sn")


if __name__ == "__main__":
    main()
