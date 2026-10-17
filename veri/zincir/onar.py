"""Arşiv onarımı: gezginin yerel coin defteri zincirdeki bakiyeyle kapanmazsa farkın doğduğu blokları düğümle bulur.

Yöntem: defterin blok blok birikimi, arşiv düğümündeki geçmiş bakiyeyle (eth_getBalance) ikiye bölerek karşılaştırılır.
Ayrılan blokta düğümün kendi işlemlerine ve makbuzlarına bakılır:
  · gezginde olmayan işlem (gönderen ya da alıcı adres) → bacak + ücret eklenir;
  · ücreti makbuzdakinden farklı işlem (gasUsed × effectiveGasPrice) → ücret düzeltilir.
Bunlarla açıklanmayan değişim (ör. iz sürmeden görünmeyen iç işlem) uydurulmaz; `aciklanamayan` olarak kalır.
Yalnız okuma: dört JSON-RPC yöntemi, başka bir şey çağrılmaz.
"""
from dataclasses import dataclass
from decimal import Decimal

import requests

from veri import hiz
from veri.aglar import Ag
from veri.kayit import cagri_kaydi
from veri.zincir.evm import Bacak, Bacaklar, Meta

ARSIV = {   # geçmiş bakiye verebilen (arşiv) düğümler; sırayla denenir
    "chiliz": ("https://rpc.chiliz.com", "https://rpc.ankr.com/chiliz"),
}
IZINLI = frozenset({"eth_blockNumber", "eth_getBalance", "eth_getBlockByNumber", "eth_getTransactionReceipt"})
E18 = Decimal(10) ** 18
SIFIR = Decimal(0)


class CagriSiniri(Exception):
    pass


class Arsiv:
    def __init__(self, ag: Ag, db=None, oturum: str | None = None, http=None, urller=None, en_cok_cagri: int = 800,
                 sinir: hiz.Sinir | None = None):
        self.ag = ag
        self.sinir = sinir or hiz.GENEL
        self.db = db
        self.oturum = oturum
        self.http = http or requests.Session()
        self.urller = tuple(urller if urller is not None else ARSIV.get(ag.anahtar, ()))
        self.en_cok = en_cok_cagri
        self.cagri = 0
        self._bakiye: dict = {}

    @property
    def hazir(self) -> bool:
        return bool(self.urller)

    def _rpc(self, yontem: str, params: list):
        if yontem not in IZINLI:
            raise PermissionError(yontem)
        if self.cagri >= self.en_cok:
            raise CagriSiniri(self.ag.ad)
        self.cagri += 1
        for url in self.urller:
            with cagri_kaydi(self.db, "zincir", f"{self.ag.ad} arşiv {yontem}", {"params": params}, self.oturum) as c:
                self.sinir.bekle()
                try:
                    r = self.http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": yontem, "params": params}, timeout=25)
                    c.kod = str(r.status_code)
                    sonuc = r.json().get("result") if r.ok else None
                except (requests.RequestException, ValueError):
                    sonuc = None
                if sonuc is not None:
                    c.satir, c.alanlar = 1, ["result"]
                    return sonuc
                c.sonuc = "hata"                   # yedek düğüm
        raise IOError(f"{self.ag.ad} arşiv {yontem}")

    def tepe(self) -> int:
        return int(self._rpc("eth_blockNumber", []), 16)

    def bakiye(self, adres: str, blok: int) -> Decimal:
        if blok <= 0:
            return SIFIR                            # başlangıç bloğundan önce bakiye yok
        k = (adres.lower(), blok)
        if k not in self._bakiye:
            self._bakiye[k] = Decimal(int(self._rpc("eth_getBalance", [adres.lower(), hex(blok)]), 16)) / E18
        return self._bakiye[k]

    def blok(self, n: int) -> dict:
        return self._rpc("eth_getBlockByNumber", [hex(n), True])

    def makbuz(self, tx: str) -> dict:
        return self._rpc("eth_getTransactionReceipt", [tx])


@dataclass
class Onarim:
    eksik_islem: int = 0
    ucret_duzeltme: int = 0
    aciklanamayan: Decimal = SIFIR             # düğümde görülen ama işleme bağlanamayan değişim (zincir − defter)
    ilk_fark: Decimal = SIFIR                  # onarımdan önce zincir − defter
    kapandi: bool = False
    cagri: int = 0


def _deltalar(a: str, ag: Ag, b: Bacaklar) -> dict[int, Decimal] | None:
    """Yerel coin defterinin blok başına değişimi; bloğu bilinmeyen satır varsa None."""
    d: dict[int, Decimal] = {}
    for x in b:
        if x.sozlesme is None and x.varlik == ag.yerel and a in (x.kimden, x.kime):
            if not x.blok:
                return None
            d[x.blok] = d.get(x.blok, SIFIR) + (x.miktar if x.kime == a else -x.miktar)
    for m in b.meta.values():
        if m.baslatan == a and m.ucret:
            if not m.blok:
                return None
            d[m.blok] = d.get(m.blok, SIFIR) - m.ucret
    return d


def defter_bakiyesi(adres: str, ag: Ag, b: Bacaklar) -> Decimal:
    """Gezgin verisinden yerel coin bakiyesi: giren − çıkan − ücret (çözücünün işlem başına netiyle aynı toplam)."""
    a = adres.lower()
    giren = sum((x.miktar if x.kime == a else -x.miktar for x in b
                 if x.sozlesme is None and x.varlik == ag.yerel and a in (x.kimden, x.kime)), SIFIR)
    return giren - sum((m.ucret for m in b.meta.values() if m.baslatan == a), SIFIR)


