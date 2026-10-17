"""Telegram gönderimi (yalnız proof1'ın kendi botu → kullanıcının sohbeti). Token hiçbir kayda yazılmaz."""
import html

import requests

from veri import ayar
from veri.kayit import cagri_kaydi

API = "https://api.telegram.org/bot{token}/{yontem}"


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None, db=None, oturum: str | None = None, http=None):
        self.token = token if token is not None else ayar.al("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id if chat_id is not None else ayar.al("TELEGRAM_CHAT_ID")
        self.db = db
        self.oturum = oturum
        self.http = http or requests.Session()

    @property
    def hazir(self) -> bool:
        return bool(self.token and self.chat_id)

    def _post(self, yontem: str, govde: dict) -> dict | None:
        with cagri_kaydi(self.db, "Telegram", yontem, {k: v for k, v in govde.items() if k != "text"}, self.oturum,
                         salt_okunur=False) as c:
            try:
                r = self.http.post(API.format(token=self.token, yontem=yontem), json=govde, timeout=15)
            except requests.RequestException as e:
                c.sonuc, c.kod = "hata", type(e).__name__
                return None
            c.kod = str(r.status_code)
            if r.status_code != 200:
                c.sonuc = "hata"
                return None
            c.satir, c.alanlar = 1, ["message_id"]
            return r.json().get("result")

    def gonder(self, metin: str, parse_mode: str | None = None) -> dict | None:
        govde = {"chat_id": self.chat_id, "text": metin, "disable_web_page_preview": True}
        if parse_mode:
            govde["parse_mode"] = parse_mode
        return self._post("sendMessage", govde)

    def gonder_pano(self, cumle: str, baglanti: str) -> dict | None:
        """Tek cümle + “Panoyu aç”. Telegram localhost bağlantısını reddederse düz metin."""
        sonuc = self.gonder(f"{html.escape(cumle)}\n\n<a href=\"{html.escape(baglanti)}\">Panoyu aç</a>", parse_mode="HTML")
        if sonuc is None:
            sonuc = self.gonder(f"{cumle}\n\nPanoyu aç: {baglanti}")
        return sonuc

    def guncellemeler(self) -> list[dict]:
        with cagri_kaydi(self.db, "Telegram", "getUpdates", {}, self.oturum) as c:
            r = self.http.get(API.format(token=self.token, yontem="getUpdates"), timeout=15)
            c.kod = str(r.status_code)
            veri = r.json().get("result", []) if r.ok else []
            c.satir = len(veri)
            return veri
