"""Model bütçesi: kullanıcı başına aylık 35 TL sert tavan.

Fiyatlar (USD / milyon parça, Anthropic fiyat tablosu, 17 Ekim 2026'da doğrulandı):
  claude-sonnet-5-5  girdi 2,00 · çıktı 10,00 · önbellek okuma 0,20 · önbellek yazma 2,50
  claude-haiku-5-5   girdi 0,10 · çıktı 0,50 · önbellek okuma 0,01 · önbellek yazma 0,125 (100 bin parçaya kadar)
Kur: PROOF1_USD_TRY (öntanımlı 49,367 — devir notundaki 16 Ekim USDT/TRY).

Seçim: azami maliyetle birlikte harcama geçiş eşiğinin (tavanın %80'i) altında kalıyorsa Sonnet; tavanı aşmıyorsa
Haiku; aşıyorsa kalıp cümle. Tavan hiçbir çağrıyla aşılmaz.
"""
from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

TAVAN_TL = Decimal("35")
GECIS_ORANI = Decimal("0.8")
MILYON = Decimal(1_000_000)

FIYAT = {  # (girdi, çıktı, önbellek okuma, önbellek yazma) USD / milyon parça
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10"), Decimal("0.20"), Decimal("2.50")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50"), Decimal("0.01"), Decimal("0.125")),
}
SONNET, HAIKU, KALIP = "claude-sonnet-5-5", "claude-haiku-5-5", "kalip"


def kur() -> Decimal:
    return Decimal(os.environ.get("PROOF1_USD_TRY", "49.367"))


def tutar_usd(model: str, kullanim: dict) -> Decimal:
    if model not in FIYAT:
        return Decimal(0)
    girdi, cikti, oku, yaz_ = FIYAT[model]
    return (Decimal(kullanim.get("input_tokens", 0)) * girdi
            + Decimal(kullanim.get("output_tokens", 0)) * cikti
            + Decimal(kullanim.get("cache_read_input_tokens", 0) or 0) * oku
            + Decimal(kullanim.get("cache_creation_input_tokens", 0) or 0) * yaz_) / MILYON


def tutar_tl(model: str, kullanim: dict) -> Decimal:
    return tutar_usd(model, kullanim) * kur()


def azami_tl(model: str, girdi_tahmini: int, azami_cikti: int) -> Decimal:
    # Önbellek yazımı en pahalı girdi; azami hesapta tüm girdi önbelleğe yazılıyor sayılır.
    return tutar_tl(model, {"cache_creation_input_tokens": girdi_tahmini, "output_tokens": azami_cikti})


def _tablo(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS butce (
        kullanici TEXT, ay TEXT, model TEXT, girdi_parca INTEGER, cikti_parca INTEGER,
        tutar_tl TEXT, tavan_tl TEXT, durum TEXT)""")


def harcanan(db: sqlite3.Connection, kullanici: str, ay: str) -> Decimal:
    _tabl = db.execute("SELECT 1 FROM sqlite_master WHERE name='butce'").fetchone()
    if not _tabl:
        return Decimal(0)
    return sum((Decimal(r[0]) for r in db.execute(
        "SELECT tutar_tl FROM butce WHERE kullanici=? AND ay=?", (kullanici, ay))), Decimal(0))


def model_sec(db: sqlite3.Connection, kullanici: str, ay: str, girdi_tahmini: int, azami_cikti: int,
              hizli: bool = False) -> str:
    """hizli: Telegram (3 sn) ve çok sayıdaki bant cümlesi için doğrudan Haiku; tavan kuralı aynı."""
    h = harcanan(db, kullanici, ay)
    if not hizli and h + azami_tl(SONNET, girdi_tahmini, azami_cikti) <= TAVAN_TL * GECIS_ORANI:
        return SONNET
    if h + azami_tl(HAIKU, girdi_tahmini, azami_cikti) <= TAVAN_TL:
        return HAIKU
    return KALIP


def yaz(db: sqlite3.Connection, kullanici: str, ay: str, model: str, girdi: int, cikti: int,
        tutar: Decimal, durum: str) -> None:
    _tablo(db)
    db.execute("INSERT INTO butce VALUES (?,?,?,?,?,?,?,?)",
               (kullanici, ay, model, girdi, cikti, format(tutar, "f"), str(TAVAN_TL), durum))
    db.commit()
