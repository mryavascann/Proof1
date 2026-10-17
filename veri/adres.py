"""Çekim kaydından adresler (kullanıcı adres yazmaz) ve sahiplik önerisi.

“Büyük olasılıkla senin”: çekim yapılan adres hesaba para da yatırmışsa. Yatırmanın göndereni kayıtta yoksa
işlem kimliğinden zincirde bulunur. Kesin karar kullanıcının (`isaret` tablosu, Merve).
"""
from collections import Counter
from dataclasses import dataclass, field

from veri import bicim
from veri.aglar import ag_bul, gezgin_url
from veri.borsa import Kayit
from veri.kayit import kisalt


def normal(adres: str) -> str:
    return adres.lower() if adres.lower().startswith("0x") else adres


@dataclass
class AdresKarti:
    adres: str
    ag: str
    aglar: list
    katman: int
    tahmin: str
    kanit: str
    cekim_sayisi: int
    ilk_ms: int
    son_ms: int
    yatirma_sayisi: int = 0
    etiket: str = ""
    cekim_kimlikleri: list = field(default_factory=list)

    @property
    def kisa(self) -> str:
        return kisalt(self.adres)


def adresleri_cikar(cekimler: list[Kayit], yatirmalar: list[Kayit], gonderen) -> list[AdresKarti]:
    """gonderen(ag, tx) → adres | None."""
    gruplar: dict[str, list[Kayit]] = {}
    for c in cekimler:
        if c.adres and not c.okunamadi:
            gruplar.setdefault(normal(c.adres), []).append(c)
    yatiranlar: dict[str, list[Kayit]] = {}
    for y in yatirmalar:
        s = y.adres or gonderen(y.ag, y.tx)
        if s:
            yatiranlar.setdefault(normal(s), []).append(y)
    kartlar = []
    for adres, grup in gruplar.items():
        aglar = Counter(c.ag.anahtar for c in grup)
        ana_ag = aglar.most_common(1)[0][0]
        yat = yatiranlar.get(adres, [])
        n = len(grup)
        if yat:
            kanit = (f"Bu adrese {n} kez çekim yapıldı; bu adresten hesaba {len(yat)} kez yatırma geldi "
                     f"(ilki {bicim.tarih(min(y.ts for y in yat), saat=False)}).")
        else:
            kanit = f"Bu adrese {n} kez çekim yapıldı; bu adresten hesaba yatırma görülmedi."
        kartlar.append(AdresKarti(
            adres=adres, ag=ana_ag, aglar=sorted(aglar), katman=max(c.ag.katman for c in grup),
            tahmin="benim" if yat else "belli_degil", kanit=kanit, cekim_sayisi=n,
            ilk_ms=min(c.ts for c in grup), son_ms=max(c.ts for c in grup), yatirma_sayisi=len(yat),
            cekim_kimlikleri=[c.kimlik for c in grup]))
    kartlar.sort(key=lambda a: a.ilk_ms)
    sira = {"benim": 0, "belli_degil": 0}
    for a in kartlar:
        sira[a.tahmin] += 1
        a.etiket = f"{'BENIM' if a.tahmin == 'benim' else 'ADRES'}_{sira[a.tahmin]}"
    return kartlar


def yaz(db, kartlar: list[AdresKarti], cekimler: list[Kayit] | None = None):
    """adres tablosunu günceller; çekim hareketlerinin `karsi` alanına etiketi yazar."""
    db.execute("UPDATE adres SET etiket = etiket || '~' || id")       # yeniden etiketlemede çakışma olmasın
    for a in kartlar:
        ag = next(ag_bul(c.chain) for c in (cekimler or []) if normal(c.adres) == a.adres) if cekimler else ag_bul(a.ag)
        db.execute(
            "INSERT INTO adres (adres, etiket, kisa, ag, katman, tahmin, kanit, cekim_sayisi, ilk_cekim, son_cekim, gezgin_url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(adres, ag) DO UPDATE SET etiket=excluded.etiket,"
            " kisa=excluded.kisa, katman=excluded.katman, tahmin=excluded.tahmin, kanit=excluded.kanit,"
            " cekim_sayisi=excluded.cekim_sayisi, ilk_cekim=excluded.ilk_cekim, son_cekim=excluded.son_cekim,"
            " gezgin_url=excluded.gezgin_url",
            (a.adres, a.etiket, a.kisa, a.ag, a.katman, a.tahmin, a.kanit, a.cekim_sayisi,
             bicim.tarih(a.ilk_ms), bicim.tarih(a.son_ms), gezgin_url(ag, a.adres)))
        for kimlik in a.cekim_kimlikleri:
            db.execute("UPDATE hareket SET karsi=? WHERE ham_kimlik IN (?, ?)", (a.etiket, f"cekim:{kimlik}", f"cekim:{kimlik}:ucret"))
    db.execute("DELETE FROM adres WHERE etiket LIKE '%~%'")
    db.commit()


def cekim_dolar_guncelle(db):
    """adres.cekim_dolar = o adrese yapılan çekimlerin o anki dolar toplamı (hareket.dolar dolduktan sonra)."""
    db.execute("""UPDATE adres SET cekim_dolar = (
                    SELECT printf('%.2f', -SUM(CAST(h.dolar AS REAL))) FROM hareket h
                    WHERE h.tur='cekim' AND h.karsi = adres.etiket AND h.dolar IS NOT NULL)""")
    db.commit()
