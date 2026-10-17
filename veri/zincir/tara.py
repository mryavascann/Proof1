"""Tarama: çekim adreslerini okunabilen her ağda okur, çözer, `hareket`e yazar; her (adres, ağ) için durum tutar.

Durum: okundu (olay var) · bos (okundu, olay yok) · okunamadi (çekim yapılan ağ okunamadı → “yalnız çekimi görüyorum”).
“Benim” tahminli adreslerden para gönderilen yeni adresler `KARSI_n` etiketiyle eklenir (“bu adres senin mi?”).
"""
from dataclasses import dataclass, field

from veri import bicim
from veri.adres import normal
from veri.aglar import AGLAR, gezgin_url
from veri.defter import yaz as hyaz
from veri.kayit import kisalt, simdi
from veri.zincir.cozucu import Baglam, coz, hareketlere
from veri.zincir.okuyucu import Okunamadi

EVM_AGLAR = [AGLAR[k] for k in ("ERC20", "Arbitrum One", "Polygon", "Avalanche C-Chain", "Chiliz Chain", "BSC", "Base", "Optimism")]


@dataclass
class TaramaSonucu:
    okunan: int = 0
    okunamayan: list = field(default_factory=list)
    yeni_hareket: int = 0
    supheli: int = 0


def _tablo(db):
    db.execute("""CREATE TABLE IF NOT EXISTS _ag_durum (adres_id INTEGER, ag TEXT, durum TEXT, kaynak TEXT,
                  olay INTEGER, cekim_agi INTEGER, zaman TEXT, PRIMARY KEY (adres_id, ag))""")


def ag_durumlari(db) -> list[dict]:
    _tablo(db)
    return [dict(r) for r in db.execute(
        "SELECT a.etiket, d.ag, d.durum, d.kaynak, d.olay, d.cekim_agi FROM _ag_durum d JOIN adres a ON a.id=d.adres_id ORDER BY a.id, d.ag")]


def _benimler(db) -> set[str]:
    benim = {r[0].lower() for r in db.execute("SELECT adres FROM adres WHERE tahmin='benim'")}
    try:
        for et, sahip in db.execute("SELECT adres_etiket, sahip FROM isaret ORDER BY zaman"):
            r = db.execute("SELECT adres FROM adres WHERE etiket=?", (et,)).fetchone()
            if r:
                (benim.add if sahip == "benim" else benim.discard)(r[0].lower())
    except Exception:
        pass                                # isaret tablosu Merve'nin; henüz yoksa tahmin kullanılır
    return benim


def tara(db, okuyucu, cekimler, yatirmalar, borsa_adresleri: set | None = None) -> TaramaSonucu:
    _tablo(db)
    sonuc = TaramaSonucu()
    benim = _benimler(db)
    adresler = [r for r in db.execute("SELECT id, adres, etiket, tahmin, cekim_sayisi FROM adres ORDER BY id").fetchall()
                if r["cekim_sayisi"] > 0 or r["adres"].lower() in benim]       # çekim adresleri + “benim” denenler
    tum = {r[0].lower(): r[1] for r in db.execute("SELECT adres, etiket FROM adres")}
    baglam = Baglam(benim=benim, cekim_tx={c.tx.lower() for c in cekimler if c.tx},
                    yatirma_tx={y.tx.lower() for y in yatirmalar if y.tx},
                    borsa_adresleri=borsa_adresleri or set(), bilinen=set(tum))
    cekim_aglari: dict[str, set] = {}
    for c in cekimler:
        cekim_aglari.setdefault(normal(c.adres).lower(), set()).add(c.ag.anahtar)

    def etiketle(adres: str | None) -> str | None:
        return tum.get(adres.lower()) if adres else None

    for r in adresler:
        a = r["adres"]
        aglar = EVM_AGLAR if a.lower().startswith("0x") else [AGLAR["TRC20"]]
        for ag in aglar:
            cekim_agi = ag.anahtar in cekim_aglari.get(a.lower(), set())
            durum, kaynak, olay_sayisi = "okundu", "", 0
            if not okuyucu.okuyucular(ag):
                if not cekim_agi:
                    continue                 # okuyucusu olmayan, çekim de yapılmamış ağ: bilgi yok, satır yok
                durum = "okunamadi"
            else:
                try:
                    b = okuyucu.oku(a, ag)
                    kaynak = b.kaynak
                    olaylar = coz(a, ag, b, baglam)
                except Okunamadi:
                    durum, olaylar = "okunamadi", []
                if durum == "okundu":
                    olay_sayisi = len(olaylar)
                    if not olaylar:
                        durum = "bos"
                    else:
                        # benim tahminli adresten gidilen yeni adresler → KARSI_n
                        if a.lower() in benim:
                            for o in olaylar:
                                if o.tur == "gonderim" and o.karsi_adres and o.karsi_adres.lower() not in tum and not o.karsi:
                                    et = _karsi_ekle(db, o.karsi_adres, ag, r["etiket"], o)
                                    tum[o.karsi_adres.lower()] = et
                        h = hareketlere(olaylar, r["id"], ag.anahtar, kaynak, etiketle)
                        sonuc.yeni_hareket += hyaz(db, h)
                        sonuc.supheli += sum(1 for o in olaylar if o.supheli)
                        sonuc.okunan += 1
            if durum == "okunamadi":
                sonuc.okunamayan.append((r["etiket"], ag.anahtar))
            db.execute("INSERT OR REPLACE INTO _ag_durum VALUES (?,?,?,?,?,?,?)",
                       (r["id"], ag.anahtar, durum, kaynak, olay_sayisi, int(cekim_agi), simdi()))
        db.commit()
    _katman_guncelle(db)
    return sonuc


def _karsi_ekle(db, adres: str, ag, kimden_etiket: str, olay) -> str:
    n = db.execute("SELECT COUNT(*) FROM adres WHERE etiket LIKE 'KARSI_%'").fetchone()[0] + 1
    et = f"KARSI_{n}"
    ne = ", ".join(bicim.miktar(m, v) for v, m in olay.verdi.items())
    db.execute("INSERT OR IGNORE INTO adres (adres, etiket, kisa, ag, katman, tahmin, kanit, cekim_sayisi, gezgin_url)"
               " VALUES (?,?,?,?,?,?,?,?,?)",
               (adres.lower(), et, kisalt(adres), ag.anahtar, 3, "belli_degil",
                f"{kimden_etiket} bu adrese {bicim.tarih(olay.ts)} tarihinde {ne} gönderdi.", 0, gezgin_url(ag, adres)))
    r = db.execute("SELECT etiket FROM adres WHERE adres=? AND ag=?", (adres.lower(), ag.anahtar)).fetchone()
    return r[0]


def _katman_guncelle(db):
    """Adresin katmanı: herhangi bir ağda okunduysa 3, yalnız okunamadıysa 1."""
    db.execute("""UPDATE adres SET katman = CASE
                    WHEN EXISTS (SELECT 1 FROM _ag_durum d WHERE d.adres_id=adres.id AND d.durum IN ('okundu','bos')) THEN 3
                    WHEN EXISTS (SELECT 1 FROM _ag_durum d WHERE d.adres_id=adres.id) THEN 1
                    ELSE katman END""")
    db.commit()
