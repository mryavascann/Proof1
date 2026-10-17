"""Kendi OKX TR hesabını panodan bağlama (misafir): salt okuma anahtarıyla bir kerelik tarama.

Anahtar yalnız bu bilgisayarda kalır: diske, veritabanına, günlüğe, ekrana ya da hata iletisine yazılmaz. Tarama iş
parçacığının yerel değişkenlerinde ve OkxKimlik nesnesinde durur, ATK'ya ortam değişkeniyle geçer (ATK'nın ev dizini boş
bir geçici dizindir); tarama bitince ya da düşünce bırakılır. Yetkisi okunamayan ya da işlem/çekim yetkili anahtarla
hiçbir hesap verisi okunmaz (veri/atk.py, yetki_zorunlu). Misafir taraması Telegram'a yazmaz, ücretli anlatıcıyı
çalıştırmaz; cümleler yalnız kalıptan. Sonuç data/hesaplar/<hesap>.db; tarama başarıyla bitmeden bu adla görünmez.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path

from calistir.sabah import ILERLEME
from veri.ayar import OkxKimlik

KOK = Path(__file__).resolve().parents[1]
HESAP_DIZINI = KOK / "data" / "hesaplar"              # data/ depoya girmez (.gitignore)
BICIM = re.compile(r"[0-9a-f]{12}")
SAHIP = {"hesap": "ana", "ad": "Ana hesap"}

YAZMA_YETKISI = "Bu anahtarın işlem ya da çekim yetkisi var. proof1 yalnız “Okuma” yetkili anahtarla çalışır."
TANIMADI = "OKX anahtarı tanımadı: anahtar, gizli anahtar ya da parola yanlış."
# OKX'in kimlik hataları (anahtar, imza, parola, ortam) ve HTTP 401. ATK 50111-50113'ü kodsuz AuthenticationError verir.
TANIMA_KODLARI = frozenset({"50100", "50101", "50103", "50104", "50105", "50106", "50107", "50111", "50113", "50114",
                            "401", "http401"})


def hata_metni(e: BaseException) -> str:
    """Kullanıcıya gösterilen ileti: yalnız sabit metin ve istisnanın tür adı; istisnanın kendi metni gösterilmez."""
    kod = str(getattr(e, "kod", "") or "")
    if kod == "yazma_yetkili_anahtar":
        return YAZMA_YETKISI
    if kod in TANIMA_KODLARI or (kod and "AuthenticationError" in str(e)):
        return TANIMADI
    return f"Tarama yarıda kaldı ({type(e).__name__})."


def tara(kimlik: OkxKimlik, db_yolu: Path, ilerleme) -> None:
    """Gerçek tarama: sabah işi tek hesap kipinde (Telegram yok, ücretli anlatıcı yok), sonra kalıp cümleler."""
    from anlatim import anlat
    from calistir import sabah
    sonuc = sabah.calistir(gonder=False, hafta=False, kimlik=kimlik, db_yolu=db_yolu, anlatici=False, ilerleme=ilerleme)
    try:
        anlat.anlat(db_yolu, sonuc["oturum"], None, kullanici="misafir")   # istemci yok: model çağrısı, ücret yok
    except Exception:
        pass                                    # cümlesiz de pano açılır (uyarı kartları kalıbı kendisi kurar)


def _tek_dosya(yol: Path) -> None:
    """WAL günlüğünü ana dosyaya katar, günlük kipini DELETE yapar: dosya tek başına taşınır ve okunur."""
    with closing(sqlite3.connect(yol)) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("PRAGMA journal_mode=DELETE")


def _sil(yol: Path) -> None:
    for ek in ("", "-wal", "-shm", "-journal"):
        try:
            Path(f"{yol}{ek}").unlink(missing_ok=True)
        except OSError:
            pass


class Hesaplar:
    """Misafir taramaları: aynı anda en çok bir tarama. Durum yalnız bellekte; anahtar tutulmaz."""

    def __init__(self, dizin: Path | None = None, tarayici=None):
        self.dizin = Path(dizin) if dizin else HESAP_DIZINI
        self.tarayici = tarayici or tara             # testte sahtesi verilir
        self._kilit = threading.Lock()
        self._durum: dict[str, dict] = {}
        self._suren: str | None = None

    def yol(self, hesap: str | None) -> Path | None:
        """Bitmiş misafir veri dosyası; kimlik biçimi tutmuyorsa ya da dosya yoksa None."""
        if not hesap or not BICIM.fullmatch(hesap):
            return None
        yol = self.dizin / f"{hesap}.db"
        return yol if yol.is_file() else None

    def liste(self) -> list[dict]:
        """Sahibin hesabı, ardından bitmiş misafir hesapları (bağlanma sırasıyla)."""
        bitmis = []
        if self.dizin.is_dir():
            for yol in self.dizin.iterdir():
                if yol.suffix == ".db" and BICIM.fullmatch(yol.stem) and yol.is_file():
                    st = yol.stat()
                    bitmis.append((getattr(st, "st_birthtime", st.st_ctime), yol.stem))
        return [dict(SAHIP)] + [{"hesap": h, "ad": f"Hesap {h[:4]}"} for _, h in sorted(bitmis)]

    def durum(self, hesap: str | None) -> dict | None:
        with self._kilit:
            d = self._durum.get(hesap or "")
            return dict(d) if d else None

    def bagla(self, api_key: str, secret_key: str, passphrase: str) -> str | None:
        """Taramayı arka planda başlatır, hesap kimliğini döndürür; bir tarama sürüyorsa None."""
        with self._kilit:
            if self._suren:
                return None
            hesap = secrets.token_hex(6)
            while hesap in self._durum or (self.dizin / f"{hesap}.db").exists():
                hesap = secrets.token_hex(6)
            self._suren = hesap
            self._durum[hesap] = {"hesap": hesap, "adim": ILERLEME[0], "sira": 1, "toplam": len(ILERLEME),
                                  "bitti": False, "hata": None}
        try:
            threading.Thread(target=self._tara, args=(hesap, api_key, secret_key, passphrase),
                             name=f"proof1-hesap-{hesap}", daemon=True).start()
        except RuntimeError:                         # iş parçacığı açılamadı: yuva boşalsın, durum hatayı söylesin
            self._bitir(hesap, "Tarama başlatılamadı.")
        return hesap

    def _adim(self, hesap: str, etiket: str) -> None:
        with self._kilit:
            d = self._durum[hesap]
            if not d["bitti"] and etiket in ILERLEME:
                d.update(adim=etiket, sira=ILERLEME.index(etiket) + 1)

    def _bitir(self, hesap: str, hata: str | None) -> None:
        with self._kilit:
            d = self._durum[hesap]
            if hata is None:
                d.update(adim=ILERLEME[-1], sira=len(ILERLEME))
            d.update(bitti=True, hata=hata)
            if self._suren == hesap:
                self._suren = None

    def _tara(self, hesap: str, api_key: str, secret_key: str, passphrase: str) -> None:
        hata, ev, kimlik = "Tarama yarıda kaldı.", None, None
        yarim = self.dizin / f"{hesap}.yaziliyor.db"
        try:
            ev = Path(tempfile.mkdtemp(prefix="proof1-atk-"))         # ATK'nın ev dizini: boş, sonunda silinir
            kimlik = OkxKimlik("misafir", api_key, secret_key, passphrase, "env", ev)
            api_key = secret_key = passphrase = None
            self.dizin.mkdir(parents=True, exist_ok=True)
            self.tarayici(kimlik, yarim, lambda etiket: self._adim(hesap, etiket))
            kimlik = None
            _tek_dosya(yarim)
            os.replace(yarim, self.dizin / f"{hesap}.db")
            hata = None
        except Exception as e:      # ileti sabit metinden kurulur; istisna (ve izindeki anahtarlı çerçeveler) saklanmaz
            hata = hata_metni(e)
        finally:
            kimlik = api_key = secret_key = passphrase = None
            if hata is not None:
                _sil(yarim)                          # yarım tarama verisi kalmasın
            if ev is not None:
                shutil.rmtree(ev, ignore_errors=True)
            self._bitir(hesap, hata)
