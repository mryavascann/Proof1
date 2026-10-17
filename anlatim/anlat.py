"""Anlatıcı: bir oturumun olgularını cümleye çevirir, sayı denetiminden geçirir, cumle tablosuna yazar.

    python -m anlatim.anlat --oturum sabah-2026-10-17

Sözleşme (ortak/SOZLESME.md · Çalıştırma bağı): Buğra'nın sabah işi bu komutu çalıştırır, 5 saniye bekler ve
`yer='telegram'` + `denetim='gecti'` satırını okur. Bu yüzden önce yalnız Telegram cümlesi istenir ve yazılır;
pano başlığı ikinci çağrıda (Sonnet), bant cümleleri onar onar sonraki çağrılarda (Haiku) gelir.

Model sayı üretmez: yalnız gizli olmayan olgular gönderilir, her cevap anlatim.denetim'den geçmezse
doğrulanmış kalıp cümle yazılır. Reddedilen ham cümle hiçbir yerde saklanmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from anlatim import butce, kalip
from anlatim.denetim import Olgu, denetle

KOK_DIZIN = Path(__file__).resolve().parents[1]
TELEGRAM_ZAMAN_ASIMI = 3.0   # Buğra 5 sn bekliyor; süreç açılışı (Windows) ve yazma için pay
DIGER_ZAMAN_ASIMI = 30.0
TELEGRAM_AZAMI_CIKTI = 600
DIGER_AZAMI_CIKTI = 4000
# Bant cümleleri çok (örnek veride ~50): tek çağrıda çıktı tavanına çarpıp kesiliyordu. Onar onar, Haiku ile.
BANT_PARCA = 10
OZET_TURLERI = {"cekim_ozet", "kopru"}

DUSUNME = {butce.SONNET: {"type": "between_tools"}, butce.HAIKU: {"type": "disabled"}}

SISTEM = """Sen proof1'ın anlatıcısısın. proof1 kullanıcının OKX TR hesabını ve zincirdeki adreslerini yalnız okur; \
emir vermez, para taşımaz, öğüt vermez. Görevin, sana verilen numaralı olguları kısa Türkçe cümlelere çevirmek.

Kurallar:
1) Yalnız verilen olgulara dayan; olgularda olmayan bilgiyi ekleme.
2) Sayıları olgulardan harfiyen kopyala: aynı rakamlar, aynı işaret (+ / -), aynı birim ya da token adı, aynı \
Türkçe biçim. Yuvarlama, toplama, çıkarma, çarpma ya da yüzde hesabı yapma; olgularda olmayan hiçbir sayıyı yazma. \
Tarih ve saatleri olgudaki gibi yaz.
3) Olgularda "tanınmadı", "bilinmiyor" ya da "yok" yazanı tahmin etme; bilinmediğini açıkça söyle.
4) Bakiye, toplam servet ya da yüzde uydurma; bunlar sana verilmez.
5) Öğüt verme. "Şunu yap", "kontrol et", "fırsat", "öneri" deme; "şu oldu" de. Yargısız, sakin yaz.
6) Kullanıcıya "sen" diye hitap et. Kısa, sade Türkçe kullan; görevin istediği cümle sayısını aşma.
7) Her görev için yalnız o görevin olgu listesinden, dayandığın olgu numaralarını "olgular" alanına yaz. \
Olgu numaralarını metne yazma.

