"""Bot karşılaştırıcı: borsanın kaydı (`totalPnl`) ile hesaba dönen paradan hesaplanan gerçek sonuç.

Elde kalan coin, durdurma dakikasının en düşük ve en yüksek fiyatıyla değerlenir (aralık). Kayıt aralığın
içindeyse bot “tutuyor”; değilse gerçek sonuç kayda en yakın sınırdır (kayıt en iyimser fiyatla bile açıklanamıyor).
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from veri.atk import Atk, satirlar

GIRIS_PAYI_MS = 5_000          # bot kurulumu ile bota_giris satırı arası
DONUS_PAYI_MS = 15_000         # durdurma ile bottan_donus satırları arası
ESIK_TL = Decimal(1)


@dataclass
class BotSonucu:
    algo_id: str
    inst: str
    olus_ms: int
    durus_ms: int | None
    yatirim: Decimal
    kayit_pnl: Decimal
    stop_type: str
    giren: dict = field(default_factory=dict)
    donen: dict = field(default_factory=dict)
    fiyatlar: dict = field(default_factory=dict)       # ccy → (alt, üst)
    gercek: Decimal | None = None
    gercek_aralik: tuple | None = None
    fark: Decimal | None = None
    kalan_coin_degeri: Decimal | None = None
    iki_kez: bool = False
    durum: str = "bekleniyor"   # bekleniyor | fiyat_yok | tutuyor | uyusmazlik
    hareket_kimlikleri: list = field(default_factory=list)

    @property
    def kote(self) -> str:
        return self.inst.split("-")[1]

    @property
    def taban(self) -> str:
        return self.inst.split("-")[0]


def _ms(zaman: str) -> int:
    return int(datetime.fromisoformat(zaman.replace("Z", "+00:00")).timestamp() * 1000)


def _dec(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(0)


def _aralik(p):
    if p is None:
        return None
    return p if isinstance(p, tuple) else (p, p)


def durdu_mu(bot: dict) -> bool:
    return bot.get("state") in ("stopped", "stopping") or bool(bot.get("stopType"))


def karsilastir(bot: dict, hareketler: list[dict], fiyat, esle: bool = True) -> BotSonucu:
    """fiyat(cift, ts_ms) → Decimal | (alt, üst) | None. esle=False: hareketler zaten bu bota atanmış."""
    olus = int(bot["cTime"])
    durus = int(bot["uTime"]) if durdu_mu(bot) else None
    b = BotSonucu(str(bot["algoId"]), bot["instId"], olus, durus, _dec(bot.get("investment")),
                  _dec(bot.get("totalPnl")), str(bot.get("stopType") or ""))
    for h in hareketler:
        t = _ms(h["zaman"])
        m = Decimal(h["miktar"])
        if h["tur"] == "bota_giris" and (not esle or abs(t - olus) <= GIRIS_PAYI_MS):
            b.giren[h["varlik"]] = b.giren.get(h["varlik"], Decimal(0)) - m
            b.hareket_kimlikleri.append(h.get("ham_kimlik"))
        elif h["tur"] == "bottan_donus" and durus and (not esle or -2_000 <= t - durus <= DONUS_PAYI_MS):
            b.donen[h["varlik"]] = b.donen.get(h["varlik"], Decimal(0)) + m
            b.hareket_kimlikleri.append(h.get("ham_kimlik"))
    if not durus or not b.donen:
        return b
    kote = b.kote
    alt = ust = Decimal(0)
    for yon, sozluk in ((1, b.donen), (-1, b.giren or {kote: b.yatirim})):
        for ccy, miktar in sozluk.items():
            if ccy == kote:
                alt += yon * miktar
                ust += yon * miktar
                continue
            p = _aralik(fiyat(f"{ccy}-{kote}", durus))
            if p is None:
                b.durum = "fiyat_yok"
                return b
            b.fiyatlar[ccy] = p
            d1, d2 = yon * miktar * p[0], yon * miktar * p[1]
            alt += min(d1, d2)
            ust += max(d1, d2)
    b.gercek_aralik = (alt, ust)
    b.gercek = min(max(b.kayit_pnl, alt), ust)        # kayda en yakın değer
    b.fark = b.kayit_pnl - b.gercek
    b.kalan_coin_degeri = sum((m * b.fiyatlar[c][1] for c, m in b.donen.items() if c != kote), Decimal(0))
    if abs(b.fark) > ESIK_TL:
        b.durum = "uyusmazlik"
        alt_deger = sum((m * b.fiyatlar[c][0] for c, m in b.donen.items() if c != kote), Decimal(0))
        pay = max(Decimal("0.5"), b.kalan_coin_degeri * Decimal("0.01"))
        b.iki_kez = b.kalan_coin_degeri > 0 and (alt_deger - pay) <= b.fark <= (b.kalan_coin_degeri + pay)
    else:
        b.durum = "tutuyor"
    return b


def bot_listesi(atk: Atk, durum: str = "history") -> list[dict]:
    return satirlar(atk.cagir("grid_get_orders", {"algoOrdType": "grid", "status": durum},
                              alanlar=["algoId", "instId", "cTime", "uTime", "investment", "totalPnl", "stopType", "state"]))


def ata(botlar: list[dict], hareketler: list[dict]) -> dict[str, list[dict]]:
    """Her bot aktarımını zamanca en yakın bota atar (yakın zamanda kurulan botlar karışmasın)."""
    atanan = {str(b["algoId"]): [] for b in botlar}
    for h in hareketler:
        if h["tur"] not in ("bota_giris", "bottan_donus"):
            continue
        t = _ms(h["zaman"])
        en_iyi, en_az = None, None
        for b in botlar:
            if h["tur"] == "bota_giris":
                fark = abs(t - int(b["cTime"]))
                uygun = fark <= GIRIS_PAYI_MS
            else:
                if not durdu_mu(b):
                    continue
                fark = t - int(b["uTime"])
                uygun = -2_000 <= fark <= DONUS_PAYI_MS
                fark = abs(fark)
            if uygun and (en_az is None or fark < en_az):
                en_iyi, en_az = str(b["algoId"]), fark
        if en_iyi:
            atanan[en_iyi].append(h)
    return atanan


def botlari_karsilastir(atk: Atk, db=None, botlar: list[dict] | None = None, hareketler: list[dict] | None = None):
    """Durmuş botların hepsi. Hareketler verilmezse alt hesabın 3 aylık defterinden okunur."""
    from veri.defter import alt_defteri, hareketlere, zincirle
    from veri.fiyat import Fiyatci
    botlar = botlar if botlar is not None else bot_listesi(atk)
    if hareketler is None:
        s = alt_defteri(atk)
        zincirle(s)
        hareketler = hareketlere(s)
    atanan = ata(botlar, hareketler)
    fiyatci = Fiyatci(atk, db)
    return [karsilastir(b, atanan[str(b["algoId"])], fiyatci.aralik, esle=False) for b in botlar]
