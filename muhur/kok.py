"""Günlük defter kökü: satır satır, tuzlu yapraklar, Merkle, önceki güne zincirli.

Sabit kurallar (değiştirilirse eski kökler yeniden üretilemez):
- Gün: Europe/Istanbul günü. Türkiye 2016'dan beri sürekli UTC+3; gün = [önceki gün 21:00Z, gün 21:00Z).
- Satır sırası: (zaman, ham_kimlik).
- Kanonik satır: ALANLAR'daki alanlar, anahtar sırasıyla, boşluksuz JSON (UTF-8); `id` dahil değil.
  Tutarlar (miktar, dolar) ondalık metin: üssüz, sondaki sıfırlar atılmış, "-0" yerine "0".
- Yaprak = sha256(tuz || kanonik_satır). Tuz satır başına 32 rastgele bayt, ham_kimlik ile eşlenir,
  yalnız yerelde saklanır, bir kez üretilir.
- Merkle: ikili sha256(sol || sağ); tek kalan düğüm bir üst seviyeye olduğu gibi çıkar. Boş gün = 32 sıfır bayt.
- Zincirli kök = sha256(merkle || önceki_kök); önceki kök zincirdeki son mühür (yoksa 32 sıfır bayt).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ALANLAR = ("zaman", "kaynak", "hesap", "adres_id", "ag", "varlik", "miktar", "dolar", "tur",
           "islem_kimligi", "karsi", "supheli", "durum", "kaynak_okuma", "ham_kimlik")
ONDALIK_ALANLAR = ("miktar", "dolar")
SIFIR = bytes(32)


def _sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def ondalik(deger) -> str | None:
    if deger is None:
        return None
    try:
        d = Decimal(str(deger))
    except InvalidOperation as e:
        raise ValueError(f"ondalık değil: {deger!r}") from e
    if not d.is_finite():
        raise ValueError(f"ondalık değil: {deger!r}")
    metin = format(d.normalize(), "f")
    return "0" if metin == "-0" else metin


def kanonik(satir: dict) -> str:
    nesne = {}
    for alan in ALANLAR:
        deger = satir.get(alan)
        nesne[alan] = ondalik(deger) if alan in ONDALIK_ALANLAR else deger
    return json.dumps(nesne, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def gun_sayi(gun: str) -> int:
    return int(date.fromisoformat(gun).strftime("%Y%m%d"))


def gun_satirlari(db: sqlite3.Connection, gun: str) -> list[dict]:
    g = date.fromisoformat(gun)
    bas = f"{(g - timedelta(days=1)).isoformat()}T21:00:00"
    son = f"{g.isoformat()}T21:00:00"
    db.row_factory = sqlite3.Row
    satirlar = [dict(r) for r in db.execute(
        "SELECT * FROM hareket WHERE zaman >= ? AND zaman < ?", (bas, son))]
    return sorted(satirlar, key=lambda s: (s["zaman"], s["ham_kimlik"]))


def tuzlari_hazirla(yol: Path, kimlikler) -> dict[str, bytes]:
    yol = Path(yol)
    kayit = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
    eksik = [k for k in kimlikler if k not in kayit]
    for k in eksik:
        kayit[k] = secrets.token_bytes(32).hex()
    if eksik or not yol.exists():
        yol.parent.mkdir(parents=True, exist_ok=True)
        fd, gecici = tempfile.mkstemp(dir=yol.parent, prefix=".tuz-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(kayit, f, sort_keys=True)
        os.chmod(gecici, 0o600)
        os.replace(gecici, yol)
    return {k: bytes.fromhex(v) for k, v in kayit.items()}


def yaprak(tuz: bytes, satir: dict) -> bytes:
    return _sha(tuz + kanonik(satir).encode("utf-8"))


def _ust_seviye(seviye: list[bytes]) -> list[bytes]:
    ust = [_sha(seviye[i] + seviye[i + 1]) for i in range(0, len(seviye) - 1, 2)]
    if len(seviye) % 2:
        ust.append(seviye[-1])
    return ust


def merkle(yapraklar: list[bytes]) -> bytes:
    if not yapraklar:
        return SIFIR
    seviye = list(yapraklar)
    while len(seviye) > 1:
        seviye = _ust_seviye(seviye)
    return seviye[0]


def kanit(yapraklar: list[bytes], i: int) -> list[tuple[str, bytes]]:
    adimlar = []
    seviye = list(yapraklar)
    while len(seviye) > 1:
        kardes = i ^ 1
        if kardes < len(seviye):
            adimlar.append(("sol" if kardes < i else "sag", seviye[kardes]))
        seviye = _ust_seviye(seviye)
        i //= 2
    return adimlar


def kanit_dogrula(yaprak_: bytes, adimlar, kok_: bytes) -> bool:
    h = yaprak_
    for yon, kardes in adimlar:
        h = _sha(kardes + h) if yon == "sol" else _sha(h + kardes)
    return h == kok_


def gun_koku(satirlar: list[dict], tuz_yolu: Path, onceki: bytes) -> dict:
    tuzlar = tuzlari_hazirla(tuz_yolu, [s["ham_kimlik"] for s in satirlar])
    yapraklar = [yaprak(tuzlar[s["ham_kimlik"]], s) for s in satirlar]
    m = merkle(yapraklar)
    return {
        "merkle": m,
        "kok": _sha(m + onceki),
        "onceki": onceki,
        "yaprak_sayisi": len(yapraklar),
        "kanitlar": {s["ham_kimlik"]: kanit(yapraklar, i) for i, s in enumerate(satirlar)},
    }


def seal_cagri_verisi(agent_id: int, gun: int, kok_: bytes) -> bytes:
    from eth_abi import encode
    from eth_utils import keccak
    return keccak(text="seal(uint256,uint32,bytes32)")[:4] + encode(["uint256", "uint32", "bytes32"],
                                                                     [agent_id, gun, kok_])


def muhur_yaz(db: sqlite3.Connection, kayit: dict) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS muhur (
        gun TEXT, kok TEXT, onceki_kok TEXT, islem_kimligi TEXT,
        agent_id TEXT, ag TEXT, sozlesme TEXT, zaman TEXT)""")
    zaman = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    db.execute("INSERT INTO muhur VALUES (?,?,?,?,?,?,?,?)",
               (kayit["gun"], kayit["kok"], kayit["onceki_kok"], kayit["islem_kimligi"],
                kayit["agent_id"], kayit["ag"], kayit["sozlesme"], zaman))
    db.commit()