Girdi bir JSON nesnesidir: "gorevler" (id, yer, cumle_sayisi, olgular) ve "olgular" (no, tur, alanlar).
Her görev için tam bir cevap ver: {"id": görev id, "metin": cümleler, "olgular": dayandığın olgu numaraları}."""

SEMA = {
    "type": "object",
    "properties": {"cevaplar": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "metin": {"type": "string"},
                       "olgular": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "metin", "olgular"], "additionalProperties": False}}},
    "required": ["cevaplar"], "additionalProperties": False,
}


def _simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def olgulari_oku(db: sqlite3.Connection, oturum: str) -> list[Olgu]:
    satirlar = db.execute("SELECT no, tur, alanlar, gizli FROM olgu WHERE oturum=?", (oturum,)).fetchall()
    olgular = [Olgu(no, tur, json.loads(alanlar), bool(gizli)) for no, tur, alanlar, gizli in satirlar]
    return sorted(olgular, key=lambda o: int(o.no[1:]) if o.no[1:].isdigit() else 0)


def ozet_olgulari(olgular: list[Olgu]) -> list[str]:
    """Telegram ve pano başlığı için en önemli olgular. Bot uyuşmazlığı varsa yalnız o (sahnenin canlı anı);
    yoksa dünden bugüne özet (önce toplam servet), sonra çekim özeti. Tanınmayan/şüpheli girişler başlığa girmez."""
    acik = [o for o in olgular if not o.gizli]
    bot = [o.no for o in acik if o.tur == "bot_uyusmazlik"]
    if bot:
        return bot[:1]
    sira = sorted((o for o in acik if o.tur == "kopru_ozet"), key=lambda o: o.alanlar.get("kapsam") != "servet")
    secilen = [o.no for o in sira[:1]] + [o.no for o in acik if o.tur == "cekim_ozet"][:1]
    if secilen:
        return secilen
    yedek, _ = kalip.ozet([o for o in acik if o.tur not in ("taninmadi", "supheli")], 1)
    return [o.no for o in acik if o.tur not in ("taninmadi", "supheli") and kalip.olgu_cumlesi(o) == yedek][:1]


def gorevler(olgular: list[Olgu]) -> list[dict]:
    if not any(not o.gizli for o in olgular):
        return []
    ozet = ozet_olgulari(olgular)
    liste = [{"id": "telegram", "yer": "telegram", "cumle_sayisi": 1, "olgular": ozet[:1]},
             {"id": "pano", "yer": "pano", "cumle_sayisi": len(ozet) or 1, "olgular": ozet}]
    if not ozet:
        liste = []
    for o in olgular:
        if o.gizli or o.tur in OZET_TURLERI or o.tur not in kalip.KALIPLAR:
            continue
        # Bant, olgunun kendi ağıdır: aynı adres birden çok EVM ağında kullanılabilir.
        etiket = o.alanlar.get("ag") or o.alanlar.get("adres") or o.alanlar.get("bot") or o.no
        liste.append({"id": f"bant-{o.no}", "yer": f"bant:{etiket}", "cumle_sayisi": 1, "olgular": [o.no]})
    return liste


def _istek(model: str, gorev_listesi: list[dict], olgular: list[Olgu], azami_cikti: int) -> dict:
    gerekli = {n for g in gorev_listesi for n in g["olgular"]}
    girdi = {"gorevler": gorev_listesi,
             "olgular": [{"no": o.no, "tur": o.tur, "alanlar": o.alanlar}
                         for o in olgular if o.no in gerekli and not o.gizli]}
    return {
        "model": model,
        "max_tokens": azami_cikti,
        "system": [{"type": "text", "text": SISTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": json.dumps(girdi, ensure_ascii=False)}],
        "thinking": DUSUNME[model],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SEMA}},
    }


def _kullanim(yanit) -> dict:
    u = getattr(yanit, "usage", None)
    return {k: int(getattr(u, k, 0) or 0) for k in
            ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}


def _modeli_cagir(db, istemci, gorev_listesi, olgular, kullanici, ay, zaman_asimi, azami_cikti, hizli=False):
    """(model, {görev id: cevap}, neden) döndürür; model 'kalip' ise çağrı yapılmamış ya da başarısızdır."""
    if istemci is None:
        return butce.KALIP, {}, "model anahtarı yok"
    tahmini_istek = _istek(butce.HAIKU, gorev_listesi, olgular, azami_cikti)
    girdi_tahmini = (len(SISTEM) + len(tahmini_istek["messages"][0]["content"])) // 2 + 200
    model = butce.model_sec(db, kullanici, ay, girdi_tahmini, azami_cikti, hizli=hizli)
    if model == butce.KALIP:
        butce.yaz(db, kullanici, ay, butce.KALIP, 0, 0, Decimal(0), "tavan")
        return butce.KALIP, {}, "bütçe tavanı"

    import anthropic
    istek = _istek(model, gorev_listesi, olgular, azami_cikti)
    try:
        yanit = istemci.with_options(timeout=zaman_asimi, max_retries=0).messages.create(**istek)
    except anthropic.APITimeoutError:
        butce.yaz(db, kullanici, ay, model, 0, 0, Decimal(0), "zaman_asimi")
        return butce.KALIP, {}, f"zaman aşımı ({zaman_asimi:g} sn)"
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        butce.yaz(db, kullanici, ay, model, 0, 0, Decimal(0), "hata")
        return butce.KALIP, {}, f"API hatası: {type(e).__name__} {getattr(e, 'status_code', '')}".strip()

    kullanim = _kullanim(yanit)
    durum = {"end_turn": "ok", "refusal": "red", "max_tokens": "kesik"}.get(yanit.stop_reason, str(yanit.stop_reason))
    butce.yaz(db, kullanici, ay, model,
              kullanim["input_tokens"] + kullanim["cache_read_input_tokens"] + kullanim["cache_creation_input_tokens"],
              kullanim["output_tokens"], butce.tutar_tl(model, kullanim), durum)
    if durum != "ok":
        return butce.KALIP, {}, f"model durdu: {yanit.stop_reason}"
    try:
        metin = next(b.text for b in yanit.content if getattr(b, "type", "") == "text")
        cevaplar = json.loads(metin)["cevaplar"]
    except (StopIteration, ValueError, KeyError, TypeError):
        return butce.KALIP, {}, "model cevabı JSON değil"
    return model, {c.get("id"): c for c in cevaplar if isinstance(c, dict)}, ""


def _cumle_tablosu(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS cumle (
        id INTEGER PRIMARY KEY, oturum TEXT, olgular TEXT, metin TEXT, model TEXT,
        denetim TEXT, yer TEXT, zaman TEXT)""")


