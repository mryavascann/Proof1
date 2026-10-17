"""Araştıran anlatıcı: bot kaydı tutmadığında proof1 salt okuma araçlarıyla kendisi araştırır ve izini yazar.

    python -m anlatim.arastir --oturum sabah-2026-10-17 --kayit anlatim/kayit/bot_16_ekim.json
    python -m anlatim.arastir --oturum sabah-2026-10-17 --canli      # ATK --read-only, alt hesap (Buğra'nın bilgisayarı)

Her adım `iz` tablosuna yazılır: hedef → plan/gerekçe → araç → gözlem → karar → sonuç; başarısız çağrı da.
- Araçlar yalnız IZINLI listesidir; başka bir ad ATK'ya hiç iletilmez.
- Gözlemlerdeki sayıları kod çıkarır; model sayı yazmaz. Gerekçede sayı varsa gösterilmez.
- Modelin kararını kod, olgularla karşılaştırarak doğrular; uyuşmazsa kodun kararı yazılır.
- Model yoksa (anahtar, bütçe tavanı) aynı araçlarla kalıp plan izlenir ve bu açıkça "plan" diye yazılır.
- Modelin özel iç muhakemesi kaydedilmez; yalnız istenen kısa gerekçe.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from anlatim import butce, kalip
from anlatim.anlat import DUSUNME, KOK_DIZIN, _env_yukle, _kullanim, olgulari_oku
from anlatim.denetim import sayilari_ayikla

IZINLI = ("grid_get_order_details", "grid_get_sub_orders", "account_get_bills")
DURDURMA = {"1": "sat (coinleri satarak)", "2": "coinleri tut"}
EN_COK_ADIM = 6
ZAMAN_ASIMI = 20.0


class AracYasak(Exception):
    pass


class AracHatasi(Exception):
    def __init__(self, kod: str, mesaj: str = ""):
        super().__init__(mesaj or kod)
        self.kod = kod


def _izin(arac: str) -> None:
    if arac not in IZINLI:
        raise AracYasak(f"{arac} salt okuma araçları arasında değil")


class KayitliAraclar:
    """Kayıtlı (gerçek, önceden alınmış) ATK yanıtları. İzde '[kayıt]' etiketiyle görünür."""

    def __init__(self, yol):
        d = json.loads(Path(yol).read_text(encoding="utf-8"))
        self.algo_id, self.yanitlar, self.etiket = d.get("algoId"), d.get("yanitlar", {}), "kayıt"

    def cagir(self, arac: str, argumanlar: dict):
        _izin(arac)
        if arac not in self.yanitlar:
            raise AracHatasi("kayit_yok", "bu araç için kayıtlı yanıt yok")
        return self.yanitlar[arac]


class CanliAraclar:
    """Buğra'nın ATK istemcisi (--read-only). Çağrılar onun `cagri` tablosuna da yazılır."""

    def __init__(self, atk, algo_id: str | None = None):
        self.atk, self.algo_id, self.etiket = atk, algo_id, "canlı"

    def cagir(self, arac: str, argumanlar: dict):
        _izin(arac)
        try:
            return self.atk.cagir(arac, argumanlar)
        except AracYasak:
            raise
        except Exception as e:  # ATK hatası, zaman aşımı, bağlantı
            raise AracHatasi(str(getattr(e, "kod", "hata")), str(e)[:160]) from e


# ---------- gözlemler (sayılar koddan) ----------
def _satirlar(veri) -> list[dict]:
    if isinstance(veri, list):
        return veri
    if isinstance(veri, dict):
        for k in ("data", "result", "items"):
            if isinstance(veri.get(k), list):
                return veri[k]
    return []


def _tr(d: Decimal, isaret: bool = False) -> str:
    metin = format(abs(d).normalize(), "f")
    tam, _, kesir = metin.partition(".")
    govde = f"{int(tam):,}".replace(",", ".") + ("," + kesir if kesir else "")
    if d < 0:
        return "−" + govde
    return ("+" if isaret and d > 0 else "") + govde


GORUNEN = {"TRY": "TL"}


def _ad(varlik: str) -> str:
    return GORUNEN.get(varlik, varlik)


