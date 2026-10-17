"""Olgular: anlatıcının tek girdisi. Sayıları burada kod hesaplar ve Türkçe biçimde metne çevirir; model hesaplamaz."""
import json
from decimal import Decimal

from veri import bicim
from veri.kayit import simdi


class OlguYazici:
    def __init__(self, db, oturum: str):
        self.db = db
        self.oturum = oturum
        r = db.execute("SELECT no FROM olgu WHERE oturum=?", (oturum,)).fetchall()
        self.n = max((int(x[0][1:]) for x in r), default=0)

    def ekle(self, tur: str, alanlar: dict, gizli: bool = False, kaynak: list | None = None) -> str:
        for k, v in alanlar.items():
            if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool):
                raise TypeError(f"olgu alanı metin olmalı: {k}")   # sayı her zaman biçimli metin
        self.n += 1
        no = f"o{self.n}"
        self.db.execute("INSERT INTO olgu (oturum, no, tur, alanlar, gizli, kaynak) VALUES (?,?,?,?,?,?)",
                        (self.oturum, no, tur, json.dumps(alanlar, ensure_ascii=False), int(gizli),
                         json.dumps(kaynak or [], ensure_ascii=False)))
        self.db.commit()
        return no

    def uyari(self, tur: str, onem: str, olgular: list[str]) -> int:
        c = self.db.execute("INSERT INTO uyari (oturum, zaman, tur, onem, olgular) VALUES (?,?,?,?,?)",
                            (self.oturum, simdi(), tur, onem, json.dumps(olgular)))
        self.db.commit()
        return c.lastrowid


def temizle(db, oturum: str):
    db.execute("DELETE FROM olgu WHERE oturum=?", (oturum,))
    db.execute("DELETE FROM uyari WHERE oturum=?", (oturum,))
    db.commit()


# --- olgu kurucuları ---

def bot_olgusu(y: OlguYazici, b, ad: str | None = None) -> str:
    """b: veri.bot.BotSonucu. Uyuşmazlıkta acil uyarı da yazar."""
    kote = b.kote
    para = (lambda x, **k: bicim.tl(x, **k)) if kote == "TRY" else (lambda x, **k: bicim.miktar(x, kote))
    donen_coin = {c: m for c, m in b.donen.items() if c != kote}
    alanlar = {
        "bot": ad or f"{b.taban}/{kote} spot grid",
        "kurulus": bicim.tarih(b.olus_ms),
        "durdurma": bicim.tarih(b.durus_ms) if b.durus_ms else "çalışıyor",
        "durdurma_tipi": {"1": "satarak durdur", "2": "coinleri tut"}.get(b.stop_type, "bilinmiyor"),
        "yatirim": para(b.yatirim),
        "kayit_sonuc": para(b.kayit_pnl, isaretli=True) if kote == "TRY" else para(b.kayit_pnl),
        "donen_kote": para(b.donen.get(kote, Decimal(0))),
        "donen_coin": ", ".join(bicim.miktar(m, c) for c, m in donen_coin.items()) or "yok",
    }
    if b.gercek is not None:
        alanlar["gercek_sonuc"] = para(b.gercek, isaretli=True) if kote == "TRY" else para(b.gercek)
        alanlar["fark"] = para(abs(b.fark))
    if b.durum == "uyusmazlik":
        if b.iki_kez:
            alanlar["neden"] = f"elde kalan {b.taban} iki kez sayılmış gibi"
            alanlar["kalan_coin_degeri"] = para(b.kalan_coin_degeri)
        no = y.ekle("bot_uyusmazlik", alanlar, kaynak=[h for h in b.hareket_kimlikleri if h] + [f"grid:{b.algo_id}"])
        y.uyari("bot_uyusmazlik", "acil", [no])
        return no
    tur = "bot_tutuyor" if b.durum == "tutuyor" else ("bot_fiyat_yok" if b.durum == "fiyat_yok" else "bot_bekleniyor")
    return y.ekle(tur, alanlar, kaynak=[f"grid:{b.algo_id}"])
