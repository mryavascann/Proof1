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
UYARI_METNI = {"supheli_token": "Şüpheli görünen token hareketi görüldü; ayrıntı defterde.",
               "adres_zehirleme": "Adres zehirleme kalıbına benzeyen bir giriş görüldü; ayrıntı defterde.",
               "aciklanamayan": "Defterde açıklanamayan bir fark görüldü.",
               "okunamayan_ag": "Bir ağda yalnız çekim görülebiliyor; sonrası okunamadı.",
               "taninmadi": "Kaynağı tanınmayan bir giriş görüldü."}
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


def _birim(varlik: str) -> str:
    """Panoda Türk lirası her yerde TL yazılır (anlatıcının gözlem metinleriyle aynı)."""
    return "TL" if varlik == "TRY" else varlik


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
    return [f"{tr_sayi(m)} {_birim(v)}" for v, m in toplam.items() if m != 0]


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


def _uyari_satirlari(db, oturum: str) -> list:
    """Bu raporun uyarıları ve dönem içindeki canlı bot izleyicisi uyarıları (oturum `canli-<algoId>`).
    Başka günlerin raporlarındaki uyarılar karışmaz."""
    if not _tablo_var(db, "uyari"):
        return []
    gun = _gun(oturum)
    if gun:
        from datetime import date, timedelta
        sinir = f"{date.fromisoformat(gun) - timedelta(days=1)}T06:00"  # dün 09.00 İstanbul, UTC
    else:
        sinir = ""
    satirlar = db.execute("SELECT oturum, tur, onem, olgular, zaman FROM uyari "
                          "WHERE oturum=? OR (oturum LIKE 'canli-%' AND coalesce(zaman, '') >= ?)",
                          (oturum, sinir)).fetchall()
    satirlar.sort(key=lambda r: (ONEM_SIRASI.get(r[2], 9), _ters(r[4])))
    return satirlar


def _uyari_metni(db, oturum: str, tur: str, nolar: list, olgu_onbellek: dict) -> str:
    if oturum not in olgu_onbellek:
        olgu_onbellek[oturum] = {o.no: o for o in olgulari_oku(db, oturum)}
    olgular = olgu_onbellek[oturum]
    metin = next((kalip.olgu_cumlesi(olgular[n]) for n in nolar if n in olgular and kalip.olgu_cumlesi(olgular[n])),
                 None)
    if metin:
        return metin
    if any(olgular[n].gizli for n in nolar if n in olgular):
        return "Bu uyarının ayrıntısı gizli."
    return UYARI_METNI.get(tur, "Bu uyarı için cümle yok; ayrıntı defterde.")


def _uyarilar(db, oturum: str) -> dict:
    satirlar = _uyari_satirlari(db, oturum)
    onbellek: dict = {}
    liste = []
    for u_oturum, tur, onem, olg, zaman in satirlar[:3]:
        nolar = json.loads(olg or "[]")
        liste.append({"tur": tur, "onem": onem, "zaman": zaman, "olgular": nolar,
                      "metin": _uyari_metni(db, u_oturum, tur, nolar, onbellek)})
    return {"liste": liste, "toplam": len(satirlar)}


def _uyari_gruplari(db, oturum: str) -> list[dict]:
    """Ayrıntılı mod: bütün uyarılar tür ve öneme göre gruplanır; her grupta sayı, son zaman, örnek cümle."""
    gruplar: dict = {}
    onbellek: dict = {}
    for u_oturum, tur, onem, olg, zaman in _uyari_satirlari(db, oturum):
        g = gruplar.get((tur, onem))
        if g is None:
            nolar = json.loads(olg or "[]")
            g = gruplar[(tur, onem)] = {"tur": tur, "onem": onem, "sayi": 0, "son": zaman, "olgular": nolar,
                                        "metin": _uyari_metni(db, u_oturum, tur, nolar, onbellek),
                                        "canli": u_oturum.startswith("canli-")}
        g["sayi"] += 1
    return list(gruplar.values())


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
        "uyarilar": _uyarilar(db, oturum),
        "sahiplik": _sahiplik(adresler, _isaretler(db)),
    }
    if not gizli:
        k = next((o for o in olgular if o.tur == "kalan_ozet"), None)
        if k and sayilari_ayikla(str(k.alanlar.get("dolar", ""))):  # değer yoksa (ör. "gizli") cümle kurulmaz
            sonuc["kalan"] = {"metin": f"{k.alanlar.get('adres_sayisi')} adreste yaklaşık {k.alanlar.get('dolar')} "
                                       f"duruyor.",
                              "not": "Güncel bakiye seviyesi; tarihsel akıştan ayrı zaman damgasıyla okunur.",
                              "olgular": [k.no]}
    return sonuc


