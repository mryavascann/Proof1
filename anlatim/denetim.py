"""Sayı ve olgu denetimi.

Bir cevap ancak şu koşullarla geçer:
- Atıf yaptığı olgular boş değil, hepsi o görevin yetkili olgularından ve hiçbiri gizli değil.
- Metindeki her sayı, atıf yapılan olgulardan birinde aynı değer, aynı birim/varlık ve aynı işaretle geçiyor.
  İşaretsiz sayı yalnız negatif olmayan bir olguya eşleşir; −0,22 ile +0,22 eşdeğer değildir.
- "verip / aldın" gibi rol fiilleri doğru alana (verilen / alinan) bağlanıyor.
- Tarih ve saatler bütün olarak eşleşiyor; saat, aynı alandaki tarihle birlikte doğrulanır.
- Metinde gizli bir olgunun değeri hiçbir biçimde geçmiyor.
Olgu kimlikleri (o3 gibi) sayı taramasından önce ayıklanır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7,
         "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}

_OLGU_NO = re.compile(r"\(?\bo\d+\b\)?")
_TARIH_SAYISAL = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\d.])")
_TARIH_YAZI = re.compile(r"(?<!\d)(\d{1,2})\s+(" + "|".join(AYLAR) + r")(?:['’][^\W\d_]+)?(?:\s+(\d{4}))?(?!\d)",
                         re.IGNORECASE)
_SAAT = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?!\d|:\d)")
_SAYI = re.compile(r"(?<![\w.,])([+\-−]?)(%?)(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?![\d])")
_BIRIM = re.compile(r"\s?(\$|%|[A-ZÇĞİÖŞÜ][A-Z0-9ÇĞİÖŞÜ]{1,11})(?![a-zçğıöşü0-9])")
_ROL = re.compile(r"\s*(?:['’][^\W\d_]+)?\s*(ver(?:ip|din|di|ilen|erek)|al(?:dın|dı|ındı|ınan|arak))", re.IGNORECASE)


@dataclass
class Olgu:
    no: str
    tur: str
    alanlar: dict
    gizli: bool = False


@dataclass
class Sayi:
    deger: Decimal
    birim: str | None
    isaretli: bool
    rol: str | None = None


@dataclass
class Sonuc:
    gecti: bool
    neden: str = ""


@dataclass
class _Parcalar:
    sayilar: list = field(default_factory=list)
    tarihler: list = field(default_factory=list)   # (gün, ay, yıl|None, konum)
    saatler: list = field(default_factory=list)    # (saat, dakika, konum)


def _turk_sayi(metin: str) -> Decimal:
    return Decimal(metin.replace(".", "").replace(",", "."))


def _ayristir(metin: str) -> _Parcalar:
    p = _Parcalar()
    temiz = _OLGU_NO.sub(lambda m: " " * len(m.group(0)), metin)

    def sil(m):
        nonlocal temiz
        temiz = temiz[:m.start()] + " " * (m.end() - m.start()) + temiz[m.end():]

    for m in list(_TARIH_SAYISAL.finditer(temiz)):
        p.tarihler.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.start()))
        sil(m)
    for m in list(_TARIH_YAZI.finditer(temiz)):
        yil = int(m.group(3)) if m.group(3) else None
        p.tarihler.append((int(m.group(1)), AYLAR[m.group(2).lower().replace("i̇", "i")], yil, m.start()))
        sil(m)
    for m in list(_SAAT.finditer(temiz)):
        p.saatler.append((int(m.group(1)), int(m.group(2)), m.start()))
        sil(m)

    for m in _SAYI.finditer(temiz):
        isaret, yuzde, govde = m.groups()
        deger = _turk_sayi(govde)
        if isaret in ("-", "−"):
            deger = -deger
        birim = "%" if yuzde else None
        son = m.end()
        if not birim:
            b = _BIRIM.match(temiz, son)
            if b:
                birim = b.group(1)
                son = b.end()
        r = _ROL.match(temiz, son)
        rol = None
        if r:
            rol = "verilen" if r.group(1).lower().startswith("ver") else "alinan"
        p.sayilar.append(Sayi(deger, birim, bool(isaret), rol))
    return p


def sayilari_ayikla(metin: str) -> list[Sayi]:
    return _ayristir(metin).sayilar


def _olgu_degerleri(olgu: Olgu):
    """Olgunun alanlarından (alan, Sayi) ve (alan, tarihler, saatler) listeleri."""
    sayilar, zamanlar = [], []
    for alan, deger in olgu.alanlar.items():
        if not isinstance(deger, str):
            deger = str(deger)
        p = _ayristir(deger)
        sayilar += [(alan, s) for s in p.sayilar]
        if p.tarihler or p.saatler:
            zamanlar.append((alan, [t[:3] for t in p.tarihler], [s[:2] for s in p.saatler]))
    return sayilar, zamanlar


def _sayi_eslesir(s: Sayi, alan: str, v: Sayi) -> bool:
    if s.birim != v.birim or s.deger != v.deger:
        return False
    if not s.isaretli and v.deger < 0:
        return False
    if s.rol and s.rol not in alan:
        return False
    return True


def _tarih_eslesir(t, olgu_tarihleri) -> bool:
    g, a, y = t
    return any(g == og and a == oa and (y is None or oy is None or y == oy) for og, oa, oy in olgu_tarihleri)


def denetle(cevap: dict, gorev_olgulari: list[Olgu]) -> Sonuc:
    metin = (cevap.get("metin") or "").strip()
    if not metin:
        return Sonuc(False, "boş metin")
    atif = list(cevap.get("olgular") or [])
    if not atif:
        return Sonuc(False, "olgu atfı yok")
    yetkili = {o.no: o for o in gorev_olgulari}
    for no in atif:
        if no not in yetkili:
            return Sonuc(False, f"{no} bu görevin olgusu değil")
        if yetkili[no].gizli:
            return Sonuc(False, f"{no} gizli")

    p = _ayristir(metin)

    # Gizli olgu değeri hiçbir biçimde geçmemeli (atıf olmasa da).
    for o in gorev_olgulari:
        if o.gizli:
            for _, v in _olgu_degerleri(o)[0]:
                if any(s.deger == v.deger or s.deger == -v.deger for s in p.sayilar):
                    return Sonuc(False, f"gizli değer metinde ({o.no})")

    atif_olgular = [yetkili[no] for no in atif]
    degerler, zamanlar = [], []
    for o in atif_olgular:
        d, z = _olgu_degerleri(o)
        degerler += d
        zamanlar += z

    for s in p.sayilar:
        if not any(_sayi_eslesir(s, alan, v) for alan, v in degerler):
            birim = f" {s.birim}" if s.birim else ""
            return Sonuc(False, f"olgularda yok: {s.deger}{birim}" + (f" ({s.rol})" if s.rol else ""))

    tum_tarihler = [t for _, ts, _ in zamanlar for t in ts]
    for g, a, y, _ in p.tarihler:
        if not _tarih_eslesir((g, a, y), tum_tarihler):
            return Sonuc(False, f"tarih olgularda yok: {g}.{a}.{y or ''}")

    for sa, dk, konum in p.saatler:
        onceki = [t for t in p.tarihler if t[3] < konum]
        tarih = max(onceki, key=lambda t: t[3])[:3] if onceki else None
        uygun = False
        for _, ts, ss in zamanlar:
            if (sa, dk) in ss and (tarih is None or _tarih_eslesir(tarih, ts)):
                uygun = True
                break
        if not uygun:
            return Sonuc(False, f"saat olgularda yok: {sa:02d}:{dk:02d}")

    return Sonuc(True)
