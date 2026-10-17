"""Türkçe sayı ve tarih biçimi. Olgulardaki her sayı buradan geçer; anlatıcının denetimi bu metinle karşılaştırır.

Kural: |x| ≥ 1000 → tam sayı, binlik nokta (1.587) · 1 ≤ |x| < 1000 → en çok 2 ondalık (46,15)
· |x| < 1 → 4 anlamlı basamak (0,9828 · 0,000212). Sondaki sıfırlar atılır.
"""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

IST = timezone(timedelta(hours=3))
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def _yuvarla(d: Decimal) -> Decimal:
    m = abs(d)
    if m == 0:
        return Decimal(0)
    if m >= 1000:
        return d.quantize(Decimal(1), ROUND_HALF_UP)
    if m >= 1:
        return d.quantize(Decimal("0.01"), ROUND_HALF_UP)
    us = m.adjusted()                     # 0,000212 → -4
    return d.quantize(Decimal(1).scaleb(us - 3), ROUND_HALF_UP)


def _metin(d: Decimal, binlik: bool = True) -> str:
    isaret = "-" if d < 0 else ""
    d = abs(d)
    s = format(d, "f")
    tam, _, ond = s.partition(".")
    ond = ond.rstrip("0")
    if binlik and len(tam) > 3:
        gruplar = []
        while len(tam) > 3:
            gruplar.insert(0, tam[-3:])
            tam = tam[:-3]
        tam = ".".join([tam] + gruplar)
    return isaret + tam + ("," + ond if ond else "")


def sayi(x) -> str:
    return _metin(_yuvarla(Decimal(str(x))))


def miktar(x, varlik: str) -> str:
    return f"{sayi(x)} {varlik}"


def dolar(x) -> str:
    d = Decimal(str(x))
    d = d.quantize(Decimal(1), ROUND_HALF_UP) if abs(d) >= 1000 else d.quantize(Decimal("0.01"), ROUND_HALF_UP)
    return f"{_metin(d)} $"


def tl(x, isaretli: bool = False) -> str:
    d = Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    s = _metin(d)
    if "," not in s:
        s += ",00"
    elif len(s.split(",")[1]) == 1:
        s += "0"
    if isaretli and d > 0:
        s = "+" + s
    return f"{s} TL"


def yuzde(x) -> str:
    d = Decimal(str(x)).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return "%" + _metin(d)


def tarih(ms_ya_da_iso, saat: bool = True) -> str:
    if isinstance(ms_ya_da_iso, str):
        an = datetime.fromisoformat(ms_ya_da_iso.replace("Z", "+00:00"))
    else:
        an = datetime.fromtimestamp(int(ms_ya_da_iso) / 1000, tz=timezone.utc)
    an = an.astimezone(IST)
    t = f"{an.day} {AYLAR[an.month - 1]} {an.year}"
    return f"{t} {an:%H:%M}" if saat else t


def gun(ms_ya_da_iso) -> str:
    if isinstance(ms_ya_da_iso, str):
        an = datetime.fromisoformat(ms_ya_da_iso.replace("Z", "+00:00"))
    else:
        an = datetime.fromtimestamp(int(ms_ya_da_iso) / 1000, tz=timezone.utc)
    return an.astimezone(IST).strftime("%Y-%m-%d")
