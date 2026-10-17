"""Panonun rapor verisi. Buğra'nın tablolarını salt okur, muhasebe yapmaz; yalnız görsel gruplar kurar.

Gizli mod (öntanımlı açık): bakiye seviyeleri, bunlardan türeyen yüzdeler ve güncel dağılım rapora hiç girmez.
Hareket, aktarım ve ücret tutarları açıktır. Tam adres yalnız `gezgin_url` hedefinde bulunabilir.
Pano yeni toplam üretmez: "Diğer" grubunun etiketinde tutar yoktur; geometri değeri yalnız çizim içindir.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from anlatim import kalip
from anlatim.anlat import olgulari_oku
from anlatim.denetim import sayilari_ayikla

AKIS_EN_COK_GRUP = 5
KATMANLAR = {1: "Çekim görüldü", 2: "Bakiye okundu", 3: "Sonraki hareketler izlendi"}
KOPRU_OZET = [
    ("Dış hareket", ("disari", "iceri")),
    ("Bot sonucu", ("bot",)),
    ("Fiyat ve takas", ("fiyat", "takas")),
    ("Ücretler", ("ucret",)),
    ("Açıklanamayan", ("aciklanamayan",)),
]
KALEM_ADI = {"disari": "Dışarı giden", "iceri": "Dışarıdan gelen", "bot": "Bot sonucu", "fiyat": "Fiyat etkisi",
             "takas": "Takas farkı", "ucret": "Ücret", "aciklanamayan": "Açıklanamayan",
             "izlenemeyen": "İzlenemeyen (okunamayan kapsam)", "aktarim": "Kendi hesapların arası (servet değişmez)",
             "baslangic": "Dün 09.00", "bitis": "Bugün 09.00"}
SEVIYE_KALEMLERI = {"baslangic", "bitis"}
ONEM_SIRASI = {"acil": 0, "orta": 1, "bilgi": 2}
AYLAR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
         "Aralık"]


class IsaretHatasi(ValueError):
    pass


def _tablo_var(db, ad: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (ad,)).fetchone() is not None


def tr_sayi(d: Decimal) -> str:
    """Decimal → Türkçe biçim, hassasiyet korunur: −0,017189 · 1.587 · 20.889,5"""
    eksi = d < 0
    metin = format(abs(d).normalize(), "f")
    tam, _, kesir = metin.partition(".")
    tam = f"{int(tam):,}".replace(",", ".")
    return ("−" if eksi else "") + tam + ("," + kesir if kesir else "")


def _gun_tr(gun: str) -> str:
    y, a, g = (int(x) for x in gun.split("-"))
    return f"{g} {AYLAR[a]} {y}"


def _deger(metin: str | None) -> float:
    sayilar = sayilari_ayikla(metin or "")
    return float(sayilar[0].deger) if sayilar else 0.0


def _cumleler(db, oturum: str) -> list[dict]:
    if not _tablo_var(db, "cumle"):
        return []
    return [{"yer": yer, "metin": metin, "model": model, "denetim": denetim, "olgular": json.loads(olg or "[]")}
            for yer, metin, model, denetim, olg in db.execute(
                "SELECT yer, metin, model, denetim, olgular FROM cumle WHERE oturum=? ORDER BY id", (oturum,))]


def _isaretler(db) -> dict:
    if not _tablo_var(db, "isaret"):
        return {}
    son = {}
    for etiket, ag, sahip, zaman in db.execute("SELECT adres_etiket, ag, sahip, zaman FROM isaret ORDER BY zaman, rowid"):
        son[(etiket, ag)] = sahip
    return son


def _kapsam(adresler: list[dict], ag: str) -> dict:
    burada = [a for a in adresler if a["ag"] == ag.lower()]
    katman = max((a["katman"] or 1 for a in burada), default=0)
    return {
        "adres": len(burada),
        "benim_tahmini": sum(1 for a in burada if a["tahmin"] == "benim"),
        "katmanlar": [KATMANLAR[k] for k in sorted(KATMANLAR) if k <= katman],
        "eksik": [KATMANLAR[k] for k in sorted(KATMANLAR) if k > katman] if burada else [],
        "yalniz_cekim": katman == 1,
    }


def _bant_cumleleri(cumleler, olgular, ag: str, etiketler: set[str], donem: str | None) -> list[dict]:
    olgu = {o.no: o for o in olgular}
    secilen = []
    for c in cumleler:
        if not c["yer"].startswith("bant:"):
            continue
        bant = c["yer"][5:]
        if bant != ag and bant not in etiketler:
            continue
        tarih = next((olgu[n].alanlar.get("tarih") for n in c["olgular"] if n in olgu and olgu[n].alanlar.get("tarih")),
                     None)
        not_ = f"Bu hareket {tarih} tarihli; akışın dönemi {donem}." if tarih and donem else None
        secilen.append({**{k: c[k] for k in ("metin", "model", "denetim", "olgular")}, "donem_notu": not_})
    return secilen


def _akis(db, olgular, cumleler, adresler) -> dict:
    ozet = next((o for o in olgular if o.tur == "cekim_ozet" and not o.gizli), None)
    a = ozet.alanlar if ozet else {}
    donem = a.get("donem")
    paylar = sorted((o for o in olgular if o.tur == "ag_payi" and not o.gizli),
                    key=lambda o: _deger(o.alanlar.get("dolar")), reverse=True)

    def grup(o):
        ad = o.alanlar["ag"]
        etiketler = {x["etiket"] for x in adresler if x["ag"] == ad.lower()}
        return {"id": ad.lower(), "ad": ad, "tutar": o.alanlar.get("dolar"), "deger": _deger(o.alanlar.get("dolar")),
                "cekim_sayisi": o.alanlar.get("cekim_sayisi"), "olgular": [o.no], "kapsam": _kapsam(adresler, ad),
                "cumleler": _bant_cumleleri(cumleler, olgular, ad, etiketler, donem)}

    gruplar = [grup(o) for o in paylar]
    if len(gruplar) > AKIS_EN_COK_GRUP:
        bas, kalan_gruplar = gruplar[:AKIS_EN_COK_GRUP - 1], gruplar[AKIS_EN_COK_GRUP - 1:]
        diger = {"id": "diger", "ad": "Diğer", "tutar": None, "deger": sum(g["deger"] for g in kalan_gruplar),
                 "cekim_sayisi": None, "olgular": [n for g in kalan_gruplar for n in g["olgular"]],
                 "alt": kalan_gruplar, "cumleler": [c for g in kalan_gruplar for c in g["cumleler"]],
                 "kapsam": None}
        gruplar = bas + [diger]
    return {
        "donem": donem,
        "birim": "USD",
        "kaynak": {"ad": a.get("borsa", "OKX TR"), "tutar": a.get("toplam_dolar"),
                   "cekim_sayisi": a.get("cekim_sayisi"), "adres_sayisi": a.get("adres_sayisi"),
                   "olgular": [ozet.no] if ozet else []},
        "gruplar": gruplar,
        "not": "Tarihsel çekimlerin toplamı; bugünkü bakiye değil. Bant kalınlıkları çekim anındaki dolar "
               "karşılığıyla orantılı.",
    }


def _varliklar(satirlar) -> list[str]:
    toplam: dict[str, Decimal] = {}
    for s in satirlar:
        for varlik, miktar in json.loads(s["varlik_tutar"] or "{}").items():
            toplam[varlik] = toplam.get(varlik, Decimal(0)) + Decimal(miktar)
    return [f"{tr_sayi(m)} {v}" for v, m in toplam.items() if m != 0]


def _dolar(satirlar) -> str | None:
    """Tutar alanı doldurulmamışsa (0 ama coin hareketi var) dolar bilinmiyor sayılır; sıfır yazılmaz."""
    toplam = Decimal(0)
    for s in satirlar:
        tutar = Decimal(s["tutar"] or "0")
        hareket = any(Decimal(m) != 0 for m in json.loads(s["varlik_tutar"] or "{}").values())
        if tutar == 0 and hareket:
            return None
        toplam += tutar
    return f"{tr_sayi(toplam)} $"


def _kopru(db, oturum: str, gizli: bool) -> dict | None:
    if not _tablo_var(db, "kopru"):
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", oturum)
    sinir = m.group(1) if m else "9999-12-31"
    gun = db.execute("SELECT max(gun) FROM kopru WHERE gun <= ?", (sinir,)).fetchone()[0]
    if not gun:
        return None
    db.row_factory = sqlite3.Row
    satirlar = [dict(r) for r in db.execute("SELECT * FROM kopru WHERE gun=? ORDER BY kapsam, sira", (gun,))]
    db.row_factory = None
    kapsamlar = {}
    for kapsam, ad in (("borsa", "Borsadaki hesap"), ("servet", "Toplam servet (borsa + senin cüzdanların)")):
        bu = [s for s in satirlar if s["kapsam"] == kapsam and not (gizli and s["kalem"] in SEVIYE_KALEMLERI)]
        if not bu:
            continue
        ozet = []
        for grup_adi, kalemler in KOPRU_OZET:
            grup = [s for s in bu if s["kalem"] in kalemler]
            if grup:
                ozet.append({"ad": grup_adi, "varliklar": _varliklar(grup), "dolar": _dolar(grup),
                             "olgular": sorted({n for s in grup for n in json.loads(s["olgular"] or "[]")})})
        kapsamlar[kapsam] = {
            "ad": ad,
            "ozet": ozet[:5],
            "kalemler": [{"kalem": s["kalem"], "ad": KALEM_ADI.get(s["kalem"], s["kalem"]),
                          "varliklar": _varliklar([s]), "dolar": _dolar([s]), "aciklama": s["aciklama"],
                          "olgular": json.loads(s["olgular"] or "[]")} for s in bu],
        }
    return {"gun": gun, "kapsamlar": kapsamlar,
            "not": f"Dün 09.00 → {_gun_tr(gun)} 09.00. Tarihsel çekim akışından ayrı bir dönem."}


def _uyarilar(db) -> dict:
    if not _tablo_var(db, "uyari"):
        return {"liste": [], "toplam": 0}
    satirlar = db.execute("SELECT oturum, tur, onem, olgular, zaman FROM uyari").fetchall()
    satirlar.sort(key=lambda r: (ONEM_SIRASI.get(r[2], 9), _ters(r[4])))
    liste = []
    for oturum, tur, onem, olg, zaman in satirlar[:3]:
        nolar = json.loads(olg or "[]")
        olgular = {o.no: o for o in olgulari_oku(db, oturum)}
        metin = next((kalip.olgu_cumlesi(olgular[n]) for n in nolar if n in olgular and kalip.olgu_cumlesi(olgular[n])),
                     None)
        liste.append({"tur": tur, "onem": onem, "zaman": zaman, "olgular": nolar,
                      "metin": metin or "Bu uyarının ayrıntısı gizli."})
    return {"liste": liste, "toplam": len(satirlar)}


def _ters(zaman: str | None) -> str:
    return "".join(chr(0x10FFFF - ord(c)) for c in (zaman or ""))


def _adresler(db) -> list[dict]:
    if not _tablo_var(db, "adres"):
        return []
    return [{"etiket": e, "kisa": k, "ag": ag, "katman": katman, "tahmin": t, "kanit": kanit, "gezgin_url": url,
             "cekim_sayisi": cs}
            for e, k, ag, katman, t, kanit, url, cs in db.execute(
                "SELECT etiket, kisa, ag, katman, tahmin, kanit, gezgin_url, cekim_sayisi FROM adres")]


def _sahiplik(adresler, isaretler) -> list[dict]:
    sonuc = []
    for a in adresler:
        sahip = isaretler.get((a["etiket"], a["ag"]))
        if a["tahmin"] != "benim" and sahip is None:
            continue
        sonuc.append({"etiket": a["etiket"], "kisa": a["kisa"], "ag": a["ag"], "kanit": a["kanit"],
                      "gezgin_url": a["gezgin_url"], "durum": sahip or "tahmin"})
    return sonuc


def _veri_turu(db) -> tuple[str, str | None]:
    if _tablo_var(db, "_ornek"):
        uretim = db.execute("SELECT deger FROM _ornek WHERE anahtar='uretim'").fetchone()
        return "örnek", uretim[0] if uretim else None
    son = db.execute("SELECT max(zaman) FROM cagri").fetchone()[0] if _tablo_var(db, "cagri") else None
    return "canlı", son


def rapor(db: sqlite3.Connection, oturum: str, gizli: bool = True) -> dict:
    olgular = olgulari_oku(db, oturum)
    cumleler = _cumleler(db, oturum)
    adresler = _adresler(db)
    veri_turu, uretim = _veri_turu(db)
    sonuc = {
        "oturum": oturum,
        "veri_turu": veri_turu,
        "uretim": uretim,
        "gizli": gizli,
        "ozet": [{k: c[k] for k in ("metin", "model", "denetim", "olgular")} for c in cumleler if c["yer"] == "pano"],
        "akis": _akis(db, olgular, cumleler, adresler),
        "kopru": _kopru(db, oturum, gizli),
        "uyarilar": _uyarilar(db),
        "sahiplik": _sahiplik(adresler, _isaretler(db)),
    }
    if not gizli:
        k = next((o for o in olgular if o.tur == "kalan_ozet"), None)
        if k:
            sonuc["kalan"] = {"metin": f"{k.alanlar.get('adres_sayisi')} adreste yaklaşık {k.alanlar.get('dolar')} "
                                       f"duruyor.",
                              "not": "Güncel bakiye seviyesi; tarihsel akıştan ayrı zaman damgasıyla okunur.",
                              "olgular": [k.no]}
    return sonuc


def isaret_yaz(db: sqlite3.Connection, etiket: str, ag: str, sahip: str) -> None:
    if sahip not in ("benim", "benim_degil"):
        raise IsaretHatasi("sahip 'benim' ya da 'benim_degil' olmalı")
    if not db.execute("SELECT 1 FROM adres WHERE etiket=? AND ag=?", (etiket, ag)).fetchone():
        raise IsaretHatasi("adres bulunamadı")
    db.execute("CREATE TABLE IF NOT EXISTS isaret (adres_etiket TEXT, ag TEXT, sahip TEXT, zaman TEXT)")
    zaman = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    db.execute("INSERT INTO isaret VALUES (?,?,?,?)", (etiket, ag, sahip, zaman))
    db.commit()
