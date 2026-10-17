"""Tek işlemin göndereni: EVM ağlarında JSON-RPC (gerekirse Routescan vekili), Tron'da TronGrid. Yalnız okuma."""
import hashlib
import json

import requests

from veri import hiz
from veri.aglar import Ag
from veri.kayit import cagri_kaydi

RPC = {
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "polygon": "https://polygon-bor-rpc.publicnode.com",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "base": "https://mainnet.base.org",
    "bnb": "https://bsc-dataseed.binance.org",
    "optimism": "https://mainnet.optimism.io",
}
ROUTESCAN = "https://api.routescan.io/v2/network/mainnet/evm/{zincir}/etherscan/api"
ROUTESCAN_ZINCIR = {1, 43114, 88888}
TRONGRID = "https://api.trongrid.io"
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def tron_base58(hex_adres: str) -> str:
    """'41…' (21 bayt) → 'T…' (base58check)."""
    ham = bytes.fromhex(hex_adres)
    ham += hashlib.sha256(hashlib.sha256(ham).digest()).digest()[:4]
    n = int.from_bytes(ham, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = _B58[r] + s
    return "1" * (len(ham) - len(ham.lstrip(b"\0"))) + s


def tron_hex(base58: str) -> str:
    n = 0
    for ch in base58:
        n = n * 58 + _B58.index(ch)
    ham = n.to_bytes(25, "big")
    govde, sag = ham[:-4], ham[-4:]
    if hashlib.sha256(hashlib.sha256(govde).digest()).digest()[:4] != sag:
        raise ValueError("tron adresi bozuk")
    return govde.hex()


class TxOkuyucu:
    def __init__(self, db=None, oturum: str | None = None, http=None):
        self.db = db
        self.oturum = oturum
        self.http = http or requests.Session()
        if db is not None:
            db.execute("CREATE TABLE IF NOT EXISTS _tx_gonderen (ag TEXT, tx TEXT, gonderen TEXT, PRIMARY KEY (ag, tx))")

    def _bellek(self, ag: str, tx: str):
        if self.db is None:
            return False, None
        r = self.db.execute("SELECT gonderen FROM _tx_gonderen WHERE ag=? AND tx=?", (ag, tx)).fetchone()
        return (True, r[0]) if r else (False, None)

    def _sakla(self, ag: str, tx: str, gonderen: str | None):
        if self.db is not None:
            self.db.execute("INSERT OR REPLACE INTO _tx_gonderen VALUES (?,?,?)", (ag, tx, gonderen))
            self.db.commit()

    def _evm(self, ag: Ag, tx: str) -> str | None:
        if ag.anahtar in RPC:
            url, govde = RPC[ag.anahtar], {"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionByHash", "params": [tx]}
            with cagri_kaydi(self.db, "zincir", f"{ag.ad} RPC eth_getTransactionByHash", {"tx": tx}, self.oturum) as c:
                hiz.GENEL.bekle()
                r = self.http.post(url, json=govde, timeout=15)
                c.kod = str(r.status_code)
                sonuc = r.json().get("result") if r.ok else None
                c.alanlar, c.satir = ["from"], int(bool(sonuc))
                if not r.ok:
                    c.sonuc = "hata"
                return (sonuc or {}).get("from")
        if ag.evm_zincir in ROUTESCAN_ZINCIR:
            p = {"module": "proxy", "action": "eth_getTransactionByHash", "txhash": tx}
            with cagri_kaydi(self.db, "zincir", f"Routescan {ag.ad} eth_getTransactionByHash", p, self.oturum) as c:
                hiz.GENEL.bekle()
                r = self.http.get(ROUTESCAN.format(zincir=ag.evm_zincir), params=p, timeout=15)
                c.kod = str(r.status_code)
                sonuc = r.json().get("result") if r.ok else None
                c.alanlar, c.satir = ["from"], int(isinstance(sonuc, dict))
                return sonuc.get("from") if isinstance(sonuc, dict) else None
        return None

    def _tron(self, tx: str) -> str | None:
        with cagri_kaydi(self.db, "zincir", "TronGrid wallet/gettransactionbyid", {"tx": tx}, self.oturum) as c:
            hiz.GENEL.bekle()
            r = self.http.post(f"{TRONGRID}/wallet/gettransactionbyid", data=json.dumps({"value": tx}), timeout=15)
            c.kod = str(r.status_code)
            try:
                sahip = r.json()["raw_data"]["contract"][0]["parameter"]["value"]["owner_address"]
            except (ValueError, KeyError, IndexError, TypeError):
                c.sonuc = "hata"
                return None
            c.alanlar, c.satir = ["owner_address"], 1
            return tron_base58(sahip)

    def gonderen(self, ag: Ag, tx: str) -> str | None:
        """İşlemin göndereni; okunamazsa None (çağıran 'okunamadı' der)."""
        if not tx:
            return None
        var, g = self._bellek(ag.anahtar, tx)
        if var:
            return g
        try:
            g = self._tron(tx) if ag.anahtar == "tron" else (self._evm(ag, tx) if ag.evm_zincir else None)
        except (requests.RequestException, ValueError):
            g = None
        self._sakla(ag.anahtar, tx, g)
        return g
