"""Olgular: anlatıcının tek girdisi. Sayıları burada kod hesaplar ve Türkçe biçimde metne çevirir; model hesaplamaz."""
import json
import time
from datetime import datetime
from decimal import Decimal

from veri import bicim
from veri.aglar import AGLAR, ag_bul
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

def _sozle(x: Decimal, kote: str) -> str:
    """-0,2207 TL → '22 kuruş zarar'; 99,89 TL → '99,89 TL kâr'."""
    yon = "zarar" if x < 0 else "kâr"
    m = abs(x)
    if kote == "TRY" and 0 < m < 1:
        return f"{int((m * 100).quantize(Decimal(1)))} kuruş {yon}"
    return f"{bicim.tl(m) if kote == 'TRY' else bicim.miktar(m, kote)} {yon}"


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
    alanlar["kayit_sozle"] = _sozle(b.kayit_pnl, kote)
    if b.gercek is not None:
        alanlar["gercek_sonuc"] = para(b.gercek, isaretli=True) if kote == "TRY" else para(b.gercek)
        alanlar["gercek_sozle"] = _sozle(b.gercek, kote)
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


# --- oturumun bütün olguları ---

KALEM_ADI = {"baslangic": "dün 09:00", "bitis": "bugün 09:00", "aktarim": "kendi hesapların arası", "disari": "dışarı giden",
             "iceri": "dışarıdan gelen", "bot": "bot sonucu", "takas": "takas farkı", "ucret": "ücretler",
             "fiyat": "fiyat etkisi", "izlenemeyen": "izlenemeyen", "fiyatsiz": "fiyatı bilinmeyen",
             "aciklanamayan": "açıklayamadığım"}
AG_ADI = {ag.anahtar: ag.ad for ag in AGLAR.values()}


def _ms(zaman: str) -> int:
    return int(datetime.fromisoformat(zaman.replace("Z", "+00:00")).timestamp() * 1000)


def _varliklar(d: dict) -> str:
    return ", ".join(bicim.miktar(q, v) for v, q in sorted(d.items()) if q)


def _dolar(h, fiyat) -> Decimal | None:
    if h["dolar"] is not None:
        return Decimal(h["dolar"])
    if fiyat is None:
        return None
    p = fiyat(h["varlik"], _ms(h["zaman"]))
    return None if p is None else Decimal(h["miktar"]) * p