def _gunluge(kayit: dict) -> None:
    """Teşhis günlüğü (data/ altında, depoya girmez). Reddedilen ham cümle yazılmaz; yalnız neden."""
    yol = Path(os.environ.get("PROOF1_ANLATICI_GUNLUK") or KOK_DIZIN / "data" / "anlatici_gunluk.jsonl")
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": _simdi(), **kayit}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _yaz(db, oturum, gorev, olgular, model, cevaplar, neden="", sure_ms=0) -> dict | None:
    olgu_haritasi = {o.no: o for o in olgular}
    yetkili = [olgu_haritasi[n] for n in gorev["olgular"]]
    gizliler = [o for o in olgular if o.gizli]
    cevap = cevaplar.get(gorev["id"])
    if model != butce.KALIP and not cevap:
        neden = "modelin cevabında bu görev yok"
    elif model != butce.KALIP:
        sonuc = denetle(cevap, yetkili + gizliler)
        neden = "" if sonuc.gecti else f"denetim: {sonuc.neden}"
    if model != butce.KALIP and cevap and not neden:
        metin, dayanak, kayit_modeli, durum = cevap["metin"].strip(), list(cevap["olgular"]), model, "gecti"
    else:
        metin, dayanak = kalip.ozet(yetkili, gorev["cumle_sayisi"])
        kayit_modeli, durum = butce.KALIP, "kalip"
    _gunluge({"oturum": oturum, "gorev": gorev["id"], "yer": gorev["yer"], "model": model, "sonuc": durum,
              "neden": neden, "sure_ms": sure_ms})
    if not metin:
        return None
    db.execute("INSERT INTO cumle (oturum, olgular, metin, model, denetim, yer, zaman) VALUES (?,?,?,?,?,?,?)",
               (oturum, json.dumps(dayanak), metin, kayit_modeli, durum, gorev["yer"], _simdi()))
    db.commit()
    return {"yer": gorev["yer"], "metin": metin, "model": kayit_modeli, "denetim": durum}


