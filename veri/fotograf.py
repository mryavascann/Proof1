"""Sabah fotoğrafı: borsa hesaplarının bakiyesi (salt okuma uçları) ve “benim” cüzdanların defterden seviyesi."""
from decimal import Decimal

from veri.atk import Atk, satirlar
from veri.borsa import ondalik
from veri.okx_imzali import OkxTr


def _topla(hedef: dict, ccy, miktar):
    q = ondalik(miktar)
    if ccy and q:
        hedef[str(ccy)] = hedef.get(str(ccy), Decimal(0)) + q


def _detaylar(veri) -> list[dict]:
    """account/balance cevabı: [{details: [...]}] ya da doğrudan satırlar."""
    sonuc = []
    for r in satirlar(veri) if not isinstance(veri, list) else veri:
        if isinstance(r, dict) and isinstance(r.get("details"), list):
            sonuc.extend(r["details"])
        elif isinstance(r, dict):
            sonuc.append(r)
    return sonuc


def borsa_bakiyeleri(okx_ana: OkxTr | None, atk_alt: Atk | None) -> dict:
    """{'borsa:ana': {ccy: miktar}, 'borsa:alt': {...}} — fonlama + işlem hesabı."""
    yerler = {}
    if okx_ana is not None:
        ana: dict = {}
        for r in okx_ana.oku("/api/v5/asset/balances", alanlar=["ccy", "bal"]):
            _topla(ana, r.get("ccy"), r.get("bal"))
        for d in _detaylar(okx_ana.oku("/api/v5/account/balance", alanlar=["details.ccy", "details.cashBal"])):
            _topla(ana, d.get("ccy"), d.get("cashBal") or d.get("eq"))
        yerler["borsa:ana"] = ana
    if atk_alt is not None:
        alt: dict = {}
        for r in satirlar(atk_alt.cagir("account_get_asset_balance", {}, alanlar=["ccy", "bal"])):
            _topla(alt, r.get("ccy"), r.get("bal"))
        for d in _detaylar(atk_alt.cagir("account_get_balance", {}, alanlar=["details.ccy", "details.cashBal"])):
            _topla(alt, d.get("ccy"), d.get("cashBal") or d.get("eq"))
        yerler["borsa:alt"] = alt
    return yerler


def cuzdan_seviyeleri(db, ts_ms: int | None = None) -> dict:
    """“Benim” adreslerin defterden seviyesi: {'adres:BENIM_1': {varlik: miktar}}."""
    from veri.kopru import _benim, _ms
    ids, _ = _benim(db)
    yerler: dict = {}
    if not ids:
        return yerler
    for r in db.execute(f"SELECT h.zaman, h.varlik, h.miktar, a.etiket FROM hareket h JOIN adres a ON a.id=h.adres_id "
                        f"WHERE h.hesap='cuzdan' AND h.supheli=0 AND h.adres_id IN ({','.join('?' * len(ids))})", tuple(ids)):
        if ts_ms is None or _ms(r["zaman"]) <= ts_ms:
            d = yerler.setdefault(f"adres:{r['etiket']}", {})
            d[r["varlik"]] = d.get(r["varlik"], Decimal(0)) + Decimal(r["miktar"])
    return {y: {v: q for v, q in d.items() if q} for y, d in yerler.items()}
