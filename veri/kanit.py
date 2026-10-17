"""OKX kanıt paneli: `cagri` tablosunun özeti (araç/uç, çağrı sayısı, süre, kullanılan alanlar, salt okunur).

Pano bunu `cagri_ozet` görünümünden ya da `kanit_ozeti()` ile okur.  Ekranda:  python -m veri.kanit [oturum]
"""
import json
import sys

GORUNUM = """
CREATE VIEW IF NOT EXISTS cagri_ozet AS
SELECT oturum, kaynak, ad, COUNT(*) AS cagri, SUM(sonuc='hata') AS hata,
       CAST(AVG(sure_ms) AS INTEGER) AS ort_ms, MAX(sure_ms) AS en_cok_ms, MIN(salt_okunur) AS salt_okunur,
       MIN(zaman) AS ilk, MAX(zaman) AS son
FROM cagri GROUP BY oturum, kaynak, ad
"""


def kanit_ozeti(db, oturum: str | None = None) -> list[dict]:
    db.execute(GORUNUM)
    kosul, p = ("WHERE oturum=?", (oturum,)) if oturum else ("", ())
    satirlar = db.execute(f"SELECT kaynak, ad, sure_ms, alanlar, sonuc, kod, salt_okunur, satir FROM cagri {kosul} ORDER BY id", p)
    ozet: dict = {}
    for r in satirlar:
        o = ozet.setdefault((r["kaynak"], r["ad"]), {"kaynak": r["kaynak"], "ad": r["ad"], "cagri": 0, "hata": 0, "_sure": [],
                                                      "alanlar": set(), "salt_okunur": True, "son_hata": None, "satir": 0})
        o["cagri"] += 1
        o["_sure"].append(r["sure_ms"])
        o["alanlar"] |= set(json.loads(r["alanlar"] or "[]"))
        o["salt_okunur"] &= bool(r["salt_okunur"])
        o["satir"] += r["satir"] or 0
        if r["sonuc"] == "hata":
            o["hata"] += 1
            o["son_hata"] = r["kod"]
    sonuc = []
    for o in ozet.values():
        s = o.pop("_sure")
        o["ort_ms"] = int(sum(s) / len(s))
        o["en_cok_ms"] = max(s)
        o["alanlar"] = sorted(o["alanlar"])
        sonuc.append(o)
    return sorted(sonuc, key=lambda o: (o["kaynak"], -o["cagri"]))


def atk_denetim_kaydi(atk, db, limit: int = 50) -> int:
    """ATK'nın kendi denetim kaydı (trade_get_history) → `_atk_denetim` (panoda “denetim kaydı”)."""
    from veri.atk import satirlar
    db.execute("CREATE TABLE IF NOT EXISTS _atk_denetim (zaman TEXT, arac TEXT, seviye TEXT, sure_ms INTEGER, ham TEXT,"
               " PRIMARY KEY (zaman, arac))")
    n = 0
    for r in satirlar(atk.cagir("trade_get_history", {"limit": limit})):
        if not isinstance(r, dict):
            continue
        db.execute("INSERT OR IGNORE INTO _atk_denetim VALUES (?,?,?,?,?)",
                   (str(r.get("timestamp") or r.get("time") or ""), str(r.get("tool") or ""), str(r.get("level") or ""),
                    r.get("durationMs") or r.get("duration"), json.dumps({k: v for k, v in r.items() if k not in ("args", "params")},
                                                                          ensure_ascii=False)[:2000]))
        n += 1
    db.commit()
    return n


def main():
    from veri.ayar import konsol_utf8
    konsol_utf8()                      # Windows: '→' gibi karakterlerde çökmesin
    from veri import db as dbm
    oturum = sys.argv[1] if len(sys.argv) > 1 else None
    for o in kanit_ozeti(dbm.baglan(), oturum):
        print(f"{o['kaynak']:<10} {o['ad'][:52]:<52} {o['cagri']:>4} çağrı  {o['ort_ms']:>5} ms  "
              f"{'salt okunur' if o['salt_okunur'] else 'yazma'}  hata {o['hata']}  alanlar: {', '.join(o['alanlar'][:6])}")


if __name__ == "__main__":
    main()
