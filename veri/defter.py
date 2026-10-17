"""Defter: borsa kayıtlarını `hareket` satırlarına çevirir ve bakiye zincirini denetler.

OKX işlem hesabı defterinde bota giden para iki satırdır: hesaptan çıkış ve botun kendi iç defterine
giriş. Bu yüzden her para birimi için birden çok zincir tutulur (hesap + her bot). `hareket` tablosuna
yalnız hesap zincirinin satırları yazılır; botun içi `_defter` tablosunda kalır (servet iki kez sayılmaz).
"""
from dataclasses import dataclass, field
from decimal import Decimal

from veri.atk import Atk, satirlar as atk_satirlar
from veri.borsa import Kayit, ondalik
from veri.kayit import ms_iso


@dataclass
class DefterSatiri:
    kimlik: str
    ts: int
    ccy: str
    chg: Decimal
    bal: Decimal
    tip: str
    alt_tip: str
    fee: Decimal
    inst: str
    ord: str
    hesap: str
    kaynak: str
    defter: str = ""            # hesap | bot (zincirle doldurur)

    @property
    def acilis(self) -> Decimal:
        return self.bal - self.chg


@dataclass
class Fark:
    ccy: str
    kimlik: str
    ts: int
    acilis: Decimal


@dataclass
class _Zincir:
    tur: str
    son_bal: Decimal
    satirlar: list = field(default_factory=list)

    def ekle(self, s: DefterSatiri):
        s.defter = self.tur
        self.son_bal = s.bal
        self.satirlar.append(s)


@dataclass
class ZincirSonucu:
    zincirler: dict
    farklar: list


def ayristir(ham: list[dict], hesap: str, kaynak: str) -> list[DefterSatiri]:
    """Alanı eksik ya da sayı olmayan satır atlanır (çağıran sayıyı karşılaştırabilir)."""
    sonuc = []
    for r in ham:
        chg, bal = ondalik(r.get("balChg")), ondalik(r.get("bal"))
        ts = str(r.get("ts") or "")
        if chg is None or bal is None or not ts.isdigit() or not r.get("ccy") or not r.get("billId"):
            continue
        sonuc.append(DefterSatiri(
            kimlik=str(r["billId"]), ts=int(ts), ccy=str(r["ccy"]), chg=chg, bal=bal,
            tip=str(r.get("type") or ""), alt_tip=str(r.get("subType") or ""),
            fee=ondalik(r.get("fee") or "0") or Decimal(0), inst=str(r.get("instId") or ""),
            ord=str(r.get("ordId") or ""), hesap=hesap, kaynak=kaynak))
    return sonuc


def _cift(s: DefterSatiri, grup: list[DefterSatiri]) -> DefterSatiri | None:
    """Aynı anda, aynı coinde, ters yönlü strateji aktarımı (hesap ↔ bot)."""
    if s.tip != "12":
        return None
    return next((x for x in grup if x is not s and x.tip == "12" and x.ccy == s.ccy and x.chg == -s.chg), None)


def _kardes(s: DefterSatiri, grup: list[DefterSatiri]) -> DefterSatiri | None:
    """Aynı emrin öbür coindeki bacağı."""
    if s.tip != "2" or not s.ord:
        return None
    return next((x for x in grup if x is not s and x.ord == s.ord and x.ccy != s.ccy and x.defter), None)


def _ipucu(s: DefterSatiri, grup) -> tuple[str | None, str | None]:
    """(tercih edilen defter, dışlanan defter)."""
    c = _cift(s, grup)
    if c is not None and c.defter:
        return ("bot" if c.defter == "hesap" else "hesap"), c.defter
    k = _kardes(s, grup)
    if k is not None:
        return k.defter, None
    return None, None


def zincirle(satirlar: list[DefterSatiri]) -> ZincirSonucu:
    satirlar.sort(key=lambda s: (s.ts, s.kimlik))
    zincirler: dict[str, list[_Zincir]] = {}
    farklar: list[Fark] = []
    i = 0
    while i < len(satirlar):
        j = i
        while j < len(satirlar) and satirlar[j].ts == satirlar[i].ts:
            j += 1
        grup = satirlar[i:j]
        # Açılışı sıfır olmayanlar önce: var olan bir zincire bağlanmak zorundalar.
        kalan = sorted(grup, key=lambda s: s.acilis == 0)
        ilerledi = True
        while kalan and ilerledi:
            ilerledi = False
            for s in list(kalan):
                tercih, disla = _ipucu(s, grup)
                adaylar = [z for z in zincirler.get(s.ccy, []) if z.son_bal == s.acilis and z.tur != disla]
                if tercih:
                    adaylar.sort(key=lambda z: z.tur != tercih)
                if adaylar and (s.acilis != 0 or tercih or len(adaylar) == 1):
                    adaylar[0].ekle(s)
                    kalan.remove(s)
                    ilerledi = True
        for s in kalan:
            zz = zincirler.setdefault(s.ccy, [])
            tercih, _ = _ipucu(s, grup)
            if s.acilis == 0:
                tur = tercih or ("bot" if (s.tip == "12" and s.chg > 0) or any(z.tur == "hesap" for z in zz) else "hesap")
            elif not any(z.tur == "hesap" for z in zz):
                tur = "hesap"              # pencerenin başı: hesabın açılış bakiyesi
            else:
                farklar.append(Fark(s.ccy, s.kimlik, s.ts, s.acilis))
                tur = tercih or "hesap"
            z = _Zincir(tur, s.bal)
            z.ekle(s)
            zz.append(z)
        i = j
    return ZincirSonucu(zincirler, farklar)


