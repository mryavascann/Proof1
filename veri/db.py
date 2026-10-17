"""Ortak SQLite dosyası: Buğra'nın tabloları (ortak/SOZLESME.md)."""
import sqlite3
from pathlib import Path

from veri import ayar

SEMA = """
CREATE TABLE IF NOT EXISTS hareket (
    id INTEGER PRIMARY KEY,
    zaman TEXT NOT NULL,
    kaynak TEXT NOT NULL,
    hesap TEXT NOT NULL,
    adres_id INTEGER,
    ag TEXT,
    varlik TEXT NOT NULL,
    miktar TEXT NOT NULL,
    dolar TEXT,
    tur TEXT NOT NULL,
    islem_kimligi TEXT,
    karsi TEXT,
    supheli INTEGER NOT NULL DEFAULT 0,
    durum TEXT NOT NULL DEFAULT 'ok',
    kaynak_okuma TEXT NOT NULL,
    ham_kimlik TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS adres (
    id INTEGER PRIMARY KEY,
    adres TEXT NOT NULL,
    etiket TEXT UNIQUE NOT NULL,
    kisa TEXT NOT NULL,
    ag TEXT NOT NULL,
    katman INTEGER NOT NULL,
    tahmin TEXT NOT NULL,
    kanit TEXT,
    cekim_sayisi INTEGER NOT NULL DEFAULT 0,
    cekim_dolar TEXT,
    ilk_cekim TEXT,
    son_cekim TEXT,
    gezgin_url TEXT,
    UNIQUE (adres, ag)
);
CREATE TABLE IF NOT EXISTS fotograf (
    gun TEXT NOT NULL,
    zaman TEXT NOT NULL,
    yer TEXT NOT NULL,
    varlik TEXT NOT NULL,
    miktar TEXT NOT NULL,
    fiyat TEXT,
    dolar TEXT,
    PRIMARY KEY (gun, yer, varlik)
);
CREATE TABLE IF NOT EXISTS kopru (
    gun TEXT NOT NULL,
    kapsam TEXT NOT NULL,
    sira INTEGER NOT NULL,
    kalem TEXT NOT NULL,
    tutar TEXT NOT NULL,
    varlik_tutar TEXT,
    aciklama TEXT,
    olgular TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (gun, kapsam, sira)
);
CREATE TABLE IF NOT EXISTS olgu (
    oturum TEXT NOT NULL,
    no TEXT NOT NULL,
    tur TEXT NOT NULL,
    alanlar TEXT NOT NULL,
    gizli INTEGER NOT NULL DEFAULT 0,
    kaynak TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (oturum, no)
);
CREATE TABLE IF NOT EXISTS uyari (
    id INTEGER PRIMARY KEY,
    oturum TEXT NOT NULL,
    zaman TEXT NOT NULL,
    tur TEXT NOT NULL,
    onem TEXT NOT NULL,
    olgular TEXT NOT NULL,
    gonderildi TEXT
);
CREATE TABLE IF NOT EXISTS cagri (
    id INTEGER PRIMARY KEY,
    oturum TEXT,
    zaman TEXT NOT NULL,
    kaynak TEXT NOT NULL,
    ad TEXT NOT NULL,
    parametreler TEXT NOT NULL,
    sure_ms INTEGER NOT NULL,
    alanlar TEXT NOT NULL DEFAULT '[]',
    satir INTEGER,
    sonuc TEXT NOT NULL,
    kod TEXT,
    salt_okunur INTEGER NOT NULL DEFAULT 1
);
"""


def baglan(yol: Path | str | None = None) -> sqlite3.Connection:
    yol = Path(yol) if yol else ayar.db_yolu()
    if str(yol) != ":memory:":
        yol.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(yol), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL" if str(yol) != ":memory:" else "PRAGMA journal_mode=MEMORY")
    db.executescript(SEMA)
    return db
