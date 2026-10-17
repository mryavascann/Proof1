"""Bir günün defterini Avalanche Fuji'deki Proof1Muhur sözleşmesine mühürler.

    python -m muhur.muhurle --gun 2026-10-11            # yalnız hesaplar
    python -m muhur.muhurle --gun 2026-10-11 --gonder   # Fuji'ye yazar, muhur tablosuna kaydeder

Ortam: PROOF1_DB, PROOF1_TUZ (öntanımlı data/muhur_tuzlari.json), FUJI_RPC_URL, PROOF1_AGENT_ID,
PROOF1_SEAL_ADDRESS, PROOF1_FUJI_PRIVATE_KEY. Zincire yalnız kök gider; adres ya da tutar gitmez.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from eth_abi import encode
from eth_account import Account
from eth_utils import keccak

from muhur import kok

KOK_DIZIN = Path(__file__).resolve().parents[1]
FUJI_ZINCIR = 43113
GAZ_SINIRI = 200_000
SECICI_LAST_DAY = keccak(text="lastDay(uint256)")[:4]
SECICI_ROOT_OF = keccak(text="rootOf(uint256,uint32)")[:4]
GEZGIN = "https://testnet.snowtrace.io/tx/"


class MuhurHatasi(Exception):
    pass


def _tls_baglami() -> ssl.SSLContext:
    # python.org macOS kurulumları sistem sertifikalarını görmeyebilir; certifi varsa onu kullan.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def http_rpc(url: str):
    baglam = _tls_baglami()

    def cagir(yontem, parametreler):
        istek = urllib.request.Request(
            url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": yontem, "params": parametreler}).encode(),
            headers={"content-type": "application/json", "user-agent": "proof1-muhur"})
        try:
            with urllib.request.urlopen(istek, timeout=30, context=baglam) as yanit:
                govde = json.load(yanit)
        except (urllib.error.URLError, TimeoutError) as e:
            raise MuhurHatasi(f"{yontem}: RPC'ye ulaşılamadı ({e})") from e
        if "error" in govde:
            raise MuhurHatasi(f"{yontem}: {govde['error'].get('message')}")
        return govde["result"]
    return cagir


def _oku(rpc, muhur: str, veri: bytes) -> bytes:
    return bytes.fromhex(rpc("eth_call", [{"to": muhur, "data": "0x" + veri.hex()}, "latest"])[2:])


def zincir_durumu(rpc, muhur: str, agent_id: int, gun: int) -> tuple[int, bytes, bytes]:
    """(son mühürlü gün, son kök, bu günün kökü) döndürür."""
    son_gun = int.from_bytes(_oku(rpc, muhur, SECICI_LAST_DAY + encode(["uint256"], [agent_id])), "big")
    son_kok = _oku(rpc, muhur, SECICI_ROOT_OF + encode(["uint256", "uint32"], [agent_id, son_gun])) if son_gun else kok.SIFIR
    bu_gun = _oku(rpc, muhur, SECICI_ROOT_OF + encode(["uint256", "uint32"], [agent_id, gun]))
    return son_gun, son_kok, bu_gun


def _makbuz_bekle(rpc, islem: str, sure: int = 90) -> dict:
    bitis = time.time() + sure
    while time.time() < bitis:
        makbuz = rpc("eth_getTransactionReceipt", [islem])
        if makbuz:
            return makbuz
        time.sleep(2)
    raise MuhurHatasi(f"makbuz gelmedi: {islem}")


def _yerel_onceki(db_yolu, gun: str) -> list[bytes]:
    with closing(sqlite3.connect(db_yolu)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='muhur'").fetchone():
            return []
        return [bytes.fromhex(r[0][2:]) for r in db.execute(
            "SELECT onceki_kok FROM muhur WHERE gun = ? ORDER BY zaman DESC", (gun,)) if r[0]]


def muhurle(gun: str, db_yolu, tuz_yolu, ayar: dict, rpc, gonder: bool) -> dict:
    gun_no = kok.gun_sayi(gun)
    son_gun, son_kok, bu_gun = zincir_durumu(rpc, ayar["muhur"], ayar["agent_id"], gun_no)

    if bu_gun != kok.SIFIR:
        onceki = kok.SIFIR  # zincirdeki kaydın önceki kökünü olaydan okumak yerine yeniden hesapla
    elif son_gun and gun_no < son_gun:
        raise MuhurHatasi(f"{gun} zincirdeki son mühürden ({son_gun}) eski; sözleşme geriye yazmaz")
    else:
        onceki = son_kok

    with closing(sqlite3.connect(db_yolu)) as db:
        satirlar = kok.gun_satirlari(db, gun)

    if bu_gun != kok.SIFIR:
        # Zaten mühürlü: hangi önceki kökle yazıldıysa onunla eşleşmeli. Aday: yerel kayıt, son kök, sıfır.
        adaylar = _yerel_onceki(db_yolu, gun) + [son_kok, kok.SIFIR]
        for aday in adaylar:
            hesap = kok.gun_koku(satirlar, tuz_yolu, aday)
            if hesap["kok"] == bu_gun:
                return {"durum": "zaten_muhurlu", "kok": hesap["kok"], "onceki": aday,
                        "yaprak_sayisi": hesap["yaprak_sayisi"]}
        return {"durum": "uyusmuyor", "kok": bu_gun, "onceki": None, "yaprak_sayisi": len(satirlar)}

    hesap = kok.gun_koku(satirlar, tuz_yolu, onceki)
    sonuc = {"durum": "hesaplandi", "kok": hesap["kok"], "onceki": onceki, "yaprak_sayisi": hesap["yaprak_sayisi"]}
    if not gonder:
        return sonuc

    if int(rpc("eth_chainId", []), 16) != FUJI_ZINCIR:
        raise MuhurHatasi("RPC Avalanche Fuji değil")
    hesap_ = Account.from_key(ayar["anahtar"])
    islem = {
        "to": ayar["muhur"],
        "data": kok.seal_cagri_verisi(ayar["agent_id"], gun_no, hesap["kok"]),
        "value": 0,
        "gas": GAZ_SINIRI,
        "gasPrice": max(int(rpc("eth_gasPrice", []), 16) * 2, 1),
        "nonce": int(rpc("eth_getTransactionCount", [hesap_.address, "latest"]), 16),
        "chainId": FUJI_ZINCIR,
    }
    imzali = hesap_.sign_transaction(islem)
    ham = imzali.raw_transaction if hasattr(imzali, "raw_transaction") else imzali.rawTransaction
    islem_kimligi = rpc("eth_sendRawTransaction", ["0x" + bytes(ham).hex()])
    makbuz = _makbuz_bekle(rpc, islem_kimligi)
    if makbuz.get("status") != "0x1":
        raise MuhurHatasi(f"mühür işlemi geri döndü: {islem_kimligi}")

    _, _, yazilan = zincir_durumu(rpc, ayar["muhur"], ayar["agent_id"], gun_no)
    if yazilan != hesap["kok"]:
        raise MuhurHatasi("zincirdeki kök hesaplananla aynı değil")

    with closing(sqlite3.connect(db_yolu)) as db:
        kok.muhur_yaz(db, {"gun": gun, "kok": "0x" + hesap["kok"].hex(), "onceki_kok": "0x" + onceki.hex(),
                           "islem_kimligi": islem_kimligi, "agent_id": str(ayar["agent_id"]),
                           "ag": ayar.get("ag", "fuji"), "sozlesme": ayar["muhur"]})
    sonuc.update(durum="muhurlendi", islem_kimligi=islem_kimligi)
    return sonuc


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
    from veri.ayar import konsol_utf8
    konsol_utf8()                      # Windows: '→' gibi karakterlerde çökmesin
    ayr = argparse.ArgumentParser(description="proof1 günlük defter mührü")
    ayr.add_argument("--gun", required=True, help="YYYY-MM-DD (Europe/Istanbul)")
    ayr.add_argument("--gonder", action="store_true", help="Fuji'ye yaz")
    arg = ayr.parse_args(argv)

    _env_yukle()
    gerekli = ["FUJI_RPC_URL", "PROOF1_AGENT_ID", "PROOF1_SEAL_ADDRESS"] + (["PROOF1_FUJI_PRIVATE_KEY"] if arg.gonder else [])
    eksik = [a for a in gerekli if not os.environ.get(a)]
    if eksik:
        print("Eksik ortam değişkeni: " + ", ".join(eksik), file=sys.stderr)
        return 2

    db = KOK_DIZIN / os.environ.get("PROOF1_DB", "data/proof1.db")
    tuz = KOK_DIZIN / os.environ.get("PROOF1_TUZ", "data/muhur_tuzlari.json")
    ayar = {"agent_id": int(os.environ["PROOF1_AGENT_ID"]), "muhur": os.environ["PROOF1_SEAL_ADDRESS"],
            "anahtar": os.environ.get("PROOF1_FUJI_PRIVATE_KEY"), "ag": "fuji"}
    try:
        s = muhurle(arg.gun, db, tuz, ayar, http_rpc(os.environ["FUJI_RPC_URL"]), arg.gonder)
    except MuhurHatasi as e:
        print(f"Mühür başarısız: {e}", file=sys.stderr)
        return 1
    print(f"gün {arg.gun} · {s['yaprak_sayisi']} satır · kök 0x{s['kok'].hex()} · durum {s['durum']}")
    if s.get("islem_kimligi"):
        print(f"işlem {GEZGIN}{s['islem_kimligi']}")
    return 0 if s["durum"] != "uyusmuyor" else 1


if __name__ == "__main__":
    sys.exit(ana())
