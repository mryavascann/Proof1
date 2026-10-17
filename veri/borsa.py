"""Borsa okuyucu: ana hesabın çekim/yatırma/fonlama kaydı (imzalı uçlar) ve doğrulanmış satırlar."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from veri.aglar import ag_bul, ag_kismi
from veri.okx_imzali import OkxTr

CEKIM_ALANLARI = ["ts", "ccy", "chain", "amt", "fee", "feeCcy", "to", "txId", "state", "wdId"]
YATIRMA_ALANLARI = ["ts", "ccy", "chain", "amt", "from", "to", "txId", "state", "depId"]


def ondalik(x) -> Decimal | None:
    try:
        d = Decimal(str(x))
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass
class Kayit:
    """Borsadan gelen çekim ya da yatırma; alanı eksik olan `okunamadi=True`."""
    tur: str          # cekim | yatirma
    kimlik: str
    ts: int
    ccy: str
    chain: str
    miktar: Decimal
    ucret: Decimal
    ucret_ccy: str
    adres: str        # çekimde alıcı (`to`), yatırmada gönderen (`from`, boş olabilir)
    tx: str
    durum: str
    okunamadi: bool = False

    @property
    def ag_adi(self) -> str:
        return ag_kismi(self.chain)

    @property
    def ag(self):
        return ag_bul(self.chain)


def _kayit(tur: str, r: dict) -> Kayit:
    ts = r.get("ts")
    miktar = ondalik(r.get("amt"))
    ucret = ondalik(r.get("fee") or "0")
    adres = r.get("to" if tur == "cekim" else "from") or ""
    eksik = (not str(ts or "").isdigit() or miktar is None or ucret is None or not r.get("ccy")
             or not r.get("chain") or (tur == "cekim" and not adres))
    return Kayit(
        tur=tur,
        kimlik=str(r.get("wdId") or r.get("depId") or r.get("txId") or ts),
        ts=int(ts) if str(ts or "").isdigit() else 0,
        ccy=str(r.get("ccy") or "?"),
        chain=str(r.get("chain") or "?"),
        miktar=miktar or Decimal(0),
        ucret=ucret or Decimal(0),
        ucret_ccy=str(r.get("feeCcy") or r.get("ccy") or ""),
        adres=adres,
        tx=str(r.get("txId") or ""),
        durum=str(r.get("state") or ""),
        okunamadi=eksik,
    )


def cekimler(okx: OkxTr) -> list[Kayit]:
    ham = okx.sayfala("/api/v5/asset/withdrawal-history", alanlar=CEKIM_ALANLARI)
    return sorted((_kayit("cekim", r) for r in ham), key=lambda k: k.ts)


def yatirmalar(okx: OkxTr) -> list[Kayit]:
    ham = okx.sayfala("/api/v5/asset/deposit-history", alanlar=YATIRMA_ALANLARI)
    return sorted((_kayit("yatirma", r) for r in ham), key=lambda k: k.ts)


def fonlama_defteri(okx: OkxTr) -> list[dict]:
    return okx.sayfala("/api/v5/asset/bills", alanlar=["billId", "ccy", "balChg", "bal", "type", "ts"])


def tamamlanan(kayitlar: list[Kayit]) -> list[Kayit]:
    """Çekimde state 2 = tamamlandı; yatırmada 2 = hesaba geçti."""
    return [k for k in kayitlar if k.durum == "2" and not k.okunamadi]


def dolar_degeri(kayitlar: list[Kayit], fiyatci) -> tuple[Decimal, list[Kayit]]:
    """Her kaydın o anki dolar karşılığının toplamı; fiyatı bulunamayanlar ayrı döner."""
    toplam, fiyatsiz = Decimal(0), []
    for k in kayitlar:
        f = fiyatci.dolar(k.ccy, k.ts)
        if f is None:
            fiyatsiz.append(k)
        else:
            toplam += k.miktar * f
    return toplam, fiyatsiz
