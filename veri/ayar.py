"""Ortam ve anahtarlar. Değerler hiçbir zaman yazdırılmaz; yalnız adlar konuşulur."""
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_yuklendi = False


def konsol_utf8() -> None:
    """Windows'ta çıktı cp1254'e düşebilir ve '→' gibi karakterler süreci çökertir: komut satırı araçları UTF-8 yazar."""
    import sys
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def env_yukle(yol: Path | None = None) -> None:
    """Kök .env dosyasını süreç ortamına alır (zaten dolu olanı ezmez)."""
    global _yuklendi
    yol = yol or KOK / ".env"
    if not yol.exists():
        _yuklendi = True
        return
    for satir in yol.read_text(encoding="utf-8-sig").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        ad, deger = satir.split("=", 1)
        deger = re.sub(r"\s+#.*$", "", deger).strip().strip('"').strip("'")
        if deger and not os.environ.get(ad.strip()):
            os.environ[ad.strip()] = deger
    _yuklendi = True


def al(ad: str, varsayilan: str = "") -> str:
    if not _yuklendi:
        env_yukle()
    return os.environ.get(ad, "") or varsayilan


def eksikler(adlar: list[str]) -> list[str]:
    """Boş olan anahtar adlarını döndürür (değer değil)."""
    return [a for a in adlar if not al(a)]


def db_yolu() -> Path:
    yol = Path(al("PROOF1_DB", "data/proof1.db"))
    return yol if yol.is_absolute() else KOK / yol


@dataclass(frozen=True)
class OkxKimlik:
    hesap: str
    api_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    passphrase: str = field(repr=False)
    kaynak: str = "env"            # env | profil
    profil_dizini: Path | None = None
    taban_url: str = "https://tr.okx.com"


def _profil_dizini(hesap: str) -> Path:
    ozel = al(f"OKX_TR_{hesap.upper()}_PROFIL")
    if ozel:
        return Path(ozel)
    return Path.home() / ("okx-ana" if hesap == "ana" else "okx-atk")


def okx_kimlik(hesap: str) -> OkxKimlik:
    """hesap: 'ana' | 'alt'. Önce .env, yoksa ATK profil dosyası (içeriği basılmaz)."""
    assert hesap in ("ana", "alt"), hesap
    on = f"OKX_TR_{hesap.upper()}_"
    k, s, p = al(on + "API_KEY"), al(on + "SECRET_KEY"), al(on + "PASSPHRASE")
    if k and s and p:
        return OkxKimlik(hesap, k, s, p, "env")
    dizin = _profil_dizini(hesap)
    toml = dizin / ".okx" / "config.toml"
    if not toml.exists():
        raise RuntimeError(f"OKX {hesap} hesabı için anahtar yok: {on}API_KEY / SECRET_KEY / PASSPHRASE eksik")
    veri = tomllib.loads(toml.read_text(encoding="utf-8"))
    profiller = veri.get("profiles", {})
    profil = profiller.get(veri.get("default_profile", "")) or next(iter(profiller.values()), {})
    try:
        return OkxKimlik(hesap, profil["api_key"], profil["secret_key"], profil["passphrase"], "profil",
                         dizin, profil.get("base_url") or "https://tr.okx.com")
    except KeyError as e:
        raise RuntimeError(f"OKX {hesap} profilinde alan eksik: {e.args[0]}") from None
