"""Bant tıklaması: dinleyiciler her SVG'ye bir kez bağlanır.

17 Ekim provasında bantlar arasında hızlı tıklayınca sayfa dondu: panelAc() her çağrıda bagla() ile bütün
dinleyicileri yeniden ekliyordu; tıklama süreleri 17, 62, 171, 896, 3338, 13776 ms diye katlanıyordu.
Düzeltmeden sonra 200 hızlı tıklamada en uzunu 19 ms (tarayıcıda ölçüldü).
"""
import re
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "pano.js").read_text(encoding="utf-8")


def govde(ad: str) -> str:
    bas = JS.index(f"function {ad}(")
    derinlik, i = 0, JS.index("{", bas)
    for j in range(i, len(JS)):
        derinlik += {"{": 1, "}": -1}.get(JS[j], 0)
        if derinlik == 0:
            return JS[bas:j + 1]
    raise AssertionError(ad)


class BantTiklama(unittest.TestCase):
    def test_dinleyiciler_svg_basina_bir_kez(self):
        b = govde("bagla")
        self.assertIn('svg.getAttribute("data-bagli") !== "1"', b)
        korunan = b[b.index('svg.getAttribute("data-bagli") !== "1"'):]
        ilk_dinleyici = b.index("addEventListener")
        self.assertGreater(ilk_dinleyici, b.index('svg.getAttribute("data-bagli") !== "1"'))   # hepsi korumanın içinde
        self.assertEqual(len(re.findall(r"addEventListener", b)), len(re.findall(r"addEventListener", korunan)))

    def test_panel_acip_kapatmak_yeni_svg_uretmez(self):
        # panelAc / panelKapat şemayı yeniden çizmez; yalnız bagla() ile vurguyu günceller.
        for ad in ("panelAc", "panelKapat"):
            self.assertNotIn("sema()", govde(ad), ad)


if __name__ == "__main__":
    unittest.main()