def _kote(inst: str) -> tuple[str, str]:
    parca = (inst or "-").split("-")
    return parca[0], parca[-1]


def gozlem_detay(veri, bulgu: dict) -> str:
    r = (_satirlar(veri) or [{}])[0]
    pnl, yatirim = Decimal(str(r.get("totalPnl", "0"))), Decimal(str(r.get("investment", "0")))
    coin, kote = _kote(r.get("instId", ""))
    bulgu.update(kayit_pnl=pnl, yatirim=yatirim, coin=coin, kote=kote,
                 cTime=int(r.get("cTime") or 0), uTime=int(r.get("uTime") or 0))
    return (f"Botun kaydı: {r.get('instId')} grid, yatırım {_tr(yatirim)} {_ad(kote)}, kayıt sonucu "
            f"{_tr(pnl.quantize(Decimal('0.01')), True)} {_ad(kote)} (kayıtta {_tr(pnl)}), durdurma: "
            f"{DURDURMA.get(str(r.get('stopType')), str(r.get('stopType')))}.")


def gozlem_alt(veri, bulgu: dict) -> str:
    n = len(_satirlar(veri))
    bulgu["alt_emir"] = n
    return f"{n} alt emir okundu."


def gozlem_defter(veri, bulgu: dict) -> str:
    from veri.defter import ayristir, hareketlere, zincirle  # Buğra'nın defter çözücüsü (salt okunur kullanım)
    satirlar = _satirlar(veri)
    if bulgu.get("cTime"):
        bas, son = bulgu["cTime"] - 1_000, bulgu["uTime"] + 120_000
        satirlar = [s for s in satirlar if bas <= int(s.get("ts") or 0) <= son]
    s = ayristir(satirlar, "alt", "account_get_bills")
    zincirle(s)
    giris, donus = {}, {}
    for h in hareketlere(s):
        hedef = giris if h["tur"] == "bota_giris" else donus if h["tur"] == "bottan_donus" else None
        if hedef is not None:
            hedef[h["varlik"]] = hedef.get(h["varlik"], Decimal(0)) + Decimal(h["miktar"])
    bulgu.update(giris=giris, donus=donus)
    g = " ve ".join(f"{_tr(m)} {_ad(v)}" for v, m in giris.items()) or "bulunamadı"
    d = " ve ".join(f"{_tr(m, True)} {_ad(v)}" for v, m in donus.items()) or "bulunamadı"
    return f"Defter: bota giren {g}; hesaba dönen {d}."


GOZLEM = {"grid_get_order_details": gozlem_detay, "grid_get_sub_orders": gozlem_alt,
          "account_get_bills": gozlem_defter}


def _arguman(arac: str, algo_id: str) -> dict:
    if arac == "account_get_bills":
        return {"limit": "100"}
    a = {"algoOrdType": "grid", "algoId": algo_id}
    return {**a, "type": "filled"} if arac == "grid_get_sub_orders" else a


# ---------- karar (kod) ----------
def _sayi(metin) -> Decimal | None:
    s = sayilari_ayikla(str(metin or ""))
    return s[0].deger if s else None


def kod_karari(olgu: dict, bulgu: dict) -> tuple[str, str]:
    kayit, gercek, kalan = _sayi(olgu.get("kayit_sonuc")), _sayi(olgu.get("gercek_sonuc")), _sayi(olgu.get("kalan_coin_degeri"))
    notlar = []
    if "kayit_pnl" in bulgu and kayit is not None:
        ayni = bulgu["kayit_pnl"].quantize(Decimal("0.01")) == kayit
        notlar.append("Okunan kayıt olguyla " + ("aynı." if ayni else "uyuşmuyor."))
    if "donus" in bulgu:
        donen = _sayi(olgu.get("donen_kote"))
        kote = bulgu.get("kote", "TRY")
        if donen is not None and kote in bulgu["donus"]:
            ayni = bulgu["donus"][kote].quantize(Decimal("0.01")) == donen
            notlar.append("Defterde hesaba dönen para olguyla " + ("aynı." if ayni else "uyuşmuyor."))
    else:
        notlar.append("Defter okunamadı; karar olgulara dayanıyor.")
    if kayit is None or gercek is None:
        return "belirsiz", " ".join(notlar + ["Kayıt ya da gerçek sonuç bilinmiyor."])
    fark = kayit - gercek
    if abs(fark) <= Decimal("0.05"):
        return "tutuyor", " ".join(notlar + ["Kayıt, hesaba dönen parayla tutuyor."])
    if kalan is not None and abs(fark - kalan) <= max(Decimal("0.05"), abs(kalan) * Decimal("0.005")):
        return "iki_kez_sayilmis", " ".join(notlar + ["Fark, elde kalan coinin değeri kadar: kayıt bu coini iki kez "
                                                       "sayılmış gibi gösteriyor."])
    return "uyusmazlik", " ".join(notlar + ["Kayıt ile hesaba dönen para arasındaki fark açıklanamadı."])


