"""Dünle karşılaştırma (köprü): dün 09:00 → bugün 09:00, iki kapsam: `borsa` ve `servet` (borsa + “benim” cüzdanlar).

Önce coin miktarı düzeyinde: her varlık için seviye farkı = kalemler + açıklanamayan. Sonra dolar: kalemler bugünün
fiyatıyla, elde tutulanın fiyat farkı ayrı kalem (`fiyat`). Böylece köprü tam kapanır:
    başlangıç($) + Σ kalem($) = bitiş($)
Fiyatı olmayan varlık dolar hesabına girmez; `fiyatsiz` kaleminde coin cinsinden görünür (uydurulmaz).
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from veri.zincir.tara import _benimler, _tablo

SIRA = ["baslangic", "aktarim", "disari", "iceri", "bot", "takas", "ucret", "fiyat", "izlenemeyen", "fiyatsiz",
        "aciklanamayan", "bitis"]
ACIKLAMA = {
    "baslangic": "dün 09:00 toplam", "bitis": "bugün 09:00 toplam",
    "aktarim": "kendi hesapların arası (servet değişmez)", "disari": "dışarı giden", "iceri": "dışarıdan gelen",
    "bot": "bot sonucu (bota giren ve hesaba dönen paradan)", "takas": "takas farkı", "ucret": "ücretler",
    "fiyat": "fiyat etkisi (elde tutulan coin × fiyat farkı)", "izlenemeyen": "okunamayan ağa giden (yalnız çekimi görüyorum)",
    "fiyatsiz": "dolar fiyatı bilinmiyor (coin cinsinden)", "aciklanamayan": "açıklayamadığım",
}


@dataclass
class Kalem:
    kalem: str
    varlik: dict = field(default_factory=dict)
    dolar: Decimal = Decimal(0)
    aciklama: str = ""


def _ms(zaman: str) -> int:
    return int(datetime.fromisoformat(zaman.replace("Z", "+00:00")).timestamp() * 1000)


def _ekle(d: dict, v: str, q: Decimal):
    d[v] = d.get(v, Decimal(0)) + q


def _benim(db):
    benim_adres = _benimler(db)
    ids, etiket = set(), set()
    for r in db.execute("SELECT id, adres, etiket FROM adres"):
        if r["adres"].lower() in benim_adres:
            ids.add(r["id"])
            etiket.add(r["etiket"])
    return ids, etiket


def _okunamayan(db) -> set:
    _tablo(db)
    return {(r[0], r[1]) for r in db.execute(
        "SELECT a.etiket, d.ag FROM _ag_durum d JOIN adres a ON a.id=d.adres_id WHERE d.durum='okunamadi'")}


def _ag_anahtari(chain: str | None) -> str | None:
    if not chain:
        return None
    from veri.aglar import ag_bul
    return ag_bul(chain).anahtar


def kategori(h, kapsam: str, benim_etiket: set, benim_tx: set, okunamayan: set) -> str | None:
    tur, karsi = h["tur"], h["karsi"]
    if h["supheli"]:
        return None                                  # şüpheli token servet sayılmaz
    if tur in ("ucret",):
        return "ucret"
    if tur in ("bota_giris", "bottan_donus"):
        return "bot"
    if tur in ("alim", "satim", "takas"):
        return "takas"
    if tur == "taninmadi":
        return "aciklanamayan"
    if tur == "aktarim":
        return "aktarim"
    tx = (h["islem_kimligi"] or "").lower()
    if h["kaynak"] == "borsa":
        if tur == "cekim":
            if kapsam == "borsa":
                return "aktarim" if karsi in benim_etiket else "disari"
            if tx and tx in benim_tx:
                return "aktarim"
            if karsi in benim_etiket and (karsi, _ag_anahtari(h["ag"])) in okunamayan:
                return "izlenemeyen"
            return "aktarim" if karsi in benim_etiket else "disari"
        if tur == "yatirma":
            return "aktarim" if (kapsam == "servet" and tx in benim_tx) or karsi in benim_etiket else "iceri"
        if tur == "giris":
            return "iceri"                           # ör. Lira Boost kazancı
        return "aciklanamayan"
    # cüzdan satırları (yalnız servet kapsamında)
    if tur == "giris":
        return "aktarim" if karsi == "ana" or karsi in benim_etiket else "iceri"
    if tur == "gonderim":
        return "aktarim" if karsi == "ana" or karsi in benim_etiket else "disari"
    return "aciklanamayan"


def _cuzdan_seviye(db, ids: set, ts: int) -> dict:
    seviye: dict = {}
    if not ids:
        return seviye
    for r in db.execute(f"SELECT zaman, varlik, miktar FROM hareket WHERE hesap='cuzdan' AND supheli=0 "
                        f"AND adres_id IN ({','.join('?' * len(ids))})", tuple(ids)):
        if _ms(r["zaman"]) <= ts:
            _ekle(seviye, r["varlik"], Decimal(r["miktar"]))
    return seviye


def kopru_kur(db, gun: str, bas_ms: int, bit_ms: int, fiyat, fotolar: dict | None = None) -> dict:
    """fiyat(varlik, ts_ms) → dolar | None. fotolar: {'bas'|'bit': {yer: {varlik: miktar}}} (borsa seviyeleri)."""
    fotolar = fotolar or {}
    ids, etiket = _benim(db)
    okunamayan = _okunamayan(db)
    satirlar = [r for r in db.execute("SELECT * FROM hareket WHERE durum='ok'") if bas_ms < _ms(r["zaman"]) <= bit_ms]
    benim_tx = {(r["islem_kimligi"] or "").lower() for r in satirlar if r["hesap"] == "cuzdan" and r["adres_id"] in ids}
    sonuc = {}
    for kapsam in ("borsa", "servet"):
        akis: dict[str, dict] = {}
        for r in satirlar:
            if r["kaynak"] != "borsa" and not (kapsam == "servet" and r["adres_id"] in ids):
                continue
            k = kategori(r, kapsam, etiket, benim_tx, okunamayan)
            if k:
                _ekle(akis.setdefault(k, {}), r["varlik"], Decimal(r["miktar"]))
        toplam_akis: dict = {}
        for d in akis.values():
            for v, q in d.items():
                _ekle(toplam_akis, v, q)
        # Borsa seviyeleri: fotoğraf varsa ondan; yoksa diğer uçtan defterle geri hesap (açıklanamayan 0 olur).
        bas, bit = {}, {}
        for uc, hedef in (("bas", bas), ("bit", bit)):
            for yer, varliklar in (fotolar.get(uc) or {}).items():
                if yer.startswith("borsa"):
                    for v, q in varliklar.items():
                        _ekle(hedef, v, Decimal(q))
        borsa_akis = {}
        for r in satirlar:
            if r["kaynak"] == "borsa":
                _ekle(borsa_akis, r["varlik"], Decimal(r["miktar"]))
        if fotolar.get("bit") and not fotolar.get("bas"):
            for v in set(bit) | set(borsa_akis):
                bas[v] = bit.get(v, Decimal(0)) - borsa_akis.get(v, Decimal(0))
        elif not fotolar.get("bit"):
            for v in set(bas) | set(borsa_akis):
                bit[v] = bas.get(v, Decimal(0)) + borsa_akis.get(v, Decimal(0))
        if kapsam == "servet":
            for v, q in _cuzdan_seviye(db, ids, bas_ms).items():
                _ekle(bas, v, q)
            for v, q in _cuzdan_seviye(db, ids, bit_ms).items():
                _ekle(bit, v, q)
        # Açıklanamayan = ölçülen seviye farkı − defterdeki kalemler (+ tanınmayan girişler).
        # İzlenemeyen ağa giden para akışta görünür, bitiş seviyesinde yoktur: fark doğal olarak kapanır.
        for v in set(bas) | set(bit) | set(toplam_akis):
            fark = bit.get(v, Decimal(0)) - bas.get(v, Decimal(0)) - toplam_akis.get(v, Decimal(0))
            if fark:
                _ekle(akis.setdefault("aciklanamayan", {}), v, fark)
        # Dolar
        p_bas = {v: fiyat(v, bas_ms) for v in set(bas) | set(bit) | set(toplam_akis)}
        p_bit = {v: fiyat(v, bit_ms) for v in p_bas}
        fiyatsiz = {v for v, p in p_bit.items() if p is None}
        kalemler = {k: Kalem(k, aciklama=ACIKLAMA[k]) for k in SIRA}
        for k, d in akis.items():
            for v, q in d.items():
                if not q:
                    continue
                if v in fiyatsiz:
                    _ekle(kalemler["fiyatsiz"].varlik, v, q)
                else:
                    _ekle(kalemler[k].varlik, v, q)
                    kalemler[k].dolar += q * p_bit[v]
        for v, q in bas.items():
            if v in fiyatsiz:
                continue
            pb = p_bas[v] if p_bas[v] is not None else p_bit[v]
            kalemler["baslangic"].varlik[v] = q
            kalemler["baslangic"].dolar += q * pb
            if q and p_bit[v] != pb:
                _ekle(kalemler["fiyat"].varlik, v, q)
                kalemler["fiyat"].dolar += q * (p_bit[v] - pb)
        for v, q in bit.items():
            if v not in fiyatsiz:
                kalemler["bitis"].varlik[v] = q
                kalemler["bitis"].dolar += q * p_bit[v]
        sonuc[kapsam] = [kalemler[k] for k in SIRA
                         if k in ("baslangic", "bitis", "aciklanamayan") or kalemler[k].varlik or kalemler[k].dolar]
    return sonuc


def kopruyu_yaz(db, gun: str, kopru: dict, olgular: dict | None = None):
    """olgular: {(kapsam, kalem): ['o3', ...]} — B7 doldurur."""
    db.execute("DELETE FROM kopru WHERE gun=?", (gun,))
    for kapsam, kalemler in kopru.items():
        for sira, k in enumerate(kalemler, start=1):
            db.execute("INSERT INTO kopru (gun, kapsam, sira, kalem, tutar, varlik_tutar, aciklama, olgular) VALUES (?,?,?,?,?,?,?,?)",
                       (gun, kapsam, sira, k.kalem, str(k.dolar.quantize(Decimal("0.0001"))),
                        json.dumps({v: str(q) for v, q in k.varlik.items()}), k.aciklama,
                        json.dumps((olgular or {}).get((kapsam, k.kalem), []))))
    db.commit()


def fotografi_yaz(db, gun: str, zaman: str, yerler: dict, fiyat, ts_ms: int):
    """yerler: {'borsa:ana': {varlik: miktar}, 'adres:BENIM_1': {...}}. Seviye: gizli modda gösterilmez."""
    for yer, varliklar in yerler.items():
        for v, q in varliklar.items():
            p = fiyat(v, ts_ms)
            db.execute("INSERT OR REPLACE INTO fotograf (gun, zaman, yer, varlik, miktar, fiyat, dolar) VALUES (?,?,?,?,?,?,?)",
                       (gun, zaman, yer, v, str(q), None if p is None else str(p),
                        None if p is None else str((Decimal(q) * p).quantize(Decimal("0.0001")))))
    db.commit()


def fotograf_oku(db, gun: str) -> dict:
    yerler: dict = {}
    for r in db.execute("SELECT yer, varlik, miktar FROM fotograf WHERE gun=?", (gun,)):
        yerler.setdefault(r["yer"], {})[r["varlik"]] = Decimal(r["miktar"])
    return yerler