def onar(adres: str, ag: Ag, b: Bacaklar, arsiv: Arsiv, tolerans: Decimal = Decimal("1e-12")) -> Onarim:
    """`b`yi yerinde düzeltir; özet döner. Düğüme ulaşılamazsa IOError (çağıran gezgin verisiyle devam eder)."""
    a = adres.lower()
    o = Onarim()
    d = _deltalar(a, ag, b)
    if d is None or not (d or b.meta):
        return o
    esit = lambda x, y: abs(x - y) <= tolerans
    tepe = arsiv.tepe()
    bal = lambda n: arsiv.bakiye(a, n)
    o.ilk_fark = bal(tepe) - sum(d.values(), SIFIR)
    if esit(o.ilk_fark, SIFIR):
        o.kapandi, o.cagri = True, arsiv.cagri
        return o
    noktalar = [0] + sorted(k for k in d if 0 < k < tepe) + [tepe]
    kum, s = [], SIFIR
    for n in noktalar:
        s += d.get(n, SIFIR)
        kum.append(s)
    try:
        # 1) defterle düğümün ayrıldığı (bilinen blok, sonraki bilinen blok] aralıkları
        araliklar, yigin = [], [(0, len(noktalar) - 1)]
        while yigin:
            i, j = yigin.pop()
            if esit(bal(noktalar[j]) - bal(noktalar[i]), kum[j] - kum[i]):
                continue
            if j == i + 1:
                araliklar.append((noktalar[i], noktalar[j]))
                continue
            k = (i + j) // 2
            yigin += [(k, j), (i, k)]
        # 2) aralıkta değişen bloklar: aradaki (defterde olmayan) bloklar + sondaki bilinen blok
        for lo, hi in sorted(araliklar):
            bilinen = hi in d
            ust = hi - 1 if bilinen else hi
            if ust > lo and not esit(bal(ust), bal(lo)):
                for n in _degisen_bloklar(bal, lo, ust, esit):
                    o.aciklanamayan += _incele(a, ag, b, arsiv, n, SIFIR, o, esit)
            if bilinen and not esit(bal(hi) - bal(hi - 1), d[hi]):
                o.aciklanamayan += _incele(a, ag, b, arsiv, hi, d[hi], o, esit)
    except CagriSiniri:
        pass                                        # bulunan düzeltmeler geçerli; kalanı fark olarak görünür
    o.kapandi = esit(bal(tepe), sum((_deltalar(a, ag, b) or {}).values(), SIFIR))     # tepe bakiyesi önbellekte
    o.cagri = arsiv.cagri
    if o.eksik_islem or o.ucret_duzeltme:
        b.kaynak = f"{b.kaynak}+arşiv" if b.kaynak and "arşiv" not in b.kaynak else (b.kaynak or "arşiv")
    return o


def _degisen_bloklar(bal, lo: int, hi: int, esit) -> list[int]:
    """(lo, hi] içinde bakiyenin değiştiği bloklar (ikiye bölerek; birbirini götüren değişimler görünmez)."""
    sonuc, yigin = [], [(lo, hi)]
    while yigin:
        x, y = yigin.pop()
        if esit(bal(x), bal(y)):
            continue
        if y == x + 1:
            sonuc.append(y)
            continue
        m = (x + y) // 2
        yigin += [(m, y), (x, m)]
    return sorted(sonuc)


def _incele(a: str, ag: Ag, b: Bacaklar, arsiv: Arsiv, n: int, beklenen: Decimal, o: Onarim, esit) -> Decimal:
    """n. bloktaki değişimi düğümün işlemleriyle açıklar; açıklanamayan kısmı döner."""
    gercek = arsiv.bakiye(a, n) - arsiv.bakiye(a, n - 1)
    if esit(gercek, beklenen):
        return SIFIR
    blk = arsiv.blok(n)
    ts = int(blk["timestamp"], 16) * 1000
    eklenen = SIFIR
    for t in blk.get("transactions") or []:
        if not isinstance(t, dict):
            continue
        kimden, kime = str(t.get("from") or "").lower(), str(t.get("to") or "").lower()
        if a not in (kimden, kime):
            continue
        h = str(t["hash"]).lower()
        m = b.meta.get(h)
        deger = Decimal(int(t.get("value") or "0x0", 16)) / E18
        if kimden == a:
            mk = arsiv.makbuz(h)
            fiyat = mk.get("effectiveGasPrice") or t.get("gasPrice") or "0x0"
            ucret = Decimal(int(mk["gasUsed"], 16) * int(fiyat, 16)) / E18
            basarili = int(mk.get("status") or "0x1", 16) == 1
            if m is None:
                b.meta[h] = Meta(h, ts, a, kime, ucret, str(t.get("input") or "")[:10], basarili, n)
                eklenen -= ucret
                if basarili and deger > 0 and kime != a:
                    b.append(Bacak(h, ts, a, kime, ag.yerel, deger, None, blok=n))
                    eklenen -= deger
                o.eksik_islem += 1
            elif m.ucret != ucret:
                eklenen += m.ucret - ucret
                m.ucret = ucret
                o.ucret_duzeltme += 1
        elif kime == a and m is None and deger > 0:
            mk = arsiv.makbuz(h)
            if int(mk.get("status") or "0x1", 16) == 1:
                b.meta[h] = Meta(h, ts, kimden, kime, SIFIR, str(t.get("input") or "")[:10], True, n)
                b.append(Bacak(h, ts, kimden, a, ag.yerel, deger, None, blok=n))
                eklenen += deger
                o.eksik_islem += 1
    return gercek - beklenen - eklenen
