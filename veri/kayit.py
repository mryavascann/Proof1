"""Çağrı kaydı (`cagri` tablosu): OKX kanıt paneli bunu gösterir. Parametreler maskelenir."""
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

GIZLI_ANAHTAR = re.compile(r"(key|secret|pass|sign|token|imza)", re.I)
EVM = re.compile(r"0x[0-9a-fA-F]{40}")
TRON = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
TXID = re.compile(r"0x[0-9a-fA-F]{64}")


def iso(an: datetime) -> str:
    an = an.astimezone(timezone.utc)
    return an.strftime("%Y-%m-%dT%H:%M:%S.") + f"{an.microsecond // 1000:03d}Z"


def ms_iso(ms) -> str:
    return iso(datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc))


def simdi() -> str:
    return iso(datetime.now(timezone.utc))


def kisalt(adres: str) -> str:
    if not adres or len(adres) < 12:
        return adres
    return f"{adres[:6]}…{adres[-4:]}"


def maskele_metin(s: str) -> str:
    s = TXID.sub(lambda m: kisalt(m.group(0)), s)
    s = EVM.sub(lambda m: kisalt(m.group(0)), s)
    return TRON.sub(lambda m: kisalt(m.group(0)), s)


def maskele(parametreler) -> dict:
    temiz = {}
    for k, v in (parametreler or {}).items():
        if GIZLI_ANAHTAR.search(k):
            continue
        if isinstance(v, str):
            temiz[k] = maskele_metin(v)
        elif isinstance(v, (list, tuple)):
            temiz[k] = [maskele_metin(x) if isinstance(x, str) else x for x in v]
        else:
            temiz[k] = v
    return temiz


class Cagri:
    """Bir dış çağrının sonucu; `with cagri_kaydi(...) as c:` içinde doldurulur."""

    def __init__(self):
        self.alanlar: list[str] = []
        self.satir: int | None = None
        self.sonuc = "ok"
        self.kod: str | None = None


@contextmanager
def cagri_kaydi(db: sqlite3.Connection | None, kaynak: str, ad: str, parametreler=None,
                oturum: str | None = None, salt_okunur: bool = True):
    c = Cagri()
    bas = time.perf_counter()
    zaman = simdi()
    try:
        yield c
    except Exception as e:
        c.sonuc = "hata"
        c.kod = c.kod or type(e).__name__
        raise
    finally:
        if db is not None:
            sure = int((time.perf_counter() - bas) * 1000)
            db.execute(
                "INSERT INTO cagri (oturum, zaman, kaynak, ad, parametreler, sure_ms, alanlar, satir, sonuc, kod, salt_okunur)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (oturum, zaman, kaynak, ad, json.dumps(maskele(parametreler), ensure_ascii=False), sure,
                 json.dumps(c.alanlar, ensure_ascii=False), c.satir, c.sonuc, c.kod, int(salt_okunur)))
            db.commit()