def olgulari_kur(db, oturum: str, gun: str, kopru: dict | None = None, botlar: list | None = None,
                 pencere: tuple | None = None, fiyat=None, olay_siniri: int = 20) -> dict:
    """Oturumun olgularını ve uyarılarını yazar. Dönen: {(kapsam, kalem): [olgu no]} (köprü satırları için)."""
    temizle(db, oturum)
    y = OlguYazici(db, oturum)
    etiket = {r["id"]: r["etiket"] for r in db.execute("SELECT id, etiket FROM adres")}

    # 1. Çekim özeti ve ağ payları (borsanın çekim kaydından)
    cekimler = db.execute("SELECT * FROM hareket WHERE kaynak='borsa' AND tur='cekim' AND durum='ok'").fetchall()
    if cekimler:
        dolarlar = [_dolar(h, fiyat) for h in cekimler]
        toplam = -sum((d for d in dolarlar if d is not None), Decimal(0))
        ilk, son = min(h["zaman"] for h in cekimler), max(h["zaman"] for h in cekimler)
        alanlar = {"borsa": "OKX TR", "cekim_sayisi": str(len(cekimler)),
                   "adres_sayisi": str(len({h["karsi"] for h in cekimler if h["karsi"]})),
                   "toplam_dolar": bicim.dolar(toplam),
                   "donem": f"{bicim.tarih(ilk, saat=False)} – {bicim.tarih(son, saat=False)}"}
        if any(d is None for d in dolarlar):
            alanlar["fiyati_bilinmeyen_cekim"] = str(sum(1 for d in dolarlar if d is None))
        y.ekle("cekim_ozet", alanlar)
        aglar: dict = {}
        for h, d in zip(cekimler, dolarlar):
            ad = ag_bul(h["ag"] or "").ad
            s = aglar.setdefault(ad, [0, Decimal(0)])
            s[0] += 1
            s[1] += -(d or 0)
        for ad, (n, d) in sorted(aglar.items(), key=lambda x: -x[1][1]):
            y.ekle("ag_payi", {"ag": ad, "cekim_sayisi": str(n), "dolar": bicim.dolar(d)})

    # 2. Adreslerde kalan (seviye → gizli)
    if fiyat is not None:
        simdi_ms = int(time.time() * 1000)
        kalan: dict = {}
        for r in db.execute("SELECT adres_id, varlik, miktar FROM hareket WHERE hesap='cuzdan' AND supheli=0"):
            kalan.setdefault(r["adres_id"], {}).setdefault(r["varlik"], Decimal(0))
            kalan[r["adres_id"]][r["varlik"]] += Decimal(r["miktar"])
        dolu, toplam = 0, Decimal(0)
        for aid, d in kalan.items():
            deger = sum((q * (fiyat(v, simdi_ms) or 0) for v, q in d.items() if q > 0), Decimal(0))
            if deger >= 1:
                dolu += 1
                toplam += deger
        y.ekle("kalan_ozet", {"adres_sayisi": str(dolu), "dolar": bicim.dolar(toplam)}, gizli=True)

    # 3. Köprü
    kopru_olgu: dict = {}
    if kopru:
        for kapsam, kalemler in kopru.items():
            degisim = Decimal(0)
            for k in kalemler:
                if k.kalem not in ("baslangic", "bitis", "aciklanamayan") and not k.varlik and not k.dolar:
                    continue
                if k.kalem not in ("baslangic", "bitis"):
                    degisim += k.dolar
                alanlar = {"kapsam": kapsam, "kalem": k.kalem, "ad": KALEM_ADI[k.kalem], "tutar": bicim.dolar(k.dolar)}
                if k.varlik:
                    alanlar["coin"] = _varliklar(k.varlik)
                no = y.ekle("kopru", alanlar, gizli=k.kalem in ("baslangic", "bitis"))
                kopru_olgu[(kapsam, k.kalem)] = [no]
                if k.kalem == "aciklanamayan" and (k.dolar or k.varlik):
                    y.uyari("aciklanamayan", "bilgi", [no])
            no = y.ekle("kopru_ozet", {"kapsam": kapsam, "ad": "borsadaki hesap" if kapsam == "borsa" else "toplam servet",
                                       "degisim": bicim.dolar(degisim), "miktar": bicim.dolar(abs(degisim)),
                                       "yon": "arttı" if degisim > 0 else ("azaldı" if degisim < 0 else "değişmedi"),
                                       "donem": "dün 09:00 → bugün 09:00"})
            kopru_olgu[(kapsam, "ozet")] = [no]

    # 4. Botlar
    for b in botlar or []:
        bot_olgusu(y, b)

    # 5. Zincir olayları: pencere içindekiler + “benim” adreslerin öne çıkan takas/stake olayları + şüpheliler
    benim = {r["id"] for r in db.execute("SELECT id FROM adres WHERE tahmin='benim'")}
    olay_bilgi = {}
    try:
        olay_bilgi = {(r["adres_id"], r["tx"]): dict(r) for r in db.execute("SELECT * FROM _olay")}
    except Exception:
        pass
    gruplar: dict = {}
    for h in db.execute("SELECT * FROM hareket WHERE hesap='cuzdan' ORDER BY zaman"):
        gruplar.setdefault((h["adres_id"], h["islem_kimligi"]), []).append(h)
    secilen = []
    for (aid, tx), hs in gruplar.items():
        ts = _ms(hs[0]["zaman"])
        pencerede = bool(pencere and pencere[0] < ts <= pencere[1])
        bilgi = olay_bilgi.get((aid, tx), {})
        one_cikan = aid in benim and (hs[0]["tur"] in ("takas", "taninmadi") or "stake" in (bilgi.get("islev") or "").lower())
        if pencerede or one_cikan or hs[0]["supheli"]:
            secilen.append((ts, aid, tx, hs, bilgi, pencerede))
    secilen.sort(key=lambda x: -x[0])                     # adres başına en yeni olaylar kalsın
    sayac: dict = {}
    tutulan = []
    for x in secilen:
        sayac[x[1]] = sayac.get(x[1], 0) + 1
        if sayac[x[1]] <= olay_siniri or x[5]:
            tutulan.append(x)
    for ts, aid, tx, hs, bilgi, pencerede in sorted(tutulan, key=lambda x: x[0]):
        ana = [h for h in hs if h["tur"] != "ucret"]
        tur = ana[0]["tur"] if ana else "ucret"
        verilen = {h["varlik"]: -Decimal(h["miktar"]) for h in ana if Decimal(h["miktar"]) < 0}
        alinan = {h["varlik"]: Decimal(h["miktar"]) for h in ana if Decimal(h["miktar"]) > 0}
        ucret = {h["varlik"]: -Decimal(h["miktar"]) for h in hs if h["tur"] == "ucret"}
        alanlar = {"tarih": bicim.tarih(ts), "adres": etiket.get(aid, "?"), "ag": AG_ADI.get(hs[0]["ag"], hs[0]["ag"] or "")}
        if tur == "takas":
            alanlar["verilen"] = _varliklar(verilen)
            alanlar["alinan"] = _varliklar(alinan)
        elif verilen or alinan:
            alanlar["miktar"] = _varliklar(verilen or alinan)
        if ucret:
            alanlar["ag_ucreti"] = _varliklar(ucret)
        karsi = next((h["karsi"] for h in ana if h["karsi"]), None)
        if karsi:
            alanlar["karsi"] = "borsa (OKX TR)" if karsi == "ana" else karsi
        if bilgi.get("islev"):
            alanlar["islev"] = bilgi["islev"]
        fiyatsiz = [v for v in list(verilen) + list(alinan) if fiyat is not None and fiyat(v, ts) is None]
        if fiyatsiz:
            alanlar["dolar_fiyati_yok"] = ", ".join(fiyatsiz)
        no = y.ekle("supheli" if hs[0]["supheli"] else tur, alanlar, kaynak=[h["id"] for h in hs])
        if hs[0]["supheli"]:
            y.uyari(bilgi.get("neden") or "supheli_token", "orta", [no])
        elif tur == "taninmadi" and pencerede:
            y.uyari("taninmadi", "bilgi", [no])

    # 6. Okunamayan ağlar (sessizce kaybolmaz)
    try:
        okunamayan = db.execute("SELECT adres_id, ag FROM _ag_durum WHERE durum='okunamadi' AND cekim_agi=1").fetchall()
    except Exception:
        okunamayan = []
    nolar = []
    for r in okunamayan:
        et = etiket.get(r["adres_id"], "?")
        ilgili = [h for h in cekimler if h["karsi"] == et and ag_bul(h["ag"] or "").anahtar == r["ag"]]
        d = -sum(((_dolar(h, fiyat) or 0) for h in ilgili), Decimal(0))
        nolar.append(y.ekle("okunamayan_ag", {"adres": et, "ag": AG_ADI.get(r["ag"], r["ag"]), "cekim_sayisi": str(len(ilgili)),
                                              "dolar": bicim.dolar(d), "durum": "bu ağda yalnız çekimi görüyorum"}))
    if nolar:
        y.uyari("okunamayan_ag", "bilgi", nolar)

    # 7. Defter–zincir kapanışı (benim adresler): kapanmayan kısım açıkça söylenir
    try:
        kapanis = db.execute("SELECT adres_id, ag, varlik, fark FROM _kapanis").fetchall()
    except Exception:
        kapanis = []
    for r in kapanis:
        fark = Decimal(r["fark"])
        if r["adres_id"] in benim and abs(fark) > Decimal("0.000001"):
            no = y.ekle("defter_farki", {"adres": etiket.get(r["adres_id"], "?"), "ag": AG_ADI.get(r["ag"], r["ag"]),
                                         "fark": bicim.miktar(fark, r["varlik"]),
                                         "durum": "zincirdeki bakiye defterle kapanmıyor; bu kadarını açıklayamadım"})
            y.uyari("aciklanamayan", "bilgi", [no])
    return kopru_olgu


