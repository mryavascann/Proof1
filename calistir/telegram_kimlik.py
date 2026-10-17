"""TELEGRAM_CHAT_ID'yi bulur ve .env'e yazar. Önce Telegram'da bota /start yaz. Token ekrana basılmaz.

Birden çok sohbet bulunursa hiçbirini seçmez (alarmlar yanlış kişiye gitmesin): listeyi gösterir,
doğru olanı `python -m calistir.telegram_kimlik <id>` ile seçersin.

Çalıştır:  python -m calistir.telegram_kimlik
"""
import re
import sys

from calistir.telegram import Telegram
from veri import ayar


def sohbet_sec(guncellemeler: list[dict]) -> tuple[str | None, list[tuple[str, str]]]:
    sohbetler: dict = {}
    for g in guncellemeler:
        m = g.get("message") or g.get("my_chat_member") or {}
        c = m.get("chat") or {}
        if c.get("id"):
            sohbetler[str(c["id"])] = c.get("first_name") or c.get("title") or ""
    liste = list(sohbetler.items())
    return (liste[0][0] if len(liste) == 1 else None), liste


def _yaz(chat_id: str):
    yol = ayar.KOK / ".env"
    metin = yol.read_text(encoding="utf-8") if yol.exists() else ""
    if re.search(r"^TELEGRAM_CHAT_ID=.*$", metin, re.M):
        metin = re.sub(r"^TELEGRAM_CHAT_ID=.*$", f"TELEGRAM_CHAT_ID={chat_id}", metin, flags=re.M)
    else:
        metin += f"\nTELEGRAM_CHAT_ID={chat_id}\n"
    yol.write_text(metin, encoding="utf-8")


def main():
    from veri.ayar import konsol_utf8
    konsol_utf8()                      # Windows: '→' gibi karakterlerde çökmesin
    t = Telegram(chat_id="")
    if not t.token:
        print("TELEGRAM_BOT_TOKEN eksik (.env).")
        return
    if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit():
        _yaz(sys.argv[1])
        print("TELEGRAM_CHAT_ID yazıldı (elle seçildi).")
        return
    secilen, liste = sohbet_sec(t.guncellemeler())
    if not liste:
        print("Güncelleme yok (ya da Telegram'a ulaşılamadı): bota /start yaz, sonra yeniden çalıştır.")
    elif secilen is None:
        print("Birden çok sohbet bulundu; hiçbiri yazılmadı. Doğrusunu seç:  python -m calistir.telegram_kimlik <id>")
        for cid, ad in liste:
            print(f"  {cid}  {ad}")
    else:
        _yaz(secilen)
        print("TELEGRAM_CHAT_ID yazıldı (1 sohbet bulundu).")


if __name__ == "__main__":
    main()
