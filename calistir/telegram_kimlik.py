"""TELEGRAM_CHAT_ID'yi bulur ve .env'e yazar. Önce Telegram'da bota /start yaz. Token ekrana basılmaz.

Çalıştır:  python -m calistir.telegram_kimlik
"""
import re

from calistir.telegram import Telegram
from veri import ayar


def main():
    t = Telegram(chat_id="")
    if not t.token:
        print("TELEGRAM_BOT_TOKEN eksik (.env).")
        return
    sohbetler = {}
    for g in t.guncellemeler():
        m = g.get("message") or g.get("my_chat_member") or {}
        c = m.get("chat") or {}
        if c.get("id"):
            sohbetler[c["id"]] = c.get("first_name") or c.get("title") or ""
    if not sohbetler:
        print("Güncelleme yok: Telegram'da bota /start yaz, sonra yeniden çalıştır.")
        return
    chat_id = str(list(sohbetler)[-1])
    yol = ayar.KOK / ".env"
    metin = yol.read_text(encoding="utf-8") if yol.exists() else ""
    if re.search(r"^TELEGRAM_CHAT_ID=.*$", metin, re.M):
        metin = re.sub(r"^TELEGRAM_CHAT_ID=.*$", f"TELEGRAM_CHAT_ID={chat_id}", metin, flags=re.M)
    else:
        metin += f"\nTELEGRAM_CHAT_ID={chat_id}\n"
    yol.write_text(metin, encoding="utf-8")
    print(f"TELEGRAM_CHAT_ID yazıldı ({len(sohbetler)} sohbet bulundu).")


if __name__ == "__main__":
    main()