def _h(s: DefterSatiri, tur: str, miktar: Decimal, ek: str = "") -> dict:
    return {"zaman": ms_iso(s.ts), "kaynak": "borsa", "hesap": s.hesap, "adres_id": None, "ag": None,
            "varlik": s.ccy, "miktar": str(miktar), "dolar": None, "tur": tur,
            "islem_kimligi": s.ord or s.kimlik, "karsi": None, "supheli": 0, "durum": "ok",
            "kaynak_okuma": s.kaynak, "ham_kimlik": f"{s.kaynak}:{s.hesap}:{s.kimlik}{ek}"}


def hareketlere(satirlar: list[DefterSatiri]) -> list[dict]:
    """Yalnız hesap zincirindeki satırlar (zincirle'den sonra çağrılır)."""
    sonuc = []
    for s in satirlar:
        if s.defter != "hesap":
            continue
        if s.tip == "12":
            sonuc.append(_h(s, "bota_giris" if s.chg < 0 else "bottan_donus", s.chg))
        elif s.tip == "2":
            brut = s.chg - s.fee
            sonuc.append(_h(s, "alim" if brut > 0 else "satim", brut))
            if s.fee:
                sonuc.append(_h(s, "ucret", s.fee, ":ucret"))
        elif s.tip == "1":
            sonuc.append(_h(s, "aktarim", s.chg))
        else:
            sonuc.append(_h(s, "taninmadi", s.chg))
    return sonuc


def cekim_hareketleri(kayitlar: list[Kayit]) -> list[dict]:
    """Ana hesabın çekim/yatırma kaydı → hareket (çekimde ücret ayrı satır)."""
    sonuc = []
    for k in kayitlar:
        ortak = {"zaman": ms_iso(k.ts), "kaynak": "borsa", "hesap": "ana", "adres_id": None, "ag": k.chain,
                 "dolar": None, "islem_kimligi": k.tx or k.kimlik, "karsi": None, "supheli": 0,
                 "durum": "okunamadi" if k.okunamadi else "ok",
                 "kaynak_okuma": "withdrawal-history" if k.tur == "cekim" else "deposit-history"}
        if k.tur == "cekim":
            sonuc.append(dict(ortak, varlik=k.ccy, miktar=str(-k.miktar), tur="cekim", ham_kimlik=f"cekim:{k.kimlik}"))
            if k.ucret:
                sonuc.append(dict(ortak, varlik=k.ucret_ccy, miktar=str(-k.ucret), tur="ucret", ham_kimlik=f"cekim:{k.kimlik}:ucret"))
        else:
            sonuc.append(dict(ortak, varlik=k.ccy, miktar=str(k.miktar), tur="yatirma", ham_kimlik=f"yatirma:{k.kimlik}"))
    return sonuc


# Fonlama hesabı (asset/bills) türleri. Kripto çekim/yatırma ayrıntılı kayıttan gelir, burada atlanır;
# TL (banka) yatırma/çekimi ise yalnız burada görünür.
FONLAMA_ATLA = {"1", "2", "13"}
FONLAMA_AKTARIM = {"20", "21", "22", "23", "130", "131"}
FONLAMA_GIRIS = {"525"}        # Lira Boost kazancı (faiz)
FONLAMA_UCRET = {"526"}        # Lira Boost vergisi
FIAT = {"TRY"}


