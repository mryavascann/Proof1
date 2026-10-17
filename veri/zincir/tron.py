"""Tron okuyucu: TronGrid (anahtarsız). TRC20 aktarımları + yerel TRX aktarımları → bacaklar."""
from decimal import Decimal

import requests

from veri import hiz
from veri.kayit import cagri_kaydi
from veri.zincir.evm import Bacak, Bacaklar, Meta, _d
from veri.zincir.tx import TRONGRID, tron_base58


class TronGrid:
    def __init__(self, db=None, oturum: str | None = None, http=None):
        self.db = db
        self.oturum = oturum
        self.http = http or requests.Session()

    def _get(self, yol: str, params: dict) -> list:
        with cagri_kaydi(self.db, "zincir", f"TronGrid {yol.split('/')[-1] or 'transactions'}", params, self.oturum) as c:
            hiz.GENEL.bekle()
            r = self.http.get(TRONGRID + yol, params=params, timeout=20)
            c.kod = str(r.status_code)
            j = r.json() if r.ok else {}
            if not r.ok or not j.get("success", True):
                c.sonuc = "hata"
                raise IOError(f"TronGrid {r.status_code}")
            veri = j.get("data") or []
            c.satir, c.alanlar = len(veri), ["transaction_id", "block_timestamp", "from", "to", "value", "token_info"]
            return veri

    def islemler(self, adres: str) -> Bacaklar:
        a = adres.lower()
        b = Bacaklar()
        b.kaynak = "trongrid"
        for r in self._get(f"/v1/accounts/{adres}/transactions/trc20", {"limit": 200, "only_confirmed": "true"}):
            bilgi = r.get("token_info") or {}
            deger, ond = _d(r.get("value")), str(bilgi.get("decimals", ""))
            if deger is None or not ond.isdigit():
                continue
            kimden, kime = str(r.get("from", "")).lower(), str(r.get("to", "")).lower()
            if a in (kimden, kime) and kimden != kime:
                b.append(Bacak(str(r.get("transaction_id", "")).lower(), int(r.get("block_timestamp", 0)), kimden, kime,
                               str(bilgi.get("symbol") or "?"), deger / Decimal(10) ** int(ond),
                               str(bilgi.get("address") or "").lower(), str(bilgi.get("name") or "")))
        for r in self._get(f"/v1/accounts/{adres}/transactions", {"limit": 200, "only_confirmed": "true"}):
            try:
                sozlesme = r["raw_data"]["contract"][0]
                deger = sozlesme["parameter"]["value"]
                tx, ts = str(r["txID"]).lower(), int(r["block_timestamp"])
            except (KeyError, IndexError, TypeError):
                continue
            kimden = tron_base58(deger.get("owner_address", "")).lower() if deger.get("owner_address") else ""
            kime = tron_base58(deger["to_address"]).lower() if deger.get("to_address") else ""
            ret = (r.get("ret") or [{}])[0]
            basarili = ret.get("contractRet", "SUCCESS") == "SUCCESS"
            ucret = Decimal(int(ret.get("fee", 0) or r.get("net_fee", 0) or 0) + int(r.get("energy_fee", 0) or 0)) / Decimal(10**6)
            b.meta[tx] = Meta(tx, ts, kimden, kime, ucret if kimden == a else Decimal(0), sozlesme.get("type", ""), basarili)
            if sozlesme.get("type") == "TransferContract" and basarili and a in (kimden, kime) and kimden != kime:
                b.append(Bacak(tx, ts, kimden, kime, "TRX", Decimal(int(deger.get("amount", 0))) / Decimal(10**6), None))
        return b
