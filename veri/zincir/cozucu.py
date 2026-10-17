"""Zincir çözücü: her işlemde kullanıcının adresine giren ve çıkan + ağ ücreti → “verdi / aldı / ücret”.

İşlemi başlatana değil, kullanıcının adresine giren ve çıkana bakılır. Tanınmayan giriş tahminle doldurulmaz.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from veri.aglar import Ag
from veri.zincir.evm import Bacaklar

# Taklit edilen tokenların resmi sözleşmeleri (herkese açık adresler).
RESMI = {
    "ethereum": {"USDC": {"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}, "USDT": {"0xdac17f958d2ee523a2206206994597c13d831ec7"}},
    "avalanche": {"USDC": {"0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e"}, "USDT": {"0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7"}},
    "arbitrum": {"USDC": {"0xaf88d065e77c8cc2239327c5edb3a432268e5831", "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8"},
                 "USDT": {"0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"}},
    "polygon": {"USDC": {"0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"},
                "USDT": {"0xc2132d05d31c914a87c6611c10748aeb04b58e8f"}},
    "bnb": {"USDC": {"0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"}, "USDT": {"0x55d398326f99059ff775485246999027b3197955"}},
    "base": {"USDC": {"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"}},
}
ALAN_ADI = re.compile(r"(https?:|www\.|\.com|\.io|\.org|\.net|\.xyz|\.app|t\.me|visit|claim|reward|airdrop)", re.I)


def supheli_token_mu(sembol: str, ad: str, sozlesme: str | None, ag: str) -> bool:
    if sozlesme is None:
        return False
    if any(unicodedata.category(ch) in ("Cf", "Cc", "Mn") or ord(ch) > 127 for ch in sembol):
        return True                                   # görünmez / Latin dışı karakterli taklit
    if ALAN_ADI.search(sembol) or ALAN_ADI.search(ad or ""):
        return True                                   # alan adı isimli token
    resmi = RESMI.get(ag, {}).get(sembol.upper())
    return bool(resmi) and sozlesme.lower() not in resmi


def zehirleme_mi(gonderen: str, bilinen: set[str]) -> bool:
    """İlk ve son 4 karakteri bilinen bir adresle aynı, kendisi farklı adres."""
    g = gonderen.lower()
    if len(g) < 12:
        return False
    for k in bilinen:
        k = k.lower()
        if k != g and len(k) == len(g) and g[2:6] == k[2:6] and g[-4:] == k[-4:]:
            return True
    return False


@dataclass
class Baglam:
    benim: set = field(default_factory=set)
    cekim_tx: set = field(default_factory=set)
    yatirma_tx: set = field(default_factory=set)
    borsa_adresleri: set = field(default_factory=set)
    bilinen: set = field(default_factory=set)          # zehirleme karşılaştırması için

    def __post_init__(self):
        self.benim = {x.lower() for x in self.benim}
        self.bilinen = {x.lower() for x in (self.bilinen or set())} | self.benim | {x.lower() for x in self.borsa_adresleri}


@dataclass
class Olay:
    tx: str
    ts: int
    tur: str
    verdi: dict
    aldi: dict
    ucret: Decimal
    ucret_varlik: str
    karsi: str | None = None          # 'ana' (borsa) ya da None
    karsi_adres: str | None = None
    islev: str = ""
    supheli: bool = False
    neden: str = ""                   # supheli_token | adres_zehirleme | basarisiz
    sahte_varliklar: set = field(default_factory=set)   # yalnız bunların satırları şüpheli (servetten düşülür)


def coz(adres: str, ag: Ag, b: Bacaklar, baglam: Baglam) -> list[Olay]:
    a = adres.lower()
    gruplar: dict[str, list] = {}
    for x in b:
        gruplar.setdefault(x.tx, []).append(x)
    for tx, m in b.meta.items():
        if m.baslatan == a:
            gruplar.setdefault(tx, [])
    olaylar = []
    for tx, bacaklar_ in gruplar.items():
        m = b.meta.get(tx)
        ts = m.ts if m else min(x.ts for x in bacaklar_)
        kullanici = bool(m and m.baslatan == a)
        net: dict[str, Decimal] = {}
        supheli, neden, sahte = False, "", set()
        gonderenler, alicilar = [], []
        for x in bacaklar_:
            yon = 1 if x.kime == a else -1
            net[x.varlik] = net.get(x.varlik, Decimal(0)) + yon * x.miktar
            if yon > 0:
                gonderenler.append(x.kimden)
                if x.token_adi == "kara liste" or supheli_token_mu(x.varlik, x.token_adi, x.sozlesme, ag.anahtar):
                    supheli, neden = True, "supheli_token"
                    sahte.add(x.varlik)
                elif zehirleme_mi(x.kimden, baglam.bilinen):
                    supheli, neden = True, "adres_zehirleme"
            else:
                alicilar.append(x.kime)
        aldi = {k: v for k, v in net.items() if v > 0}
        verdi = {k: -v for k, v in net.items() if v < 0}
        o = Olay(tx, ts, "", verdi, aldi, m.ucret if m else Decimal(0), ag.yerel, islev=m.islev if m else "",
                 supheli=supheli, neden=neden, sahte_varliklar=sahte)
        if m and not m.basarili:
            o.tur, o.verdi, o.aldi, o.neden = "ucret", {}, {}, "basarisiz"
        elif tx in baglam.cekim_tx:
            o.tur, o.karsi = "giris", "ana"
        elif tx in baglam.yatirma_tx:
            o.tur, o.karsi = "gonderim", "ana"
        elif supheli and aldi and not verdi:
            o.tur = "taninmadi"
            o.karsi_adres = gonderenler[0] if gonderenler else None
        elif verdi and aldi:
            o.tur = "takas"
        elif verdi:
            o.tur = "gonderim"
            o.karsi_adres = alicilar[0] if alicilar else (m.hedef if m else None)
        elif aldi:
            g = gonderenler[0] if gonderenler else None
            o.karsi_adres = g
            if kullanici or (g and g in baglam.benim):
                o.tur = "giris"
            elif g and g in {x.lower() for x in baglam.borsa_adresleri}:
                o.tur, o.karsi = "giris", "ana"
            else:
                o.tur = "taninmadi"
        elif kullanici and o.ucret > 0:
            o.tur = "ucret"
        else:
            continue
        olaylar.append(o)
    olaylar.sort(key=lambda o: (o.ts, o.tx))
    return olaylar


def hareketlere(olaylar: list[Olay], adres_id: int, ag: str, kaynak: str, etiketle=None) -> list[dict]:
    """Olay → `hareket` satırları (hesap='cuzdan'). etiketle(adres) → etiket | None."""
    from veri.kayit import ms_iso
    sonuc = []
    for o in olaylar:
        karsi = o.karsi or (etiketle(o.karsi_adres) if (etiketle and o.karsi_adres) else None)
        ortak = {"zaman": ms_iso(o.ts), "kaynak": "zincir", "hesap": "cuzdan", "adres_id": adres_id, "ag": ag,
                 "dolar": None, "islem_kimligi": o.tx, "karsi": karsi, "supheli": 0, "durum": "ok",
                 "kaynak_okuma": kaynak}
        for varlik, m in o.aldi.items():
            sonuc.append(dict(ortak, varlik=varlik, miktar=str(m), tur=o.tur, supheli=int(varlik in o.sahte_varliklar), ham_kimlik=f"zincir:{ag}:{adres_id}:{o.tx}:{varlik}:al"))
        for varlik, m in o.verdi.items():
            sonuc.append(dict(ortak, varlik=varlik, miktar=str(-m), tur=o.tur, supheli=int(varlik in o.sahte_varliklar), ham_kimlik=f"zincir:{ag}:{adres_id}:{o.tx}:{varlik}:ver"))
        if o.ucret > 0:
            sonuc.append(dict(ortak, varlik=o.ucret_varlik, miktar=str(-o.ucret), tur="ucret", karsi=None,
                              ham_kimlik=f"zincir:{ag}:{adres_id}:{o.tx}:ucret"))
    return sonuc
