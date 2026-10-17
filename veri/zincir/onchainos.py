"""OnchainOS (OKX'in kendi zincir aracı): adres işlem geçmişi ve bakiye. İmza OKX v5 ile aynı. Yalnız GET.

Ücretsiz kota aşılırsa durur; x402 ile otomatik ödeme KURULMAZ.
"""
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

import requests

from veri import ayar, hiz
from veri.aglar import Ag
from veri.kayit import cagri_kaydi
from veri.okx_imzali import imza, zaman_damgasi
from veri.zincir.evm import Bacak, Bacaklar, Meta, _d

TABAN = "https://web3.okx.com"
IZINLI = frozenset({
    "/api/v6/dex/post-transaction/transactions-by-address",
    "/api/v6/dex/balance/all-token-balances-by-address",
    "/api/v6/dex/balance/supported/chain",
})
ALTI_AY_MS = 183 * 24 * 3600 * 1000


class KotaDoldu(IOError):        # okuyucu bunu yakalar ve OnchainOS'u o koşu boyunca kapatır
    pass


class OnchainOS:
    def __init__(self, db=None, oturum: str | None = None, http=None):
        self.db = db
        self.oturum = oturum
        self.http = http or requests.Session()

    @property
    def hazir(self) -> bool:
        return not ayar.eksikler(["ONCHAINOS_API_KEY", "ONCHAINOS_SECRET_KEY", "ONCHAINOS_PASSPHRASE"])

    def _get(self, yol: str, params: dict) -> list:
        if yol not in IZINLI:
            raise PermissionError(yol)
        sorgu = urlencode({k: v for k, v in params.items() if v not in (None, "")})
        tam = yol + (f"?{sorgu}" if sorgu else "")
        ts = zaman_damgasi()
        basliklar = {"OK-ACCESS-KEY": ayar.al("ONCHAINOS_API_KEY"),
                     "OK-ACCESS-SIGN": imza(ayar.al("ONCHAINOS_SECRET_KEY"), ts, "GET", tam),
                     "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": ayar.al("ONCHAINOS_PASSPHRASE")}
        if ayar.al("ONCHAINOS_PROJECT_ID"):
            basliklar["OK-ACCESS-PROJECT"] = ayar.al("ONCHAINOS_PROJECT_ID")
        with cagri_kaydi(self.db, "OnchainOS", f"GET {yol}", params, self.oturum) as c:
            hiz.GENEL.bekle()
            r = self.http.get(TABAN + tam, headers=basliklar, timeout=20)
            c.kod = str(r.status_code)
            try:
                j = r.json()
            except ValueError:
                c.sonuc = "hata"
                raise IOError(f"OnchainOS http{r.status_code}")
            kod = str(j.get("code", ""))
            if r.status_code == 402 or kod in ("50011", "50061") or "quota" in str(j.get("msg", "")).lower():
                c.sonuc, c.kod = "hata", "kota"
                raise KotaDoldu(str(j.get("msg", ""))[:80])
            if kod != "0":
                c.sonuc, c.kod = "hata", kod or c.kod
                raise IOError(f"OnchainOS {kod} {str(j.get('msg', ''))[:80]}")
            veri = j.get("data") or []
            c.satir = len(veri)
            c.alanlar = ["txHash", "txTime", "from", "to", "amount", "symbol", "txFee", "txStatus", "hitBlacklist", "tokenContractAddress"]
            return veri

    def desteklenen_aglar(self) -> list[dict]:
        return self._get("/api/v6/dex/balance/supported/chain", {})

    def islemler(self, adres: str, ag: Ag, en_cok_sayfa: int = 10) -> Bacaklar:
        """Tek ağ, 6 ay geriye. Belge 'address' / 'addresses' arasında tutarsız: ikisi de denenir."""
        satirlar, cursor = [], None
        bas = int(datetime.now(timezone.utc).timestamp() * 1000) - ALTI_AY_MS
        for anahtar in ("address", "addresses"):
            try:
                for _ in range(en_cok_sayfa):
                    veri = self._get("/api/v6/dex/post-transaction/transactions-by-address",
                                     {anahtar: adres, "chains": ag.onchainos, "limit": 20, "begin": bas, "cursor": cursor})
                    sayfa = veri[0] if veri else {}
                    satirlar.extend(sayfa.get("transactionList") or sayfa.get("transactions") or [])
                    cursor = sayfa.get("cursor")
                    if not cursor:
                        break
                break
            except IOError:
                if anahtar == "addresses":
                    raise
                satirlar, cursor = [], None
        b = cevir(adres, ag, satirlar)
        b.kaynak = "onchainos"
        return b


def _adres(alan) -> str:
    if isinstance(alan, list):
        return str((alan[0] or {}).get("address", "")).lower() if alan else ""
    return str(alan or "").lower()


def cevir(adres: str, ag: Ag, satirlar: list[dict]) -> Bacaklar:
    """OnchainOS satırları → bacaklar. iType: 0 yerel, 1 iç, 2 token."""
    a = adres.lower()
    b = Bacaklar()
    for r in satirlar:
        tx, ts = str(r.get("txHash", "")).lower(), str(r.get("txTime", ""))
        miktar = _d(r.get("amount"))
        if not tx or not ts.isdigit() or miktar is None:
            continue
        kimden, kime = _adres(r.get("from")), _adres(r.get("to"))
        basarili = str(r.get("txStatus", "success")).lower() in ("success", "1")
        ucret = _d(r.get("txFee")) or Decimal(0)
        itype = str(r.get("itype", r.get("iType", "0")))      # gerçek cevapta küçük harf: itype (0 yerel, 1 iç, 2 token)
        if itype == "0" and tx not in b.meta:
            b.meta[tx] = Meta(tx, int(ts), kimden, kime, ucret if kimden == a else Decimal(0), str(r.get("methodId") or ""), basarili)
        if basarili and miktar > 0 and a in (kimden, kime) and kimden != kime:
            sozlesme = str(r.get("tokenContractAddress") or "").lower() or None
            b.append(Bacak(tx, int(ts), kimden, kime, str(r.get("symbol") or (ag.yerel if not sozlesme else "?")), miktar,
                           sozlesme if itype == "2" else None,
                           "kara liste" if str(r.get("hitBlacklist", "")).lower() == "true" else ""))
    return b