def anlat(db_yolu, oturum: str, istemci, kullanici: str = "bugra", ay: str | None = None) -> list[dict]:
    ay = ay or datetime.now(timezone.utc).strftime("%Y-%m")
    yazilan = []
    with closing(sqlite3.connect(db_yolu)) as db:
        _cumle_tablosu(db)
        olgular = olgulari_oku(db, oturum)
        liste = gorevler(olgular)
        if not liste:
            return yazilan
        # Oturumun cümleleri her çalıştırmada baştan yazılır (cumle tablosu Merve'nin).
        db.execute("DELETE FROM cumle WHERE oturum=?", (oturum,))
        db.commit()
        # Telegram: Haiku, 3 sn. Pano başlığı: Sonnet. Bantlar: Haiku, onar onar (çıktı kesilmesin).
        ust = [g for g in liste if not g["id"].startswith("bant-")]
        bantlar = [g for g in liste if g["id"].startswith("bant-")]
        asamalar = [(ust[:1], TELEGRAM_ZAMAN_ASIMI, TELEGRAM_AZAMI_CIKTI, True),
                    (ust[1:], DIGER_ZAMAN_ASIMI, DIGER_AZAMI_CIKTI, False)]
        asamalar += [(bantlar[i:i + BANT_PARCA], DIGER_ZAMAN_ASIMI, DIGER_AZAMI_CIKTI, True)
                     for i in range(0, len(bantlar), BANT_PARCA)]
        for gorev_listesi, zaman_asimi, azami_cikti, hizli in asamalar:
            if not gorev_listesi:
                continue
            bas = time.monotonic()
            model, cevaplar, neden = _modeli_cagir(db, istemci, gorev_listesi, olgular, kullanici, ay,
                                                   zaman_asimi, azami_cikti, hizli)
            sure_ms = int((time.monotonic() - bas) * 1000)
            for g in gorev_listesi:
                satir = _yaz(db, oturum, g, olgular, model, cevaplar, neden, sure_ms)
                if satir:
                    yazilan.append(satir)
    return yazilan


def _env_yukle() -> None:
    yol = KOK_DIZIN / ".env"
    if not yol.exists():
        return
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        ad, deger = satir.split("=", 1)
        deger = deger.split(" #")[0].strip()
        if deger and ad.strip() not in os.environ:
            os.environ[ad.strip()] = deger


def ana(argv=None) -> int:
    ayr = argparse.ArgumentParser(description="proof1 anlatıcı")
    ayr.add_argument("--oturum", required=True)
    arg = ayr.parse_args(argv)
    _env_yukle()
    db = KOK_DIZIN / os.environ.get("PROOF1_DB", "data/proof1.db")
    istemci = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        istemci = anthropic.Anthropic()
    kullanici = os.environ.get("PROOF1_KULLANICI", "bugra")
    for s in anlat(db, arg.oturum, istemci, kullanici=kullanici):
        print(f"[{s['yer']}] {s['denetim']} · {s['model']} · {s['metin']}")
    # Bot uyuşmazlığı varsa araştırma izi (cümlelerden sonra; Telegram'ı geciktirmez).
    #   PROOF1_ARASTIR=canli → ATK --read-only (alt hesap) · kayit → kayıtlı yanıtlar · boş → yapılmaz
    kip = os.environ.get("PROOF1_ARASTIR", "").strip().lower()
    if kip in ("canli", "kayit"):
        from anlatim import arastir
        try:
            if kip == "kayit":
                yol = os.environ.get("PROOF1_ARASTIR_KAYIT") or str(KOK_DIZIN / "anlatim" / "kayit" / "bot_16_ekim.json")
                arastir.arastir(db, arg.oturum, arastir.KayitliAraclar(yol), istemci, kullanici)
            else:
                from veri import ayar
                from veri.atk import Atk
                with closing(sqlite3.connect(db)) as cdb, Atk(ayar.okx_kimlik("alt"), cdb, arg.oturum) as atk:
                    arastir.arastir(db, arg.oturum, arastir.CanliAraclar(atk), istemci, kullanici)
        except Exception as e:  # araştırma düşerse cümleler yine yazılmış olur
            print(f"Araştırma tamamlanamadı: {type(e).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(ana())
