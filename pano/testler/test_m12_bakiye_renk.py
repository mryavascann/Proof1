"""17 Ekim geri bildirimi: OKX TR bakiyesi açık modda görünür (gizli modda "gizli"); para girişi altın, hesaptan çıkış
mavi; demo şeridi çekmecenin üstüne çıkmaz; bugün mühürlenmediyse son mühür doğrulanabilir hâlde gösterilir."""
import re
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from anlatim import anlat
from pano import veri

KOK = Path(__file__).resolve().parents[2]
STATIK = KOK / "pano" / "static"
ORNEK_DB = KOK / "ortak" / "ornek" / "proof1_ornek.db"
OTURUM = "sabah-2026-10-17"
JS = (STATIK / "pano.js").read_text(encoding="utf-8")
CSS = (STATIK / "pano.css").read_text(encoding="utf-8")
HTML = (STATIK / "index.html").read_text(encoding="utf-8")


def z(secici: str) -> int:
    m = re.search(re.escape(secici) + r"\s*\{[^}]*z-index:\s*(\d+)", CSS)
    assert m, secici
    return int(m.group(1))


class Bakiye(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yol = Path(tempfile.mkdtemp()) / "p.db"
        shutil.copy(ORNEK_DB, cls.yol)
        anlat.anlat(cls.yol, OTURUM, None, kullanici="bugra", ay="2026-10")

    def kalemler(self, gizli):
        with closing(sqlite3.connect(self.yol)) as db:
            r = veri.rapor(db, OTURUM, gizli=gizli)
        return r, [k["kalem"] for k in r["kopru"]["kapsamlar"]["borsa"]["kalemler"]]

    def test_acik_modda_borsa_bakiyesi_var_gizlide_yok(self):
        _, acik = self.kalemler(False)
        _, gizli = self.kalemler(True)
        self.assertIn("bitis", acik)                 # bugün 09.00 borsa seviyesi
        self.assertNotIn("bitis", gizli)

    def test_kalan_dolari_ayri_alan(self):
        r, _ = self.kalemler(False)
        if "kalan" in r:                             # örnek veride cüzdan seviyesi yoksa kalan hiç kurulmaz
            self.assertIn(r["kalan"]["dolar"], r["kalan"]["metin"])
        g, _ = self.kalemler(True)
        self.assertNotIn("kalan", g)

    def test_sayfa_bakiyeyi_ve_gizli_durumunu_yazar(self):
        self.assertIn('kalem === "bitis"', JS)
        self.assertIn("Bakiye gizli", JS)


class Renk(unittest.TestCase):
    def test_cikis_rengi_ve_lejant(self):
        self.assertRegex(CSS, r"--cikis:\s*#")
        self.assertIn('id="g-cikis"', JS)            # borsadan çıkan bant
        self.assertIn("taneCikis", JS)               # borsadan çıkan taneler mavi, cüzdana varınca altın
        self.assertIn('class="lejant"', HTML)

    def test_isaretli_tutarlar(self):
        self.assertIn("function isaretli(", JS)
        self.assertRegex(CSS, r"\.eksi\s*\{[^}]*var\(--cikis\)")
        self.assertRegex(CSS, r"\.arti\s*\{[^}]*var\(--altin")


class Katmanlar(unittest.TestCase):
    def test_serit_cekmecenin_altinda(self):
        self.assertGreater(z(".cekmece"), z(".ust"))
        self.assertGreater(z(".ust"), z(".kayit-serit"))
        # çekmece <main> dışında: main'in yığın bağlamına hapsolup şeridin altında kalmasın
        self.assertGreater(HTML.index('<aside class="cekmece"'), HTML.index("</main>"))


class SonMuhur(unittest.TestCase):
    def test_bugun_muhur_yoksa_son_muhur_dogrulanir(self):
        self.assertIn("mu.son[0]", JS)
        self.assertIn('api("/api/muhur-dogrula", { gun: hedefGun', JS)


if __name__ == "__main__":
    unittest.main()
