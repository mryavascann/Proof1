"""M2 kabul: mühürleme akışı (sahte RPC ile; ağ yok, anahtar yok)."""
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from eth_account import Account

from muhur import kok, muhurle

KOK_DIZIN = Path(__file__).resolve().parents[2]
ORNEK_DB = KOK_DIZIN / "ortak" / "ornek" / "proof1_ornek.db"
GUN = "2026-10-11"
MUHUR = "0x7C5aB869e8d972885673f19B848084279AAD0d48"


class SahteZincir:
    """Proof1Muhur'un okuma işlevlerini ve işlem gönderimini taklit eder."""

    def __init__(self, son_gun=0, son_kok=b"\x00" * 32):
        self.son_gun = son_gun
        self.kokler = {son_gun: son_kok} if son_gun else {}
        self.gonderilen = []

    def __call__(self, yontem, parametreler):
        if yontem == "eth_call":
            veri = bytes.fromhex(parametreler[0]["data"][2:])
            secici = veri[:4]
            if secici == muhurle.SECICI_LAST_DAY:
                return "0x" + self.son_gun.to_bytes(32, "big").hex()
            if secici == muhurle.SECICI_ROOT_OF:
                gun = int.from_bytes(veri[36:68], "big")
                return "0x" + self.kokler.get(gun, b"\x00" * 32).hex()
        if yontem == "eth_chainId":
            return hex(43113)
        if yontem == "eth_getTransactionCount":
            return "0x5"
        if yontem == "eth_gasPrice":
            return hex(25 * 10**9)
        if yontem == "eth_sendRawTransaction":
            self.gonderilen.append(parametreler[0])
            veri_gun = 20261011
            # Gönderilen kök, işlem çözülmeden kok hesabından bilinir; testte zincire yazılmış say.
            self.kokler[veri_gun] = self.beklenen_kok
            return "0x" + "ab" * 32
        if yontem == "eth_getTransactionReceipt":
            return {"status": "0x1", "blockNumber": "0x10"}
        raise AssertionError(f"beklenmeyen çağrı {yontem}")


class Muhurle(unittest.TestCase):
    def setUp(self):
        self.dizin = Path(tempfile.mkdtemp())
        self.db = self.dizin / "proof1.db"
        shutil.copy(ORNEK_DB, self.db)
        self.tuz = self.dizin / "tuzlar.json"
        self.anahtar = Account.create().key.hex()
        self.ayar = {"agent_id": 263, "muhur": MUHUR, "anahtar": self.anahtar, "ag": "fuji"}

    def tearDown(self):
        shutil.rmtree(self.dizin)

    def _beklenen(self, onceki):
        with closing(sqlite3.connect(self.db)) as db:
            return kok.gun_koku(kok.gun_satirlari(db, GUN), self.tuz, onceki)["kok"]

    def test_kuru_calisma_gondermez_yazmaz(self):
        zincir = SahteZincir()
        sonuc = muhurle.muhurle(GUN, self.db, self.tuz, self.ayar, zincir, gonder=False)
        self.assertEqual(zincir.gonderilen, [])
        self.assertEqual(sonuc["durum"], "hesaplandi")
        self.assertEqual(sonuc["kok"], self._beklenen(b"\x00" * 32))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("select count(*) from sqlite_master where name='muhur'").fetchone()[0], 0)

    def test_onceki_kok_zincirden(self):
        onceki = b"\x42" * 32
        zincir = SahteZincir(son_gun=20261010, son_kok=onceki)
        sonuc = muhurle.muhurle(GUN, self.db, self.tuz, self.ayar, zincir, gonder=False)
        self.assertEqual(sonuc["onceki"], onceki)
        self.assertEqual(sonuc["kok"], self._beklenen(onceki))

    def test_gonderim_imzali_ve_kayitli(self):
        zincir = SahteZincir()
        zincir.beklenen_kok = self._beklenen(b"\x00" * 32)
        sonuc = muhurle.muhurle(GUN, self.db, self.tuz, self.ayar, zincir, gonder=True)
        self.assertEqual(sonuc["durum"], "muhurlendi")
        self.assertEqual(len(zincir.gonderilen), 1)
        islem = Account.recover_transaction(zincir.gonderilen[0])
        self.assertEqual(islem, Account.from_key(self.anahtar).address)
        with closing(sqlite3.connect(self.db)) as db:
            satir = db.execute("select gun, kok, onceki_kok, islem_kimligi, agent_id, ag, sozlesme from muhur").fetchone()
        self.assertEqual(satir[0], GUN)
        self.assertEqual(satir[1], "0x" + zincir.beklenen_kok.hex())
        self.assertEqual(satir[3], "0x" + "ab" * 32)
        self.assertEqual(satir[4:], ("263", "fuji", MUHUR))

    def test_ayni_gun_zaten_muhurluyse_gondermez(self):
        beklenen = self._beklenen(b"\x00" * 32)
        zincir = SahteZincir(son_gun=20261011, son_kok=beklenen)
        sonuc = muhurle.muhurle(GUN, self.db, self.tuz, self.ayar, zincir, gonder=True)
        self.assertEqual(sonuc["durum"], "zaten_muhurlu")
        self.assertEqual(zincir.gonderilen, [])

    def test_gecmis_gun_reddedilir(self):
        zincir = SahteZincir(son_gun=20261017, son_kok=b"\x01" * 32)
        with self.assertRaises(muhurle.MuhurHatasi):
            muhurle.muhurle(GUN, self.db, self.tuz, self.ayar, zincir, gonder=True)
        self.assertEqual(zincir.gonderilen, [])


if __name__ == "__main__":
    unittest.main()
