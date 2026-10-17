"""EVM tek okuyucu: Etherscan biçimini konuşan gezgin API'leri (Etherscan V2, Routescan) + ağ tablosu.

Çıktı “bacak”lardır: adrese giren ya da adresten çıkan tek varlık hareketi. İşlemin kendisi (başlatan, ücret,
işlev) ayrıca `meta`da tutulur; çözücü ikisini işlem kimliğiyle birleştirir.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import requests

from veri import ayar, hiz
from veri.aglar import Ag
from veri.kayit import cagri_kaydi

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
ROUTESCAN = "https://api.routescan.io/v2/network/mainnet/evm/{zincir}/etherscan/api"
ROUTESCAN_ZINCIR = {1, 43114, 88888}
EYLEMLER = ("txlist", "txlistinternal", "tokentx")


@dataclass
class Bacak:
    tx: str
    ts: int                 # ms
    kimden: str
    kime: str
    varlik: str
    miktar: Decimal         # ≥ 0
    sozlesme: str | None    # yerel coin için None
    token_adi: str = ""


@dataclass
class Meta:
    tx: str
    ts: int
    baslatan: str
    hedef: str
    ucret: Decimal
    islev: str
    basarili: bool


class Bacaklar(list):
    """Bacak listesi + işlem bilgisi (tx → Meta)."""

    def __init__(self, *a):
        super().__init__(*a)
        self.meta: dict[str, Meta] = {}
        self.kaynak = ""


def _d(x) -> Decimal | None:
    try:
        d = Decimal(str(x))
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def bacaklar(adres: str, ag: Ag, veri: dict) -> Bacaklar:
    """veri: {"txlist": [...], "txlistinternal": [...], "tokentx": [...]} (Etherscan biçimi). Bozuk satır atlanır."""
    a = adres.lower()
    sonuc = Bacaklar()
    on18 = Decimal(10) ** 18
    for r in veri.get("txlist", []):
        ts, deger = str(r.get("timeStamp", "")), _d(r.get("value"))
        if not ts.isdigit() or deger is None or not r.get("hash"):
            continue
        tx, kimden, kime = r["hash"].lower(), str(r.get("from", "")).lower(), str(r.get("to", "")).lower()
        basarili = str(r.get("isError", "0")) == "0" and str(r.get("txreceipt_status", "1")) != "0"
        ucret = (_d(r.get("gasUsed")) or 0) * (_d(r.get("gasPrice")) or 0) / on18 if kimden == a else Decimal(0)
        sonuc.meta[tx] = Meta(tx, int(ts) * 1000, kimden, kime, ucret, str(r.get("functionName") or "").split("(")[0], basarili)
        if basarili and deger > 0 and a in (kimden, kime) and kimden != kime:
            sonuc.append(Bacak(tx, int(ts) * 1000, kimden, kime, ag.yerel, deger / on18, None))
    for r in veri.get("txlistinternal", []):
        ts, deger = str(r.get("timeStamp", "")), _d(r.get("value"))
        if not ts.isdigit() or deger is None or str(r.get("isError", "0")) != "0":
            continue
        kimden, kime = str(r.get("from", "")).lower(), str(r.get("to", "")).lower()
        if deger > 0 and a in (kimden, kime) and kimden != kime:
            sonuc.append(Bacak(str(r.get("hash", "")).lower(), int(ts) * 1000, kimden, kime, ag.yerel, deger / on18, None))
    for r in veri.get("tokentx", []):
        ts, deger, ond = str(r.get("timeStamp", "")), _d(r.get("value")), str(r.get("tokenDecimal", ""))
        if not ts.isdigit() or deger is None or not ond.isdigit() or not r.get("hash"):
            continue
        kimden, kime = str(r.get("from", "")).lower(), str(r.get("to", "")).lower()
        if a in (kimden, kime) and kimden != kime:
            sonuc.append(Bacak(r["hash"].lower(), int(ts) * 1000, kimden, kime, str(r.get("tokenSymbol") or "?"),
                               deger / (Decimal(10) ** int(ond)), str(r.get("contractAddress") or "").lower(),
                               str(r.get("tokenName") or "")))
    return sonuc


class GezginApi:
    """Etherscan biçimli API. Etherscan V2 anahtar ister; Routescan anahtarsız (1, 43114, 88888)."""

    def __init__(self, tur: str, db=None, oturum: str | None = None, http=None):
        assert tur in ("etherscan", "routescan")
        self.tur = tur
        self.db = db
        self.oturum = oturum
        self.http = http or requests.Session()

    def destekler(self, ag: Ag) -> bool:
        if not ag.evm_zincir:
            return False
        if self.tur == "etherscan":
            return bool(ayar.al("ETHERSCAN_API_KEY")) and ag.evm_zincir in (1, 137, 42161)
        return ag.evm_zincir in ROUTESCAN_ZINCIR

    def _get(self, ag: Ag, params: dict):
        if self.tur == "etherscan":
            url, p = ETHERSCAN_V2, dict(params, chainid=ag.evm_zincir, apikey=ayar.al("ETHERSCAN_API_KEY"))
            sinir = hiz.ETHERSCAN
        else:
            url, p, sinir = ROUTESCAN.format(zincir=ag.evm_zincir), dict(params), hiz.GENEL
        ad = f"{'Etherscan V2' if self.tur == 'etherscan' else 'Routescan'} {ag.ad} {params.get('action')}"
        with cagri_kaydi(self.db, "zincir", ad, params, self.oturum) as c:
            for deneme in (1, 2):
                sinir.bekle()
                r = self.http.get(url, params=p, timeout=25)
                c.kod = str(r.status_code)
                try:
                    j = r.json()
                except ValueError:
                    j = {}
                sonuc = j.get("result")
                if isinstance(sonuc, list) or (j.get("status") == "1"):
                    c.satir = len(sonuc) if isinstance(sonuc, list) else 1
                    c.alanlar = ["hash", "timeStamp", "from", "to", "value", "gasUsed", "gasPrice", "functionName",
                                 "tokenSymbol", "tokenDecimal", "contractAddress"] if params.get("action") != "balance" else ["result"]
                    return sonuc
                mesaj = str(j.get("message", "")) + str(sonuc or "")
                if "No transactions found" in mesaj:
                    c.satir = 0
                    return []
                if deneme == 1 and ("rate" in mesaj.lower() or r.status_code in (429, 502, 503)):
                    import time
                    time.sleep(2)
                    continue
                c.sonuc = "hata"
                c.kod = (mesaj[:40] or c.kod)
                raise IOError(f"{ad}: {mesaj[:80]}")
        raise IOError(ad)

    def islemler(self, adres: str, ag: Ag, sayfa_boyu: int = 1000, en_cok_sayfa: int = 10) -> Bacaklar:
        """Sayfa sayfa okur (gezginler sayfa başına en çok 1000 satır, toplam 10.000 verir)."""
        veri = {}
        for eylem in EYLEMLER:
            veri[eylem] = []
            for sayfa in range(1, en_cok_sayfa + 1):
                satirlar = self._get(ag, {"module": "account", "action": eylem, "address": adres.lower(), "startblock": 0,
                                          "endblock": 99999999, "sort": "asc", "page": sayfa, "offset": sayfa_boyu})
                veri[eylem].extend(satirlar or [])
                if not satirlar or len(satirlar) < sayfa_boyu:
                    break
        b = bacaklar(adres, ag, veri)
        b.kaynak = self.tur
        return b

    def bakiye(self, adres: str, ag: Ag) -> Decimal | None:
        sonuc = self._get(ag, {"module": "account", "action": "balance", "address": adres.lower(), "tag": "latest"})
        d = _d(sonuc)
        return None if d is None else d / Decimal(10) ** 18

    def token_bakiye(self, adres: str, ag: Ag, sozlesme: str, ondalik: int) -> Decimal | None:
        sonuc = self._get(ag, {"module": "account", "action": "tokenbalance", "contractaddress": sozlesme,
                               "address": adres.lower(), "tag": "latest"})
        d = _d(sonuc)
        return None if d is None else d / Decimal(10) ** ondalik