# ---------------------------------------------------------------- ayrıntılı mod (M6)
GEZGIN = "https://testnet.snowtrace.io"
MUHUR_NOTU = ("Bu kayıt mühürlendikten sonra değiştirilmediği kontrol edilebilir; içeriğin doğruluğunu kanıtlamaz. "
              "Zincire yalnız kök yazılır; adres ya da tutar yazılmaz.")


def _gun(oturum: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", oturum)
    return m.group(1) if m else None


def _kisa(metin: str | None, bas: int = 6, son: int = 4) -> str | None:
    if not metin:
        return None
    return metin if len(metin) <= bas + son + 1 else f"{metin[:bas]}…{metin[-son:]}"


def _hareketler(db, oturum: str, en_cok: int = 200) -> dict:
    gun = _gun(oturum)
    if not gun or not _tablo_var(db, "hareket"):
        return {"pencere": None, "satirlar": [], "toplam": 0}
    from datetime import date, timedelta
    g = date.fromisoformat(gun)
    bas, son = f"{(g - timedelta(days=1)).isoformat()}T06:00:00", f"{g.isoformat()}T06:00:00"  # 09.00 İstanbul
    toplam = db.execute("SELECT count(*) FROM hareket WHERE zaman >= ? AND zaman < ?", (bas, son)).fetchone()[0]
    satirlar = []
    for r in db.execute("SELECT zaman, kaynak, hesap, ag, varlik, miktar, dolar, tur, karsi, supheli, durum, kaynak_okuma, "
                        "islem_kimligi FROM hareket WHERE zaman >= ? AND zaman < ? ORDER BY zaman DESC LIMIT ?",
                        (bas, son, en_cok)):
        zaman, kaynak, hesap, ag, varlik, miktar, dolar, tur, karsi, supheli, durum, okuma, islem = r
        satirlar.append({"zaman": zaman, "kaynak": kaynak, "hesap": hesap, "ag": ag, "varlik": varlik,
                         "miktar": f"{tr_sayi(Decimal(miktar))} {_birim(varlik)}" if miktar else None,
                         "dolar": f"{tr_sayi(Decimal(dolar))} $" if dolar not in (None, "") else None,
                         "tur": tur, "karsi": karsi, "supheli": bool(supheli), "durum": durum,
                         "kaynak_okuma": okuma, "islem": _kisa(islem)})
    onceki = (g - timedelta(days=1))
    return {"pencere": f"{_gun_tr(onceki.isoformat())} 09.00 → {_gun_tr(gun)} 09.00", "satirlar": satirlar,
            "toplam": toplam}


def _iz(db, oturum: str) -> tuple[str | None, list[dict]]:
    if not _tablo_var(db, "iz"):
        return None, []
    son = db.execute("SELECT iz_no FROM iz WHERE oturum=? ORDER BY zaman DESC, rowid DESC LIMIT 1", (oturum,)).fetchone()
    if not son:
        return None, []
    adimlar = [{"sira": s, "dusunce": d, "arac": a, "gozlem": g, "karar": k, "sonuc": so, "zaman": z}
               for s, d, a, g, k, so, z in db.execute(
                   "SELECT sira, dusunce, arac, gozlem, karar, sonuc, zaman FROM iz WHERE iz_no=? ORDER BY sira", (son[0],))]
    return son[0], adimlar


def _kanit(db, oturum: str) -> dict:
    if not _tablo_var(db, "cagri"):
        return {"gruplar": [], "hatalar": [], "toplam": 0, "salt_okunur_hepsi": True, "denetim_kaydi": []}
    gruplar: dict = {}
    hatalar = []
    for kaynak, ad, sure, alanlar, sonuc, kod, salt, satir, zaman, param in db.execute(
            "SELECT kaynak, ad, sure_ms, alanlar, sonuc, kod, salt_okunur, satir, zaman, parametreler FROM cagri "
            "WHERE oturum=? ORDER BY id", (oturum,)):
        g = gruplar.setdefault((kaynak, ad), {"kaynak": kaynak, "ad": ad, "cagri": 0, "hata": 0, "_sure": [],
                                              "alanlar": set(), "salt_okunur": True, "satir": 0})
        g["cagri"] += 1
        g["_sure"].append(sure or 0)
        g["alanlar"] |= set(json.loads(alanlar or "[]"))
        g["salt_okunur"] &= bool(salt)
        g["satir"] += satir or 0
        if sonuc != "ok":
            g["hata"] += 1
            hatalar.append({"kaynak": kaynak, "ad": ad, "kod": kod or "hata", "sure_ms": sure, "zaman": zaman,
                            "parametreler": param})
    liste = []
    for g in gruplar.values():
        s = g.pop("_sure")
        g.update(ort_ms=int(sum(s) / len(s)), en_cok_ms=max(s), alanlar=sorted(g["alanlar"]))
        liste.append(g)
    oncelik = {"OKX TR": 0, "ATK": 1, "OnchainOS": 2}
    liste.sort(key=lambda g: (oncelik.get(g["kaynak"], 9), -g["cagri"], g["ad"]))
    denetim = []
    if _tablo_var(db, "_atk_denetim"):
        denetim = [{"zaman": z, "arac": a, "seviye": s, "sure_ms": ms} for z, a, s, ms in db.execute(
            "SELECT zaman, arac, seviye, sure_ms FROM _atk_denetim ORDER BY zaman DESC LIMIT 20")]
    return {"gruplar": liste, "hatalar": hatalar[-10:], "toplam": sum(g["cagri"] for g in liste),
            "salt_okunur_hepsi": all(g["salt_okunur"] for g in liste), "denetim_kaydi": denetim}


def _muhur(db, oturum: str, ayar: dict) -> dict:
    gun = _gun(oturum)
    kayitlar = []
    if _tablo_var(db, "muhur"):
        for g, k, o, i, a, ag, s, z in db.execute(
                "SELECT gun, kok, onceki_kok, islem_kimligi, agent_id, ag, sozlesme, zaman FROM muhur ORDER BY gun DESC, zaman DESC"):
            kayitlar.append({"gun": g, "kok": k, "onceki_kok": o, "islem": i, "agent_id": a, "sozlesme": s, "zaman": z,
                             "gezgin": f"{GEZGIN}/tx/{i}" if i else None})
    sozlesme, kimlik = ayar.get("sozlesme"), ayar.get("kimlik")
    return {
        "ag": "Avalanche Fuji", "chain_id": 43113, "agent_id": ayar.get("agent_id"),
        "kimlik": kimlik, "sozlesme": sozlesme,
        "kimlik_gezgin": f"{GEZGIN}/nft/{kimlik}/{ayar.get('agent_id')}" if kimlik and ayar.get("agent_id") else None,
        "sozlesme_gezgin": f"{GEZGIN}/address/{sozlesme}" if sozlesme else None,
        "gun": gun, "gun_muhru": next((k for k in kayitlar if k["gun"] == gun), None), "son": kayitlar[:5],
        "dogrulama": "bekliyor", "not": MUHUR_NOTU,
    }


def muhur_dogrula(db: sqlite3.Connection, gun: str, ayar: dict, rpc) -> dict:
    """Yerel muhur kaydındaki kökü zincirdeki rootOf(agentId, gün) ile karşılaştırır."""
    if not _tablo_var(db, "muhur"):
        return {"durum": "yerel_kayit_yok"}
    satir = db.execute("SELECT kok FROM muhur WHERE gun=? ORDER BY zaman DESC LIMIT 1", (gun,)).fetchone()
    if not satir:
        return {"durum": "yerel_kayit_yok"}
    from eth_abi import encode
    from eth_utils import keccak
    gun_no = int(gun.replace("-", ""))
    veri_ = keccak(text="rootOf(uint256,uint32)")[:4] + encode(["uint256", "uint32"], [int(ayar["agent_id"]), gun_no])
    try:
        zincir = rpc("eth_call", [{"to": ayar["sozlesme"], "data": "0x" + veri_.hex()}, "latest"])
    except Exception:  # ağ, RPC, zaman aşımı
        return {"durum": "baglanilamadi"}
    zincir = (zincir or "").lower()
    if not zincir or int(zincir, 16) == 0:
        return {"durum": "zincirde_yok"}
    return {"durum": "dogrulandi" if zincir == satir[0].lower() else "uyusmuyor", "zincirdeki": zincir, "yerel": satir[0]}


def _butce(db, oturum: str, kullanici: str) -> dict:
    gun = _gun(oturum)
    ay = gun[:7] if gun else datetime.now(timezone.utc).strftime("%Y-%m")
    from anlatim import butce as b
    satirlar = db.execute("SELECT model, tutar_tl, durum FROM butce WHERE kullanici=? AND ay=?",
                          (kullanici, ay)).fetchall() if _tablo_var(db, "butce") else []
    harcanan = sum((Decimal(t or "0") for _, t, _ in satirlar), Decimal(0))
    durumlar: dict = {}
    for _, _, d in satirlar:
        durumlar[d] = durumlar.get(d, 0) + 1
    kip = b.model_sec(db, kullanici, ay, 3000, 1500) if _tablo_var(db, "butce") else b.SONNET
    return {"kullanici": kullanici, "ay": ay, "harcanan": f"{tr_sayi(harcanan.quantize(Decimal('0.01')))} TL",
            "tavan": f"{tr_sayi(b.TAVAN_TL)} TL", "kalan": f"{tr_sayi((b.TAVAN_TL - harcanan).quantize(Decimal('0.01')))} TL",
            "cagri": len(satirlar), "durumlar": durumlar, "kip": kip,
            "son_model": satirlar[-1][0] if satirlar else None}


def ayrinti(db: sqlite3.Connection, oturum: str, gizli: bool = True, muhur_ayar: dict | None = None,
            kullanici: str = "bugra") -> dict:
    olgular = olgulari_oku(db, oturum)
    bot = next((o for o in olgular if o.tur == "bot_uyusmazlik" and not o.gizli), None)
    iz_no, iz = _iz(db, oturum)
    return {
        "oturum": oturum,
        "gizli": gizli,
        "hareketler": _hareketler(db, oturum),
        "uyarilar": _uyari_gruplari(db, oturum),
        "cumleler": [{k: c[k] for k in ("yer", "metin", "model", "denetim", "olgular")} for c in _cumleler(db, oturum)],
        "bot": {"olgu": bot.alanlar if bot else None, "olgu_no": bot.no if bot else None, "iz_no": iz_no, "iz": iz,
                "kayit": any("[kayıt]" in (a["arac"] or "") for a in iz)},
        "kanit": _kanit(db, oturum),
        "muhur": _muhur(db, oturum, muhur_ayar or {}),
        "butce": _butce(db, oturum, kullanici),
    }


def isaret_yaz(db: sqlite3.Connection, etiket: str, ag: str, sahip: str) -> None:
    if sahip not in ("benim", "benim_degil"):
        raise IsaretHatasi("sahip 'benim' ya da 'benim_degil' olmalı")
    if not db.execute("SELECT 1 FROM adres WHERE etiket=? AND ag=?", (etiket, ag)).fetchone():
        raise IsaretHatasi("adres bulunamadı")
    db.execute("CREATE TABLE IF NOT EXISTS isaret (adres_etiket TEXT, ag TEXT, sahip TEXT, zaman TEXT)")
    zaman = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    db.execute("INSERT INTO isaret VALUES (?,?,?,?)", (etiket, ag, sahip, zaman))
    db.commit()