# ---------- iz ----------
def _iz_tablosu(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS iz (
        iz_no TEXT, oturum TEXT, hedef TEXT, sira INTEGER, dusunce TEXT, arac TEXT,
        gozlem TEXT, karar TEXT, sonuc TEXT, zaman TEXT)""")


def _simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _gerekce(metin) -> str:
    metin = str(metin or "").strip()[:240]
    if re.search(r"\d", metin):
        return "Gerekçe sayı içerdiği için gösterilmiyor; sayılar yalnız koddan gelir."
    return metin or "Gerekçe verilmedi."


class Iz:
    def __init__(self, db, oturum: str, hedef: str, etiket: str):
        self.db, self.oturum, self.hedef, self.etiket = db, oturum, hedef, etiket
        self.no = f"iz-{oturum}-{int(time.time() * 1000)}"
        self.sira = 0
        _iz_tablosu(db)

    def yaz(self, dusunce, arac, gozlem="", karar="", sonuc="ok"):
        self.sira += 1
        etiketli = f"{arac} [{self.etiket}]" if arac in IZINLI else arac
        self.db.execute("INSERT INTO iz VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (self.no, self.oturum, self.hedef, self.sira, dusunce, etiketli, gozlem, karar, sonuc, _simdi()))
        self.db.commit()


def _calistir(araclar, arac, algo_id, bulgu) -> tuple[str, str]:
    """(gözlem, sonuç) — hata da bir gözlemdir."""
    try:
        veri = araclar.cagir(arac, _arguman(arac, algo_id))
        return GOZLEM[arac](veri, bulgu), "ok"
    except AracHatasi as e:
        return f"Çağrı başarısız: {e}", f"hata: {e.kod}"


def _plan(iz: Iz, araclar, algo_id, bulgu) -> None:
    adimlar = [("grid_get_order_details", "Plan (kalıp): önce botun kaydının ne dediğini okuyorum."),
               ("grid_get_sub_orders", "Plan (kalıp): botun dolan alt emirlerini okuyorum."),
               ("account_get_bills", "Plan (kalıp): bota giren ve hesaba dönen parayı defterden okuyorum.")]
    for arac, dusunce in adimlar:
        gozlem, sonuc = _calistir(araclar, arac, algo_id, bulgu)
        karar = ("Bu adım okunamadı; karar için zorunlu değil, sonraki okumaya devam ediyorum." if sonuc != "ok"
                 else "Gözlem kaydedildi; sonraki okumaya geçiyorum.")
        iz.yaz(dusunce, arac, gozlem, karar, sonuc)


SISTEM = """Sen proof1'ın araştırıcısısın. proof1 yalnız okur: emir veremez, botu durduramaz, para taşıyamaz.
Elinde yalnız okuma araçları var. Hedef: bir grid botunun borsadaki kaydının, hesaba dönen parayla tutup tutmadığını bulmak.
Araçları istediğin sırayla çağır; gereksiz çağrı yapma. Her çağrıda "gerekce" alanına bu adımı neden attığını tek kısa
cümleyle yaz; gerekçede sayı yazma (sayıları gözlemler verir). Yeterli gözlemin olunca karar_ver aracını çağır."""


def _araclar_tanimi() -> list[dict]:
    gerekce = {"type": "string", "description": "Bu adımı neden attığın; tek kısa cümle, sayı yazma."}
    aciklama = {"grid_get_order_details": "Botun borsadaki kaydını okur: yatırım, kayıt sonucu (totalPnl), durdurma tipi.",
                "grid_get_sub_orders": "Botun dolan alt emirlerini okur.",
                "account_get_bills": "Alt hesabın defterini okur: bota giren ve bottan dönen para."}
    tanim = [{"name": a, "description": aciklama[a], "strict": True,
              "input_schema": {"type": "object", "properties": {"gerekce": gerekce}, "required": ["gerekce"],
                               "additionalProperties": False}} for a in IZINLI]
    tanim.append({"name": "karar_ver", "description": "Araştırmayı bitirir ve kararı bildirir.", "strict": True,
                  "input_schema": {"type": "object", "properties": {
                      "karar": {"type": "string", "enum": ["tutuyor", "iki_kez_sayilmis", "uyusmazlik", "belirsiz"]},
                      "gerekce": gerekce}, "required": ["karar", "gerekce"], "additionalProperties": False}})
    return tanim


def _model(iz: Iz, araclar, algo_id, bulgu, istemci, model, olgu, kullanici, ay, db):
    """Model döngüsü. Model kararını (karar, gerekçe) ya da None döndürür."""
    import anthropic
    mesajlar = [{"role": "user", "content": json.dumps({"hedef": iz.hedef, "olgu": olgu}, ensure_ascii=False)}]
    for _ in range(EN_COK_ADIM):
        try:
            y = istemci.with_options(timeout=ZAMAN_ASIMI, max_retries=0).messages.create(
                model=model, max_tokens=1500, system=[{"type": "text", "text": SISTEM, "cache_control": {"type": "ephemeral"}}],
                tools=_araclar_tanimi(), messages=mesajlar, thinking=DUSUNME[model], output_config={"effort": "low"})
        except (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.APIStatusError) as e:
            butce.yaz(db, kullanici, ay, model, 0, 0, Decimal(0), "zaman_asimi" if isinstance(e, anthropic.APITimeoutError) else "hata")
            iz.yaz("Model yanıt vermedi.", "model", type(e).__name__, "Kalıp plana geçiyorum.", "hata: model")
            return "plana_gec"
        k = _kullanim(y)
        butce.yaz(db, kullanici, ay, model, k["input_tokens"] + k["cache_read_input_tokens"] + k["cache_creation_input_tokens"],
                  k["output_tokens"], butce.tutar_tl(model, k), "ok" if y.stop_reason in ("tool_use", "end_turn") else str(y.stop_reason))
        cagrilar = [b for b in y.content if getattr(b, "type", "") == "tool_use"]
        if not cagrilar:
            return None
        mesajlar.append({"role": "assistant", "content": y.content})
        sonuclar = []
        for c in cagrilar:
            girdi = c.input if isinstance(c.input, dict) else {}
            if c.name == "karar_ver":
                return girdi.get("karar"), _gerekce(girdi.get("gerekce"))
            if c.name not in IZINLI:
                iz.yaz(_gerekce(girdi.get("gerekce")), c.name, "Araç yok; ATK'ya iletilmedi.",
                       "Yalnız okuma araçları kullanılabilir.", "reddedildi: salt okuma dışı araç")
                sonuclar.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                                 "content": "Bu araç yok. Yalnız okuma araçları kullanılabilir."})
                continue
            gozlem, sonuc = _calistir(araclar, c.name, algo_id, bulgu)
            iz.yaz(_gerekce(girdi.get("gerekce")), c.name, gozlem, "", sonuc)
            sonuclar.append({"type": "tool_result", "tool_use_id": c.id, "content": gozlem, "is_error": sonuc != "ok"})
        mesajlar.append({"role": "user", "content": sonuclar})
    return None


def arastir(db_yolu, oturum: str, araclar, istemci=None, kullanici: str = "bugra", ay: str | None = None) -> str | None:
    ay = ay or datetime.now(timezone.utc).strftime("%Y-%m")
    with closing(sqlite3.connect(db_yolu)) as db:
        olgu = next((o for o in olgulari_oku(db, oturum) if o.tur == "bot_uyusmazlik" and not o.gizli), None)
        if olgu is None:
            return None
        a = olgu.alanlar
        hedef = f"{a.get('bot', 'Bot')} botunun kaydı ({a.get('kayit_sonuc')}) hesaba dönen parayla tutuyor mu?"
        iz = Iz(db, oturum, hedef, araclar.etiket)
        algo_id = araclar.algo_id or a.get("algoId") or next(
            (k.split(":", 1)[1] for k in (olgu.alanlar.get("kaynak") or []) if str(k).startswith("grid:")), None)
        if not algo_id:
            iz.yaz("Araştırma başlatılamadı.", "—", "", "",
                   "bot kimliği (algoId) bilinmiyor; olguda kaynak yok, araştırma başlatılamadı")
            return iz.no

        bulgu: dict = {}
        model = butce.model_sec(db, kullanici, ay, 3000, 1500 * EN_COK_ADIM) if istemci is not None else butce.KALIP
        model_karari = None
        if model != butce.KALIP:
            model_karari = _model(iz, araclar, algo_id, bulgu, istemci, model, a, kullanici, ay, db)
        if model == butce.KALIP or model_karari == "plana_gec":
            if model == butce.KALIP and istemci is not None:
                butce.yaz(db, kullanici, ay, butce.KALIP, 0, 0, Decimal(0), "tavan")
            _plan(iz, araclar, algo_id, bulgu)
            model_karari = None

        kod, metin = kod_karari(a, bulgu)
        if isinstance(model_karari, tuple):
            m_kod, m_gerekce = model_karari
            karar = metin + (" Model de aynı sonuca vardı." if m_kod == kod else
                             f" Model kararı ({m_kod}) kodla doğrulanamadı; kodun kararı yazıldı.")
            dusunce = m_gerekce
        else:
            karar, dusunce = metin, "Plan (kalıp): kayıt ile hesaba dönen parayı karşılaştırıyorum."
        sonuc = kalip.olgu_cumlesi(olgu) or "Uyarı cümlesi kurulamadı."
        iz.yaz(dusunce, "karar_ver", "", karar, sonuc)
        return iz.no


def ana(argv=None) -> int:
    ayr = argparse.ArgumentParser(description="proof1 araştıran anlatıcı")
    ayr.add_argument("--oturum", required=True)
    kip = ayr.add_mutually_exclusive_group(required=True)
    kip.add_argument("--kayit", help="kayıtlı ATK yanıtları (JSON)")
    kip.add_argument("--canli", action="store_true", help="ATK --read-only, alt hesap")
    ayr.add_argument("--algo-id")
    arg = ayr.parse_args(argv)
    _env_yukle()
    db = KOK_DIZIN / os.environ.get("PROOF1_DB", "data/proof1.db")
    istemci = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        istemci = anthropic.Anthropic()
    kullanici = os.environ.get("PROOF1_KULLANICI", "bugra")
    if arg.kayit:
        iz_no = arastir(db, arg.oturum, KayitliAraclar(arg.kayit), istemci, kullanici)
    else:
        from veri import ayar
        from veri.atk import Atk
        with closing(sqlite3.connect(db)) as cdb, Atk(ayar.okx_kimlik("alt"), cdb, arg.oturum) as atk:
            iz_no = arastir(db, arg.oturum, CanliAraclar(atk, arg.algo_id), istemci, kullanici)
    if not iz_no:
        print("Bu oturumda bot uyuşmazlığı yok; araştırma yapılmadı.")
        return 0
    with closing(sqlite3.connect(db)) as c:
        for sira, dusunce, arac, gozlem, karar, sonuc in c.execute(
                "SELECT sira, dusunce, arac, gozlem, karar, sonuc FROM iz WHERE iz_no=? ORDER BY sira", (iz_no,)):
            print(f"{sira}. {arac} · {sonuc}\n   gerekçe: {dusunce}\n   gözlem: {gozlem}\n   karar: {karar}")
    return 0


if __name__ == "__main__":
    sys.exit(ana())
