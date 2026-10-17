"""Süreç geneli hız sınırı. tr.okx.com yoğun okumada bağlantıyı kesiyor: saniyede en çok ~2,5 istek."""
import threading
import time


class Sinir:
    def __init__(self, aralik_sn: float):
        self.aralik = aralik_sn
        self._son = 0.0
        self._kilit = threading.Lock()

    def bekle(self):
        with self._kilit:
            fark = time.monotonic() - self._son
            if fark < self.aralik:
                time.sleep(self.aralik - fark)
            self._son = time.monotonic()


OKX = Sinir(0.4)
ETHERSCAN = Sinir(0.25)
GENEL = Sinir(0.2)