def kalip_cumle(db, oturum: str) -> tuple[str, list[str]]:
    """Anlatıcı yoksa ya da geç kalırsa: yalnız olgu metinlerinden kurulan cümle (gizli olgu kullanılmaz)."""
    olgular = {r["no"]: (r["tur"], json.loads(r["alanlar"])) for r in
               db.execute("SELECT no, tur, alanlar FROM olgu WHERE oturum=? AND gizli=0", (oturum,))}
    parcalar, dayanak = [], []
    bot = next(((no, a) for no, (t, a) in olgular.items() if t == "bot_uyusmazlik"), None)
    if bot:
        no, a = bot
        parcalar.append(f"{a['bot']} botu: kayıt {a['kayit_sozle']} diyor; hesabına dönen paraya göre {a['gercek_sozle']}.")
        dayanak.append(no)
    ozet = next(((no, a) for no, (t, a) in olgular.items() if t == "kopru_ozet" and a.get("kapsam") == "servet"), None)
    if ozet:
        no, a = ozet
        if a.get("yon") == "değişmedi":
            parcalar.append("Dünden bugüne toplam servetin değişmedi.")
        elif a.get("yon"):
            parcalar.append(f"Dünden bugüne toplam servetin {a['miktar']} {a['yon']}.")
        else:
            parcalar.append(f"Dünden bugüne toplam servetin {a['degisim']} değişti.")
        dayanak.append(no)
    if not parcalar:
        cek = next(((no, a) for no, (t, a) in olgular.items() if t == "cekim_ozet"), None)
        if cek:
            no, a = cek
            parcalar.append(f"OKX TR'den {a['cekim_sayisi']} çekimle {a['adres_sayisi']} adrese {a['toplam_dolar']} gitti.")
            dayanak.append(no)
    return " ".join(parcalar), dayanak
