"""Doğrulanmış kalıp cümleler: yalnız olgu alanlarını harfiyen kopyalar, hesap yapmaz.

Model zaman aşımına uğradığında, bütçe tavanında ya da sayı denetiminden geçmeyen cümlenin yerine kullanılır.
Gizli olgudan cümle kurulmaz.
"""
from __future__ import annotations

from anlatim.denetim import Olgu

ONCELIK = ("bot_uyusmazlik", "kopru_ozet", "taninmadi", "okunamayan_ag", "supheli", "kopru", "cekim_ozet", "moca_takas", "takas",
           "cekim", "gonderim", "moca_stake", "bot_tutuyor", "ag_payi")


def _takas(a: dict) -> str:
    metin = f"{a['tarih']}: {a['verilen']} verip {a['alinan']} aldın"
    if a.get("ag_ucreti"):
        metin += f"; ağ ücreti {a['ag_ucreti']}"
    metin += "."
    if a.get("dolar_fiyati_yok"):
        metin += f" {a['dolar_fiyati_yok']} için o güne ait dolar fiyatı yok."
    elif a.get("verilen_dolar") == "bilinmiyor":
        metin += " Verdiğin token için o güne ait dolar fiyatı yok."
    return metin


def _gonderim(a: dict) -> str:
    metin = f"{a['tarih']}: {a['miktar']} gönderdin"
    if a.get("ag_ucreti"):
        metin += f"; ağ ücreti {a['ag_ucreti']}"
    metin += "."
    if a.get("alici_benim") == "evet":
        metin += " Alıcı adres de senin."
    return metin


def _kopru(a: dict) -> str:
    ad = {"borsa": "borsadaki hesabın", "servet": "toplam servetin"}.get(a.get("kapsam"), a.get("kapsam", ""))
    metin = f"Dünden bugüne {ad} {a['degisim']} değişti."
    if a.get("neden"):
        metin += f" Neden: {a['neden']}."
    return metin


def _stake(a: dict) -> str:
    metin = f"{a['tarih']}: {a['miktar']} {a.get('islev', 'sözleşme')} işleviyle gönderildi"
    return metin + (" ve geri dönmedi." if a.get("geri_donmedi") == "evet" else ".")


KALIPLAR = {
    "cekim": lambda a: f"{a['tarih']}: {a['miktar']} çektin; çekim ücreti {a['ucret']}.",
    "takas": _takas,
    "moca_takas": _takas,
    "taninmadi": lambda a: f"{a['tarih']}: {a['miktar']} tutarında bir giriş geldi; kaynağını tanıyamadım.",
    "gonderim": _gonderim,
    "kopru": _kopru,
    "cekim_ozet": lambda a: (f"{a['donem']} arasında {a['borsa']} hesabından {a['adres_sayisi']} adrese "
                             f"{a['cekim_sayisi']} çekimle {a['toplam_dolar']} çektin."),
    "ag_payi": lambda a: f"{a['ag']} ağına {a['cekim_sayisi']} çekimle {a['dolar']} gitti.",
    "moca_stake": _stake,
    "bot_uyusmazlik": lambda a: (f"{a['bot']} botunun kaydı {a['kayit_sonuc']} diyor; "
                                 f"hesabına dönen paraya göre sonuç {a['gercek_sonuc']}."),
    "bot_tutuyor": lambda a: f"{a['bot']} botunun kaydı hesabına dönen parayla tutuyor: {a['gercek_sonuc']}.",
    "kopru_ozet": lambda a: f"{a['donem'].capitalize()}: {a['ad']} {a['miktar']} {a['yon']}.",
    "defter_farki": lambda a: (f"{a['ag']} ağında {a['adres']} adresinin bakiyesi defterle kapanmıyor; "
                               f"açıklanamayan fark {a['fark']}."),
    "okunamayan_ag": lambda a: f"{a['ag']} ağında yalnız çekimi görüyorum; bakiye ve sonraki hareketler okunamadı.",
}


def olgu_cumlesi(olgu: Olgu) -> str | None:
    if olgu.gizli or olgu.tur not in KALIPLAR:
        return None
    try:
        return KALIPLAR[olgu.tur](olgu.alanlar)
    except KeyError:
        return None


def ozet(olgular: list[Olgu], en_cok: int) -> tuple[str, list[str]]:
    """Öncelik sırasına göre en çok `en_cok` olgudan kalıp özet."""
    sirali = sorted((o for o in olgular if not o.gizli and o.tur in KALIPLAR),
                    key=lambda o: ONCELIK.index(o.tur) if o.tur in ONCELIK else len(ONCELIK))
    cumleler, dayanak = [], []
    for o in sirali:
        metin = olgu_cumlesi(o)
        if metin:
            cumleler.append(metin)
            dayanak.append(o.no)
        if len(cumleler) == en_cok:
            break
    return " ".join(cumleler), dayanak
