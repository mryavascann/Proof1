"""OKX Agent Trade Kit (ATK) yerel MCP istemcisi. Sunucu her zaman --read-only ile başlatılır."""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from veri import hiz
from veri.ayar import OkxKimlik
from veri.kayit import cagri_kaydi

MODULLER = "market,account,spot,bot.grid"
# Salt okuma kipinde bile bir yazma aracı görünürse bağlantı reddedilir.
YAZMA_IZLERI = ("place", "cancel", "amend", "create", "stop", "transfer", "withdraw", "close",
                "set_", "_set", "adjust", "batch_", "purchase", "redeem", "order_algo", "grid_order_")


class AtkHata(Exception):
    def __init__(self, kod: str, mesaj: str = ""):
        super().__init__(f"ATK {kod} {mesaj}".strip())
        self.kod = kod


def sunucu_komutu() -> list[str]:
    giris = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@okx_ai" / "okx-trade-mcp" / "dist" / "index.js"
    temel = ["node", str(giris)] if giris.exists() else [shutil.which("okx-trade-mcp") or "okx-trade-mcp"]
    return temel + ["--site", "tr", "--read-only", "--modules", MODULLER]


YAZMA_YETKILERI = ("trade", "withdraw")


def yetki_denetle(perm: str) -> None:
    """OKX anahtarının yetkisi (account_get_config.perm, ör. 'read_only,trade'): işlem ya da çekim varsa reddet."""
    yetkiler = {p.strip().lower() for p in str(perm or "").split(",") if p.strip()}
    yazan = sorted(yetkiler & set(YAZMA_YETKILERI))
    if yazan:
        raise AtkHata("yazma_yetkili_anahtar", "anahtar şu yetkileri taşıyor: " + ",".join(yazan) + " — proof1 yalnız okuma anahtarıyla çalışır")


def yazma_araci_mi(ad: str) -> bool:
    ad = ad.lower()
    if ad.endswith(("_get", "_list")) or "_get_" in ad or ad.startswith(("get_", "market_")):
        return False
    return any(iz in ad for iz in YAZMA_IZLERI)