def fonlama_hareketleri(ham: list[dict], hesap: str = "ana") -> list[dict]:
    sonuc = []
    for r in ham:
        chg, ts, tip, ccy = ondalik(r.get("balChg")), str(r.get("ts") or ""), str(r.get("type")), str(r.get("ccy"))
        if chg is None or not ts.isdigit():
            continue
        karsi = None
        if tip in FONLAMA_ATLA:
            if ccy not in FIAT or tip == "13":
                continue
            tur, karsi = ("yatirma" if tip == "1" else "cekim"), "banka"
        elif tip in FONLAMA_AKTARIM:
            tur = "aktarim"
        elif tip in FONLAMA_GIRIS:
            tur = "giris"
        elif tip in FONLAMA_UCRET:
            tur = "ucret"
        else:
            tur = "taninmadi"
        sonuc.append({"zaman": ms_iso(ts), "kaynak": "borsa", "hesap": hesap, "adres_id": None, "ag": None,
                      "varlik": ccy, "miktar": str(chg), "dolar": None, "tur": tur,
                      "islem_kimligi": str(r.get("billId")), "karsi": karsi, "supheli": 0, "durum": "ok",
                      "kaynak_okuma": "asset/bills", "ham_kimlik": f"asset/bills:{hesap}:{r.get('billId')}"})
    return sonuc


def _sayfala(atk: Atk, arac: str, en_cok: int = 30) -> list[dict]:
    hepsi, after = [], None
    for _ in range(en_cok):
        arg = {"limit": 100}
        if after:
            arg["after"] = after
        sayfa = atk_satirlar(atk.cagir(arac, arg))
        hepsi.extend(sayfa)
        if len(sayfa) < 100:
            break
        after = sayfa[-1]["billId"]
    return hepsi


def alt_defteri(atk: Atk, hesap: str = "alt", arsiv: bool = True) -> list[DefterSatiri]:
    """Son 7 gün + (isteğe bağlı) 3 aylık arşiv, billId ile tekilleştirilmiş."""
    ham = {r["billId"]: r for r in _sayfala(atk, "account_get_bills") if r.get("billId")}
    if arsiv:
        for r in _sayfala(atk, "account_get_bills_archive"):
            ham.setdefault(r.get("billId"), r)
    return ayristir(list(ham.values()), hesap, "account_get_bills")


HAREKET_ALANLARI = ["zaman", "kaynak", "hesap", "adres_id", "ag", "varlik", "miktar", "dolar", "tur",
                    "islem_kimligi", "karsi", "supheli", "durum", "kaynak_okuma", "ham_kimlik"]


def yaz(db, hareketler: list[dict]) -> int:
    """Yeni satırı ekler; var olanın türünü/durumunu günceller (dolar ve sonradan atanan karşı taraf korunur)."""
    once = db.execute("SELECT COUNT(*) FROM hareket").fetchone()[0]
    db.executemany(f"INSERT INTO hareket ({','.join(HAREKET_ALANLARI)}) VALUES ({','.join('?' * len(HAREKET_ALANLARI))})"
                   " ON CONFLICT(ham_kimlik) DO UPDATE SET tur=excluded.tur, durum=excluded.durum, supheli=excluded.supheli,"
                   " karsi=COALESCE(excluded.karsi, hareket.karsi)",
                   [tuple(h[a] for a in HAREKET_ALANLARI) for h in hareketler])
    db.commit()
    return db.execute("SELECT COUNT(*) FROM hareket").fetchone()[0] - once


def defter_yaz(db, satirlar: list[DefterSatiri]):
    """Ham defter (bot içi dahil) — bot karşılaştırıcı ve denetim için iç tablo."""
    db.execute("""CREATE TABLE IF NOT EXISTS _defter (kimlik TEXT, hesap TEXT, ts INTEGER, ccy TEXT, chg TEXT, bal TEXT,
                  tip TEXT, alt_tip TEXT, fee TEXT, inst TEXT, ord TEXT, defter TEXT, PRIMARY KEY (hesap, kimlik))""")
    db.executemany("INSERT OR REPLACE INTO _defter VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   [(s.kimlik, s.hesap, s.ts, s.ccy, str(s.chg), str(s.bal), s.tip, s.alt_tip, str(s.fee), s.inst,
                     s.ord, s.defter) for s in satirlar])
    db.commit()


def dolar_doldur(db, fiyatci, en_cok: int = 500) -> int:
    """`dolar` alanı boş satırlara o anın fiyatı; fiyat yoksa NULL kalır (uydurulmaz)."""
    from datetime import datetime
    n = 0
    for r in db.execute("SELECT id, zaman, varlik, miktar FROM hareket WHERE dolar IS NULL LIMIT ?", (en_cok,)).fetchall():
        ts = int(datetime.fromisoformat(r["zaman"].replace("Z", "+00:00")).timestamp() * 1000)
        f = fiyatci.dolar(r["varlik"], ts)
        if f is not None:
            db.execute("UPDATE hareket SET dolar=? WHERE id=?", (str((Decimal(r["miktar"]) * f).quantize(Decimal("0.0001"))), r["id"]))
            n += 1
    db.commit()
    return n
