"""Zincir okuyucu: ağın okuyucularını sırayla dener (OnchainOS → Etherscan → Routescan → TronGrid).

Hiçbiri okuyamazsa `Okunamadi` yükselir; çağıran adresi “bu ağda yalnız çekimi görüyorum” diye işaretler.
Ham cevaplar `_zincir_ham` tablosunda önbelleklenir (aynı adres kısa sürede yeniden okunmaz).
"""
import json
import time

from veri.aglar import Ag
from veri.zincir.evm import Bacak, Bacaklar, GezginApi, Meta

ONBELLEK_SN = 15 * 60


class Okunamadi(Exception):
    def __init__(self, ag: Ag, denenen: list[str]):
        super().__init__(f"{ag.ad}: okunamadı ({', '.join(denenen) or 'okuyucu yok'})")
        self.ag = ag
        self.denenen = denenen


class ZincirOkuyucu:
    def __init__(self, db=None, oturum: str | None = None, onbellek: bool = True):
        self.db = db
        self.oturum = oturum
        self.onbellek = onbellek
        self.gezginler = {t: GezginApi(t, db, oturum) for t in ("etherscan", "routescan")}
        self._onchainos = None
        self._tron = None
        if db is not None:
            db.execute("CREATE TABLE IF NOT EXISTS _zincir_ham (adres TEXT, ag TEXT, kaynak TEXT, zaman REAL, veri TEXT,"
                       " PRIMARY KEY (adres, ag))")

    @property
    def onchainos(self):
        if self._onchainos is None:
            from veri.zincir.onchainos import OnchainOS
            self._onchainos = OnchainOS(self.db, self.oturum)
        return self._onchainos

    @property
    def tron(self):
        if self._tron is None:
            from veri.zincir.tron import TronGrid
            self._tron = TronGrid(self.db, self.oturum)
        return self._tron

    # --- önbellek ---
    def _bellek(self, adres: str, ag: Ag) -> Bacaklar | None:
        if self.db is None:
            return None
        r = self.db.execute("SELECT kaynak, zaman, veri FROM _zincir_ham WHERE adres=? AND ag=?", (adres.lower(), ag.anahtar)).fetchone()
        if not r or time.time() - r["zaman"] > ONBELLEK_SN:
            return None
        return _ac(json.loads(r["veri"]), r["kaynak"])

    def _sakla(self, adres: str, ag: Ag, b: Bacaklar):
        if self.db is not None:
            self.db.execute("INSERT OR REPLACE INTO _zincir_ham VALUES (?,?,?,?,?)",
                            (adres.lower(), ag.anahtar, b.kaynak, time.time(), json.dumps(_paketle(b))))
            self.db.commit()

    def okuyucular(self, ag: Ag) -> list[str]:
        uygun = []
        for o in ag.okuyucu:
            if o == "onchainos" and self.onchainos.hazir and ag.onchainos:
                uygun.append(o)
            elif o in self.gezginler and self.gezginler[o].destekler(ag):
                uygun.append(o)
            elif o == "trongrid" and ag.anahtar == "tron":
                uygun.append(o)
        return uygun

    def bakiye(self, adres: str, ag: Ag):
        """Yerel coin bakiyesi (2. katman): defterin zincirle kapanış denetimi için. Okunamazsa None."""
        for o in ("etherscan", "routescan"):
            g = self.gezginler[o]
            if g.destekler(ag):
                try:
                    return g.bakiye(adres, ag)
                except (IOError, ValueError):
                    continue
        return None

    def oku(self, adres: str, ag: Ag, onbellek: bool | None = None) -> Bacaklar:
        if self.onbellek if onbellek is None else onbellek:
            b = self._bellek(adres, ag)
            if b is not None:
                return b
        denenen = []
        for o in self.okuyucular(ag):
            denenen.append(o)
            try:
                if o == "onchainos":
                    b = self.onchainos.islemler(adres, ag)
                elif o == "trongrid":
                    b = self.tron.islemler(adres)
                else:
                    b = self.gezginler[o].islemler(adres, ag)
            except (IOError, ValueError, KeyError) as e:      # sonraki okuyucuya geç
                continue
            self._sakla(adres, ag, b)
            return b
        raise Okunamadi(ag, denenen)


def _paketle(b: Bacaklar) -> dict:
    return {"bacak": [[x.tx, x.ts, x.kimden, x.kime, x.varlik, str(x.miktar), x.sozlesme, x.token_adi] for x in b],
            "meta": [[m.tx, m.ts, m.baslatan, m.hedef, str(m.ucret), m.islev, m.basarili] for m in b.meta.values()]}


def _ac(p: dict, kaynak: str) -> Bacaklar:
    from decimal import Decimal
    b = Bacaklar(Bacak(t, ts, f, to, v, Decimal(m), s, ad) for t, ts, f, to, v, m, s, ad in p["bacak"])
    b.meta = {t: Meta(t, ts, ba, h, Decimal(u), i, ok) for t, ts, ba, h, u, i, ok in p["meta"]}
    b.kaynak = kaynak
    return b