class Atk:
    def __init__(self, kimlik: OkxKimlik, db=None, oturum: str | None = None, yetki_denetimi: bool = True):
        self.k = kimlik
        self.db = db
        self.oturum = oturum
        self.surec: subprocess.Popen | None = None
        self._kuyruk: queue.Queue = queue.Queue()
        self._no = 0
        self.araclar: list[str] = []
        self.yetki_denetimi = yetki_denetimi
        self.yetki = "bilinmiyor"         # OKX'in bildirdiği anahtar yetkisi (kanıt panelinde gösterilir)

    # --- süreç ---
    def _ortam(self) -> dict:
        ortam = dict(os.environ)
        for ad in list(ortam):
            if ad.startswith(("OKX_TR_", "ONCHAINOS_", "TELEGRAM_", "ANTHROPIC_", "PROOF1_FUJI")):
                ortam.pop(ad)
        ortam["OKX_SITE"] = "tr"
        if self.k.kaynak == "profil" and self.k.profil_dizini:
            ortam["USERPROFILE"] = str(self.k.profil_dizini)
            ortam["HOME"] = str(self.k.profil_dizini)
            for ad in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE"):
                ortam.pop(ad, None)
        else:
            ortam["OKX_API_KEY"] = self.k.api_key
            ortam["OKX_SECRET_KEY"] = self.k.secret_key
            ortam["OKX_PASSPHRASE"] = self.k.passphrase
        return ortam

    def _oku(self):
        for satir in self.surec.stdout:
            satir = satir.strip()
            if satir:
                try:
                    self._kuyruk.put(json.loads(satir))
                except ValueError:
                    pass

    def _gonder(self, mesaj: dict):
        self.surec.stdin.write(json.dumps(mesaj) + "\n")
        self.surec.stdin.flush()

    def _rpc(self, yontem: str, params: dict, sure: float = 30.0):
        self._no += 1
        no = self._no
        self._gonder({"jsonrpc": "2.0", "id": no, "method": yontem, "params": params})
        bitis = time.monotonic() + sure
        while time.monotonic() < bitis:
            try:
                m = self._kuyruk.get(timeout=max(0.05, bitis - time.monotonic()))
            except queue.Empty:
                break
            if m.get("id") == no:
                if "error" in m:
                    raise AtkHata(str(m["error"].get("code")), str(m["error"].get("message", ""))[:120])
                return m.get("result", {})
        raise AtkHata("zaman_asimi", yontem)

    def baslat(self) -> "Atk":
        self.surec = subprocess.Popen(sunucu_komutu(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=self._ortam())
        threading.Thread(target=self._oku, daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "proof1-veri", "version": "0.1"}})
        self._gonder({"jsonrpc": "2.0", "method": "notifications/initialized"})
        with cagri_kaydi(self.db, "ATK", "tools/list", {"modules": MODULLER, "read_only": True}, self.oturum) as c:
            sonuc = self._rpc("tools/list", {})
            self.araclar = [a["name"] for a in sonuc.get("tools", [])]
            c.satir = len(self.araclar)
            c.alanlar = ["name"]
        yazanlar = [a for a in self.araclar if yazma_araci_mi(a)]
        if yazanlar:
            self.kapat()
            raise AtkHata("yazma_araci", ",".join(yazanlar))
        if self.yetki_denetimi and "account_get_config" in self.araclar:
            # İkinci kilit: sunucu salt okuma kipinde olsa bile anahtarın kendisi yazamamalı.
            for _ in range(2):
                try:
                    c = satirlar(self.cagir("account_get_config", {}, alanlar=["perm"]))
                    self.yetki = str(c[0].get("perm") or "bilinmiyor") if c else "bilinmiyor"
                    break
                except AtkHata:
                    time.sleep(1)                       # geçici hata: bir kez daha; bilinmiyorsa çalışmayı kesmez
            if self.yetki != "bilinmiyor":
                try:
                    yetki_denetle(self.yetki)
                except AtkHata:
                    self.kapat()
                    raise
        return self

    def kapat(self):
        if self.surec and self.surec.poll() is None:
            self.surec.terminate()
            try:
                self.surec.wait(5)
            except subprocess.TimeoutExpired:
                self.surec.kill()
        if self.surec:
            for akis in (self.surec.stdin, self.surec.stdout):
                try:
                    akis.close()
                except (OSError, ValueError):
                    pass

    def canli_mi(self) -> bool:
        return self.surec is not None and self.surec.poll() is None

    def yeniden_baslat(self) -> "Atk":
        """Node süreci öldüyse (ya da cevap vermiyorsa) MCP sunucusunu yeniden kurar; yine --read-only."""
        self.kapat()
        self._kuyruk = queue.Queue()
        return self.baslat()

    def __enter__(self):
        return self.baslat()

    def __exit__(self, *a):
        self.kapat()

    # --- araç çağrısı ---
    def cagir(self, arac: str, argumanlar: dict | None = None, alanlar: list[str] | None = None):
        if arac not in self.araclar:
            raise AtkHata("bilinmeyen_arac", arac)
        argumanlar = argumanlar or {}
        with cagri_kaydi(self.db, "ATK", arac, argumanlar, self.oturum) as c:
            for deneme in (1, 2):
                hiz.OKX.bekle()
                sonuc = self._rpc("tools/call", {"name": arac, "arguments": argumanlar}, sure=45)
                metin = "".join(p.get("text", "") for p in sonuc.get("content", []) if p.get("type") == "text")
                if sonuc.get("isError"):
                    if ("504" in metin or "Retry later" in metin) and deneme == 1:
                        time.sleep(5)
                        continue
                    c.kod = _hata_kodu(metin)
                    raise AtkHata(c.kod, metin[:160])
                break
            veri = _coz(metin, sonuc)
            satirlar = _satirlar(veri)
            c.satir = len(satirlar) if satirlar is not None else None
            c.alanlar = alanlar or (sorted({k for s in (satirlar or [])[:5] if isinstance(s, dict) for k in s}))
            return veri


def _hata_kodu(metin: str) -> str:
    try:
        j = json.loads(metin)
        return str(j.get("code") or j.get("error", {}).get("code") or "hata")
    except (ValueError, AttributeError):
        return "504" if "504" in metin else "hata"


def _coz(metin: str, sonuc: dict):
    if "structuredContent" in sonuc:
        return sonuc["structuredContent"]
    try:
        return json.loads(metin)
    except ValueError:
        return metin


def _satirlar(veri):
    """ATK cevabındaki satır listesini bulur ({data:[...]} ya da doğrudan liste)."""
    if isinstance(veri, list):
        return veri
    if isinstance(veri, dict):
        for anahtar in ("data", "result", "items"):
            v = veri.get(anahtar)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                ic = _satirlar(v)
                if ic is not None:
                    return ic
    return None


def satirlar(veri) -> list[dict]:
    return _satirlar(veri) or []
