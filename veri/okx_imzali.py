"""OKX TR'nin kendi imzalı okuma uçları (ATK'da olmayanlar). Yalnız GET, yalnız izinli uçlar."""
import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from veri import hiz
from veri.ayar import OkxKimlik
from veri.kayit import cagri_kaydi

# Bilerek kısa: burada olmayan hiçbir uç çağrılamaz. Hepsi okuma ucu.
IZINLI_UCLAR = frozenset({
    "/api/v5/asset/withdrawal-history",
    "/api/v5/asset/deposit-history",
    "/api/v5/asset/bills",
    "/api/v5/asset/balances",
    "/api/v5/account/balance",
})


class OkxHata(Exception):
    def __init__(self, kod: str, mesaj: str = ""):
        super().__init__(f"OKX {kod} {mesaj}".strip())
        self.kod = kod


def zaman_damgasi(an: datetime | None = None) -> str:
    an = (an or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return an.strftime("%Y-%m-%dT%H:%M:%S.") + f"{an.microsecond // 1000:03d}Z"


def imza(secret: str, zaman: str, yontem: str, yol: str, govde: str = "") -> str:
    mac = hmac.new(secret.encode(), (zaman + yontem.upper() + yol + govde).encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


class OkxTr:
    def __init__(self, kimlik: OkxKimlik, db=None, oturum: str | None = None, oturum_http=None):
        self.k = kimlik
        self.db = db
        self.oturum = oturum
        self.http = oturum_http or requests.Session()

    def _istek(self, yol: str, parametreler: dict) -> list[dict]:
        if yol not in IZINLI_UCLAR:
            raise PermissionError(f"izinli olmayan uç: {yol}")
        sorgu = urlencode({k: v for k, v in parametreler.items() if v not in (None, "")})
        tam_yol = yol + (f"?{sorgu}" if sorgu else "")
        for deneme in (1, 2):
            hiz.OKX.bekle()
            ts = zaman_damgasi()
            basliklar = {
                "OK-ACCESS-KEY": self.k.api_key,
                "OK-ACCESS-SIGN": imza(self.k.secret_key, ts, "GET", tam_yol),
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self.k.passphrase,
                "Content-Type": "application/json",
            }
            try:
                r = self.http.get(self.k.taban_url + tam_yol, headers=basliklar, timeout=15)
            except requests.RequestException as e:
                if deneme == 1:
                    time.sleep(3)
                    continue
                raise OkxHata("baglanti", type(e).__name__) from None
            if r.status_code in (429, 502, 503, 504) and deneme == 1:
                time.sleep(3)
                continue
            try:
                govde = r.json()
            except ValueError:
                raise OkxHata(f"http{r.status_code}", "json değil") from None
            kod = str(govde.get("code", ""))
            if kod == "50011" and deneme == 1:      # hız sınırı
                time.sleep(3)
                continue
            if kod != "0":
                raise OkxHata(kod or f"http{r.status_code}", str(govde.get("msg", ""))[:120])
            veri = govde.get("data")
            if not isinstance(veri, list):
                raise OkxHata("bicim", "data liste değil")
            return veri
        raise OkxHata("tekrar", "iki deneme başarısız")

    def oku(self, yol: str, parametreler: dict | None = None, alanlar: list[str] | None = None) -> list[dict]:
        parametreler = parametreler or {}
        with cagri_kaydi(self.db, "OKX TR", f"GET {yol}", parametreler, self.oturum) as c:
            try:
                veri = self._istek(yol, parametreler)
            except OkxHata as e:
                c.kod = e.kod
                raise
            c.satir = len(veri)
            c.alanlar = alanlar or sorted({k for satir in veri[:5] for k in satir})
            return veri

    def sayfala(self, yol: str, parametreler: dict | None = None, alanlar=None, zaman_alani: str = "ts",
                limit: int = 100, en_cok_sayfa: int = 50) -> list[dict]:
        """`after` (daha eski) ile geriye doğru sayfalar; sonuç en yeniden eskiye."""
        hepsi, after = [], None
        for _ in range(en_cok_sayfa):
            p = dict(parametreler or {}, limit=str(limit))
            if after:
                p["after"] = after
            sayfa = self.oku(yol, p, alanlar)
            hepsi.extend(sayfa)
            if len(sayfa) < limit:
                break
            after = min(int(s[zaman_alani]) for s in sayfa)
        return hepsi
