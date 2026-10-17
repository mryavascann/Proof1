"""Dolar fiyatı: OKX'te işlem görenler için mum geçmişi (ATK market_get_candles). Fiyat yoksa None."""
import time
from decimal import Decimal

from veri.atk import Atk, AtkHata, satirlar

SABIT = {"USDT": Decimal(1)}           # dolar karşılığı USDT ile ölçülür
SAAT_MS = 3_600_000


class Fiyatci:
    def __init__(self, atk: Atk, db=None):
        self.atk = atk
        self.db = db
        self._bellek: dict[tuple[str, int], Decimal | None] = {}
        self._lh: dict[tuple[str, int], tuple[Decimal, Decimal]] = {}
        self._liste: set | None = None
        if db is not None:
            db.execute("CREATE TABLE IF NOT EXISTS _fiyat (cift TEXT, saat_ms INTEGER, fiyat TEXT, PRIMARY KEY (cift, saat_ms))")

    def _onbellek(self, cift: str, saat: int):
        if (cift, saat) in self._bellek:
            return True, self._bellek[(cift, saat)]
        if self.db is not None:
            r = self.db.execute("SELECT fiyat FROM _fiyat WHERE cift=? AND saat_ms=?", (cift, saat)).fetchone()
            if r:
                return True, (Decimal(r[0]) if r[0] is not None else None)
        return False, None

    def _yaz(self, cift: str, saat: int, fiyat: Decimal | None):
        self._bellek[(cift, saat)] = fiyat
        if self.db is not None:
            self.db.execute("INSERT OR REPLACE INTO _fiyat VALUES (?,?,?)", (cift, saat, None if fiyat is None else str(fiyat)))
            self.db.commit()

    def mum(self, cift: str, ts_ms: int, bar: str = "1H") -> Decimal | None:
        """ts'yi içeren mumun (1H, 1D ya da 1m) kapanışı. Kaçırılan istekte 100 mum birden önbelleğe alınır."""
        aralik = {"1H": SAAT_MS, "1D": 24 * SAAT_MS, "1m": 60_000}[bar]
        saat = int(ts_ms) // aralik * aralik
        if bar == "1D":
            saat = (int(ts_ms) + 8 * SAAT_MS) // aralik * aralik - 8 * SAAT_MS   # OKX günlük mumu UTC+8 00:00'da açılır
        anahtar = cift if bar == "1H" else f"{cift}@{bar}"
        var, f = self._onbellek(anahtar, saat)
        if var:
            return f
        try:
            veri = self.atk.cagir("market_get_candles", {"instId": cift, "bar": bar, "after": str(saat + aralik), "limit": 100},
                                  alanlar=["ts", "c"])
        except AtkHata:
            self._yaz(anahtar, saat, None)
            return None
        f = None
        for m in satirlar(veri):
            # OKX mumu: [ts, o, h, l, c, ...] ya da {"ts":..,"c":..}
            ts, kapanis = (m[0], m[4]) if isinstance(m, list) else (m.get("ts"), m.get("c") or m.get("close"))
            if ts is None or kapanis is None:
                continue
            if int(ts) == saat:
                f = Decimal(str(kapanis))
            elif (anahtar, int(ts)) not in self._bellek:
                self._yaz(anahtar, int(ts), Decimal(str(kapanis)))
        self._yaz(anahtar, saat, f)
        return f

    def listede(self, ccy: str) -> bool:
        """OKX TR'de ccy-USDT spot çifti var mı (bir kez okunur)."""
        if self._liste is None:
            try:
                self._liste = {r.get("instId") for r in satirlar(self.atk.cagir("market_get_instruments", {"instType": "SPOT"},
                                                                                   alanlar=["instId"]))}
            except AtkHata:
                self._liste = set()
        return f"{ccy}-USDT" in self._liste

    def aralik(self, cift: str, ts_ms: int) -> tuple[Decimal, Decimal] | None:
        """ts'yi içeren 1 dakikalık mumun (en düşük, en yüksek) fiyatı."""
        dk = int(ts_ms) // 60_000 * 60_000
        anahtar = f"{cift}@1m:lh"
        if (anahtar, dk) in self._lh:
            return self._lh[(anahtar, dk)]
        if self.db is not None:
            r = self.db.execute("SELECT fiyat FROM _fiyat WHERE cift=? AND saat_ms=?", (anahtar, dk)).fetchone()
            if r:
                self._lh[(anahtar, dk)] = tuple(Decimal(x) for x in r[0].split("|")) if r[0] else None
                return self._lh[(anahtar, dk)]
        try:
            veri = self.atk.cagir("market_get_candles", {"instId": cift, "bar": "1m", "after": str(dk + 60_000), "limit": 1},
                                  alanlar=["ts", "h", "l"])
        except AtkHata:
            veri = []
        sonuc = None
        for m in satirlar(veri):
            ts, h, l = (m[0], m[2], m[3]) if isinstance(m, list) else (m.get("ts"), m.get("h"), m.get("l"))
            if ts is not None and int(ts) == dk:
                sonuc = (Decimal(str(l)), Decimal(str(h)))
        self._lh[(anahtar, dk)] = sonuc
        if self.db is not None:
            self.db.execute("INSERT OR REPLACE INTO _fiyat VALUES (?,?,?)", (anahtar, dk, f"{sonuc[0]}|{sonuc[1]}" if sonuc else None))
            self.db.commit()
        return sonuc

    def dolar(self, ccy: str, ts_ms: int) -> Decimal | None:
        if ccy in SABIT:
            return SABIT[ccy]
        bar = "1D" if time.time() * 1000 - int(ts_ms) > 7 * 24 * SAAT_MS else "1H"
        if ccy == "TRY":
            p = self.mum("USDT-TRY", ts_ms, bar)
            return (Decimal(1) / p) if p else None
        if not self.listede(ccy):
            return None                       # OKX'te fiyatı yok: uydurulmaz
        return self.mum(f"{ccy}-USDT", ts_ms, bar)

    def try_(self, ccy: str, ts_ms: int) -> Decimal | None:
        if ccy == "TRY":
            return Decimal(1)
        return self.mum(f"{ccy}-TRY", ts_ms)
