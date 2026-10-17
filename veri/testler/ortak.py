"""Test yardımcıları. Canlı testler yalnız CANLI=1 ile çalışır (gerçek hesap, aralıklı istek)."""
import os
import unittest
from pathlib import Path

from veri import ayar

CANLI = os.environ.get("CANLI") == "1"
canli = unittest.skipUnless(CANLI, "canlı test: CANLI=1 ile çalıştır")
FIXTURE = Path(__file__).parent / "fixture"
CANLI_DB = ayar.KOK / "data" / "test_canli.db"
# Devir metnindeki toplamların alındığı an: 11 Ekim 2026 gün sonu (İstanbul).
DEVIR_KESIM_MS = 1791752400000  # 2026-10-11T21:00:00Z


_db = None


def canli_db():
    global _db
    if _db is None:
        from veri import db
        _db = db.baglan(CANLI_DB)
    return _db
