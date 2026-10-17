(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var AYLAR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  var durum = {
    rapor: null, gizli: true, secili: null, dar: null, ilk: true, kopruKapsam: "servet", ertelenen: {},
    oturum: new URLSearchParams(location.search).get("oturum"), bantlar: []
  };

  /* ---------- yardımcılar ---------- */
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function el(etiket, ozellik, cocuklar) {
    var e = document.createElement(etiket);
    if (ozellik) Object.keys(ozellik).forEach(function (k) {
      if (k === "metin") e.textContent = ozellik[k];
      else if (k === "sinif") e.className = ozellik[k];
      else e.setAttribute(k, ozellik[k]);
    });
    (cocuklar || []).forEach(function (c) { if (c) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  function ikon(ad) {
    var s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("class", "i"); s.setAttribute("aria-hidden", "true");
    var u = document.createElementNS("http://www.w3.org/2000/svg", "use"); u.setAttribute("href", "#i-" + ad); s.appendChild(u);
    return s;
  }
  function duyur(m) { $("duyuru").textContent = m; }
  // Gizli mod (devir metni): yalnız bakiye seviyeleri ve yüzdeler gizlidir; bunları sunucu rapora hiç koymaz.
  // Giren, çıkan ve aktarım tutarları görünür kalır; bu yüzden hareket tutarları burada maskelenmez.
  function m(metin) { return metin; }
  function gunTr(oturum) {
    var x = /(\d{4})-(\d{2})-(\d{2})$/.exec(oturum || "");
    return x ? (+x[3]) + " " + AYLAR[+x[2]] + " " + x[1] : oturum;
  }
  function zamanTr(iso) {
    var d = new Date(iso);
    return iso && !isNaN(d) ? d.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) : "";
  }
  function cumleEtiketi(c) { return c.denetim === "gecti" ? "Sayılar olgularla doğrulandı" : "Doğrulanmış kalıp cümle"; }

  /* ---------- veri ---------- */
  function yukle() {
    var q = new URLSearchParams();
    if (durum.oturum) q.set("oturum", durum.oturum);
    q.set("gizli", durum.gizli ? "1" : "0");
    $("pano").setAttribute("aria-busy", "true");
    return fetch("/api/rapor?" + q.toString(), { cache: "no-store" })
      .then(function (y) { return y.json().then(function (g) { if (!y.ok) throw new Error(g.hata || "okunamadı"); return g; }); })
      .then(function (r) { durum.rapor = r; durum.oturum = r.oturum; ciz(); })
      .catch(function (e) {
        $("tazelik").textContent = "Veri okunamadı";
        $("ozet").textContent = e.message === "Veri kaynağı hazırlanmadı." ? e.message : "Pano verisine ulaşılamadı. Sunucu çalışıyor mu?";
      })
      .finally(function () { $("pano").setAttribute("aria-busy", "false"); });
  }

  function ciz() {
    var r = durum.rapor, a = r.akis;
    $("tazelik").textContent = (r.veri_turu === "örnek" ? "Örnek veri" : "Canlı veri") + " · rapor " + gunTr(r.oturum) +
      (r.uretim ? " · son okuma " + zamanTr(r.uretim) : "");
    $("durum-satiri").textContent = "Oturum: " + r.oturum;
    $("donem").textContent = (a.donem || "Dönem bilinmiyor") + " · çekimler · " + a.birim;
    var ozet = r.ozet || [];
    $("ozet").textContent = ozet.length ? m(ozet.map(function (c) { return c.metin; }).join(" ")) : "Bu oturum için özet cümle yok.";
    $("ozet-durum").textContent = ozet.length ? cumleEtiketi(ozet[0]) + " · olgu " + ozet[0].olgular.join(", ") + ". " + a.not : a.not;
    var hap = $("durum-hap"), u = r.uyarilar;
    hap.hidden = false;
    if (u.toplam) {
      hap.className = "durum-hap";
      hap.innerHTML = "";
      hap.appendChild(ikon("uyari"));
      var ilk = u.liste[0];
      hap.appendChild(document.createTextNode(u.toplam + " uyarı" + (ilk && ilk.onem === "acil" ? " · " + (ilk.tur === "bot_uyusmazlik" ? "bot kaydı tutmuyor" : "acil") : "")));
    } else { hap.className = "durum-hap tamam"; hap.textContent = "Uyarı yok"; }
    var kalan = $("kalan");
    kalan.hidden = !r.kalan;
    if (r.kalan) kalan.textContent = r.kalan.metin + " " + r.kalan.not;
    durum.dar = $("sema").clientWidth < 520;
    sema(); tablo(); kopru(); uyarilar(); sahiplik();
    if (durum.secili !== null) panelAc(durum.secili, true);
    durum.ilk = false;
  }

  /* ---------- akış şeması: kaynak → Sen → ağlar ---------- */
  // Yeşil (giren) bandın içinde dalgalı damarlar: paranın akış yönünü gösterir.
  function damarlar(x1, y0, y1, x2) {
    var t = y1 - y0, n = t < 10 ? 0 : t < 30 ? 2 : t < 90 ? 4 : 7, s = "";
    if (!n) return s;
    var aralik = t / (n + 1);
    for (var i = 0; i < n; i++) {
      var yc = y0 + aralik * (i + 1);
      var dalga = 38 + (i % 3) * 9;                       // dalga boyu
      var genlik = Math.min(aralik * 0.32, 3 + (i % 2) * 1.5);
      var x = x1 - (i * 13) % dalga;                       // her damar farklı evrede başlar
      var d = "M" + x.toFixed(1) + "," + yc.toFixed(1) + " Q" + (x + dalga / 4).toFixed(1) + "," + (yc - 2 * genlik).toFixed(1) +
        " " + (x + dalga / 2).toFixed(1) + "," + yc.toFixed(1);
      for (x += dalga / 2; x < x2; x += dalga / 2) d += " T" + Math.min(x + dalga / 2, x2 + dalga / 2).toFixed(1) + "," + yc.toFixed(1);
      var gecik = -((i * 0.73) % 4.2).toFixed(2);
      s += '<path class="damar' + (i % 2 ? " ince" : "") + '" style="animation-delay:' + gecik + 's" d="' + d + '"/>';
    }
    return '<g clip-path="url(#damar-kirp)">' + s + "</g>";
  }
  function bantYolu(x1, a0, a1, x2, b0, b1) {
    var xm = (x1 + x2) / 2;
    return "M" + x1 + "," + a0 + " C" + xm + "," + a0 + " " + xm + "," + b0 + " " + x2 + "," + b0 +
      " L" + x2 + "," + b1 + " C" + xm + "," + b1 + " " + xm + "," + a1 + " " + x1 + "," + a1 + " Z";
  }

  function sema() {
    var r = durum.rapor, a = r.akis, kutu = $("sema"), dar = durum.dar, gruplar = a.gruplar, n = gruplar.length;
    kutu.innerHTML = "";
    if (!n) { kutu.appendChild(el("p", { sinif: "not", metin: "Bu dönemde çekim akışı yok." })); return; }
    var W = dar ? 340 : 680, nw = 8, xL = dar ? 4 : 132, xM = dar ? 108 : 330, xR = dar ? 206 : 520, ust = 34, aralik = dar ? 12 : 16;
    var toplam = gruplar.reduce(function (s, g) { return s + g.deger; }, 0) || 1;
    var Hb = Math.max(dar ? 250 : 300, n * (dar ? 46 : 54));
    var k = (Hb - aralik * (n - 1)) / toplam, y = ust;
    var sag = gruplar.map(function (g) { var t = Math.max(2, g.deger * k), o = { g: g, y0: y, y1: y + t, t: t }; y += t + aralik; return o; });
    var akisT = sag.reduce(function (s, o) { return s + o.t; }, 0);
    var mTop = ust + (y - aralik - ust - akisT) / 2;
    var etiketY = [], son = -Infinity;
    sag.forEach(function (o) { var v = Math.max((o.y0 + o.y1) / 2, son + 38); etiketY.push(v); son = v; });
    var H = Math.max(y - aralik, son + 22) + 6;

    var bantlar = [], s = "";
    var kay = a.kaynak, solAria = "OKX TR → Sen: " + m(kay.tutar || "") + ", " + kay.cekim_sayisi + " çekim";
    bantlar.push({ tur: "kaynak", d: bantYolu(xL + nw, mTop, mTop + akisT, xM, mTop, mTop + akisT),
      v: damarlar(xL + nw, mTop, mTop + akisT, xM), aria: solAria });
    var my = mTop;
    sag.forEach(function (o) {
      var a0 = my, a1 = my + o.t; my = a1;
      bantlar.push({ tur: "grup", g: o.g, d: bantYolu(xM + nw, a0, a1, xR, o.y0, o.y1), v: "",
        aria: "Sen → " + o.g.ad + ": " + (o.g.tutar ? m(o.g.tutar) : o.g.alt.length + " ağ") + (o.g.cekim_sayisi ? ", " + o.g.cekim_sayisi + " çekim" : "") });
    });
    durum.bantlar = bantlar;
    // İlk çizimde bantlar soldan sağa açılır (SVG clipPath; azaltılmış harekette yok).
    var ac = durum.ilk && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (ac) {
      s += '<defs><clipPath id="acilis" clipPathUnits="userSpaceOnUse"><rect x="0" y="-10" width="0" height="' + (H + 20) + '">' +
        '<animate attributeName="width" from="0" to="' + (W + 4) + '" dur="0.9s" fill="freeze" calcMode="spline" keySplines="0.2 0.7 0.2 1" keyTimes="0;1"/></rect></clipPath></defs>';
    }
    s += '<defs><clipPath id="damar-kirp"><path d="' + bantlar[0].d + '"/></clipPath></defs>';
    s += '<g' + (ac ? ' clip-path="url(#acilis)"' : "") + ">";
    bantlar.forEach(function (b, i) {
      s += '<g class="bant' + (b.tur === "grup" ? " cikis" : "") + '" tabindex="' + (i === 0 ? 0 : -1) + '" role="button" data-i="' + i + '" aria-label="' + esc(b.aria) + '">' +
        '<path class="b" d="' + b.d + '"/>' + b.v +
        '<path d="' + b.d + '" fill="none" stroke="transparent" stroke-width="14" pointer-events="stroke"/></g>';
    });
    s += "</g>";
    // Düğümler
    s += '<rect x="' + xL + '" y="' + mTop + '" width="' + nw + '" height="' + akisT + '" rx="2" fill="var(--metin)"/>';
    s += '<rect x="' + xM + '" y="' + mTop + '" width="' + nw + '" height="' + akisT + '" rx="2" fill="var(--metin)"/>';
    sag.forEach(function (o, i) {
      s += '<rect x="' + xR + '" y="' + o.y0 + '" width="' + nw + '" height="' + o.t + '" rx="2" fill="var(--giden)"/>';
      var ly = etiketY[i], lx = xR + nw + 10;
      if (Math.abs(ly - (o.y0 + o.y1) / 2) > 4) s += '<path d="M' + (xR + nw + 2) + "," + (o.y0 + o.y1) / 2 + " L" + (lx - 3) + "," + (ly - 4) + '" stroke="var(--cizgi)" fill="none"/>';
      s += '<text x="' + lx + '" y="' + (ly - 3) + '" class="ad">' + esc(o.g.ad) + "</text>";
      s += '<text x="' + lx + '" y="' + (ly + 13) + '" class="tutar">' + esc(o.g.tutar ? m(o.g.tutar) : o.g.alt.length + " ağ") +
        (o.g.cekim_sayisi && !dar ? '<tspan class="kucuk"> · ' + esc(o.g.cekim_sayisi) + " çekim</tspan>" : "") + "</text>";
    });
    // Başlıklar ve kaynak / Sen etiketleri
    s += '<text x="' + (xM + nw / 2) + '" y="' + (mTop - 20) + '" text-anchor="middle" class="ad">Sen</text>';
    s += '<text x="' + (xM + nw / 2) + '" y="' + (mTop - 6) + '" text-anchor="middle" class="kucuk">' + esc(kay.adres_sayisi + " adres") + "</text>";
    if (!dar) {
      var ky = mTop + akisT / 2 - 18;
      s += '<text x="' + (xL - 10) + '" y="' + ky + '" text-anchor="end" class="ad">' + esc(kay.ad) + "</text>";
      s += '<text x="' + (xL - 10) + '" y="' + (ky + 17) + '" text-anchor="end" class="tutar">' + esc(m(kay.tutar || "")) + "</text>";
      s += '<text x="' + (xL - 10) + '" y="' + (ky + 33) + '" text-anchor="end" class="kucuk">' + esc(kay.cekim_sayisi + " çekim") + "</text>";
      s += '<text x="' + (xL - 10) + '" y="12" text-anchor="end" class="baslik">GELDİ</text>';
      s += '<text x="' + (xR + nw + 10) + '" y="12" class="baslik">GİTTİ</text>';
    } else {
      kutu.appendChild(el("p", { sinif: "kaynak-not", metin: "Geldi: " + kay.ad + " · " + m(kay.tutar || "") + " · " + kay.cekim_sayisi + " çekim" }));
    }
    var svg = '<svg viewBox="-2 -4 ' + (W + 4) + " " + (H + 8) + '" role="presentation">' + s + "</svg>";
    var sar = document.createElement("div");
    sar.innerHTML = svg;
    kutu.appendChild(sar.firstChild);
    bagla();
  }

  function okumaMetni(b) {
    var kay = durum.rapor.akis.kaynak;
    if (b.tur === "kaynak") return "<b>OKX TR → Sen</b> · " + esc(m(kay.tutar || "")) + " · " + esc(kay.cekim_sayisi) + " çekim · " + esc(kay.adres_sayisi) + " adrese";
    var g = b.g;
    return "<b>Sen → " + esc(g.ad) + "</b> · " + (g.tutar ? esc(m(g.tutar)) + " · " + esc(g.cekim_sayisi) + " çekim"
      : esc(g.alt.map(function (x) { return x.ad + " " + m(x.tutar); }).join(" · ")));
  }

  function bagla() {
    var svg = $("sema").querySelector("svg"), gs = Array.prototype.slice.call(svg.querySelectorAll(".bant"));
    function goster(i) {
      svg.classList.add("vurgu");
      gs.forEach(function (g, j) { g.classList.toggle("secili", j === i); });
      $("okuma").innerHTML = okumaMetni(durum.bantlar[i]);
    }
    function birak() {
      if (durum.secili !== null) return goster(durum.secili);
      svg.classList.remove("vurgu");
      gs.forEach(function (g) { g.classList.remove("secili"); });
      $("okuma").textContent = "Bantların üzerine gelince tutar burada görünür.";
    }
    gs.forEach(function (g, i) {
      g.addEventListener("mouseenter", function () { goster(i); });
      g.addEventListener("mouseleave", birak);
      g.addEventListener("focus", function () { goster(i); });
      g.addEventListener("blur", birak);
      g.addEventListener("click", function () { panelAc(i); });
      g.addEventListener("keydown", function (e) {
        var j = null;
        if (e.key === "ArrowDown" || e.key === "ArrowRight") j = (i + 1) % gs.length;
        if (e.key === "ArrowUp" || e.key === "ArrowLeft") j = (i - 1 + gs.length) % gs.length;
        if (j !== null) { e.preventDefault(); g.setAttribute("tabindex", "-1"); gs[j].setAttribute("tabindex", "0"); gs[j].focus(); }
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); panelAc(i); }
      });
    });
    if (durum.secili !== null && gs[durum.secili]) goster(durum.secili);
  }

  /* ---------- bant ayrıntısı ---------- */
  function kapsamListesi(k) {
    var d = el("div");
    if (!k || !k.adres) { d.appendChild(el("p", { sinif: "not", metin: "Bu ağda kayıtlı adres yok." })); return d; }
    d.appendChild(el("p", { sinif: "not", metin: k.adres + " adres" + (k.benim_tahmini ? " · " + k.benim_tahmini + " tanesi büyük olasılıkla senin (tahmin)" : "") }));
    k.katmanlar.forEach(function (x) { d.appendChild(el("div", { sinif: "katman" }, [ikon("tamam"), x])); });
    k.eksik.forEach(function (x) { d.appendChild(el("div", { sinif: "katman yok" }, [ikon("eksik"), x + ": okunamadı"])); });
    if (k.yalniz_cekim) d.appendChild(el("p", { sinif: "not", metin: "Bu ağda yalnız çekimi görüyorum." }));
    return d;
  }
  function cumleListesi(liste) {
    var d = el("div");
    if (!liste.length) { d.appendChild(el("p", { sinif: "not", metin: "Bu bant için doğrulanmış cümle yok." })); return d; }
    liste.forEach(function (c) {
      d.appendChild(el("div", { sinif: "cumle" }, [ikon("gelen"), el("p", { metin: m(c.metin) }),
        el("small", { metin: cumleEtiketi(c) + " · olgu " + c.olgular.join(", ") + (c.donem_notu ? " · " + c.donem_notu : "") })]));
    });
    return d;
  }
  function panelAc(i, sessiz) {
    var b = durum.bantlar[i], r = durum.rapor, ic = $("panel-icerik"), dl = el("dl", { sinif: "bilgi" });
    if (!b) return;
    durum.secili = i;
    ic.innerHTML = "";
    function satir(x, y) { dl.appendChild(el("dt", { metin: x })); dl.appendChild(el("dd", { metin: y })); }
    if (b.tur === "kaynak") {
      var kay = r.akis.kaynak;
      $("panel-baslik").textContent = "OKX TR → Sen";
      satir("Çekim toplamı", m(kay.tutar || "bilinmiyor") + " (çekim anındaki dolar karşılığı)");
      satir("Çekim", kay.cekim_sayisi + " kez, " + kay.adres_sayisi + " adrese");
      satir("Dönem", r.akis.donem || "bilinmiyor");
      satir("Kaynak", "olgu " + kay.olgular.join(", "));
      ic.appendChild(dl);
      ic.appendChild(el("p", { sinif: "not", metin: r.akis.not }));
      ic.appendChild(el("h4", { metin: "Ne oldu" }));
      ic.appendChild(cumleListesi((r.ozet || []).filter(function (c) { return c.olgular.some(function (o) { return kay.olgular.indexOf(o) >= 0; }); })));
    } else {
      var g = b.g;
      $("panel-baslik").textContent = "Sen → " + g.ad;
      if (g.tutar) satir("Çekim toplamı", m(g.tutar) + " (çekim anındaki dolar karşılığı)");
      if (g.cekim_sayisi) satir("Çekim sayısı", g.cekim_sayisi);
      satir("Dönem", r.akis.donem || "bilinmiyor");
      satir("Kaynak", "olgu " + g.olgular.join(", "));
      ic.appendChild(dl);
      (g.alt || [g]).forEach(function (x) {
        if (g.alt) ic.appendChild(el("h4", { metin: x.ad + " · " + m(x.tutar) + " · " + x.cekim_sayisi + " çekim" }));
        else ic.appendChild(el("h4", { metin: "Okunabilen katmanlar" }));
        ic.appendChild(kapsamListesi(x.kapsam));
        ic.appendChild(el("h4", { metin: "Ne oldu" }));
        ic.appendChild(cumleListesi(x.cumleler));
      });
    }
    $("panel").hidden = false;
    $("ozet-kolon").hidden = true;
    if (!sessiz) { $("panel").focus(); duyur($("panel-baslik").textContent + " ayrıntısı açıldı"); }
    bagla();
  }
  function panelKapat() {
    if ($("panel").hidden) return;
    var i = durum.secili;
    durum.secili = null;
    $("panel").hidden = true;
    $("ozet-kolon").hidden = false;
    bagla();
    var gs = $("sema").querySelectorAll(".bant");
    gs.forEach(function (g) { g.setAttribute("tabindex", "-1"); });
    if (gs[i]) { gs[i].setAttribute("tabindex", "0"); gs[i].focus(); }
  }

  function tablo() {
    var t = $("akis-tablo"), r = durum.rapor, kay = r.akis.kaynak, b = el("tbody");
    t.innerHTML = "";
    t.appendChild(el("thead", null, [el("tr", null, ["Akış", "Tutar (USD)", "Çekim", "Okunabilen katmanlar"].map(function (h) { return el("th", { metin: h }); }))]));
    b.appendChild(el("tr", null, [el("td", { metin: "OKX TR → Sen" }), el("td", { metin: m(kay.tutar || "") }), el("td", { metin: kay.cekim_sayisi }), el("td", { metin: "" })]));
    r.akis.gruplar.forEach(function (g) {
      (g.alt || [g]).forEach(function (x) {
        b.appendChild(el("tr", null, [el("td", { metin: "Sen → " + x.ad }), el("td", { metin: m(x.tutar || "") }), el("td", { metin: x.cekim_sayisi || "" }),
          el("td", { metin: x.kapsam && x.kapsam.adres ? x.kapsam.katmanlar.join(", ") : "adres yok" })]));
      });
    });
    t.appendChild(b);
  }

  /* ---------- dünden bugüne ---------- */
  function kopru() {
    var k = durum.rapor.kopru, sek = $("kopru-sekmeler"), ic = $("kopru-icerik");
    sek.innerHTML = ""; ic.innerHTML = "";
    if (!k) { $("kopru-not").textContent = "Karşılaştırma için en az iki günlük okuma gerekiyor."; return; }
    $("kopru-not").textContent = k.not;
    var adlar = Object.keys(k.kapsamlar);
    if (adlar.indexOf(durum.kopruKapsam) < 0) durum.kopruKapsam = adlar[0];
    adlar.forEach(function (ad) {
      var b = el("button", { type: "button", role: "tab", "aria-selected": String(ad === durum.kopruKapsam), metin: ad === "borsa" ? "Borsa" : "Toplam servet" });
      b.addEventListener("click", function () { durum.kopruKapsam = ad; kopru(); });
      sek.appendChild(b);
    });
    var kap = k.kapsamlar[durum.kopruKapsam], satirlar = el("div", { sinif: "satirlar", role: "tabpanel", "aria-label": kap.ad });
    if (!kap.ozet.length) satirlar.appendChild(el("p", { sinif: "not", metin: "Bu dönemde hareket yok; eldeki varlıkların fiyatı yine değişmiş olabilir." }));
    kap.ozet.forEach(function (o) {
      satirlar.appendChild(el("div", { sinif: "satir" }, [el("span", { metin: o.ad }),
        el("span", { sinif: "sag" }, [o.varliklar.length ? m(o.varliklar.join(" · ")) : "değişim yok",
          el("small", { metin: o.dolar ? m(o.dolar) : "Dolar karşılığı henüz yok" })])]));
    });
    ic.appendChild(satirlar);
    var liste = el("div", { sinif: "satirlar", hidden: "" }), acik = false;
    kap.kalemler.forEach(function (x) {
      liste.appendChild(el("div", { sinif: "satir" }, [el("span", null, [x.ad, el("small", { metin: x.aciklama })]),
        el("span", { sinif: "sag" }, [x.varliklar.length ? m(x.varliklar.join(" · ")) : "0",
          el("small", { metin: (x.dolar ? m(x.dolar) : "Dolar karşılığı henüz yok") + " · olgu " + x.olgular.join(", ") })])]));
    });
    var d = el("button", { type: "button", sinif: "baglanti", "aria-expanded": "false", metin: "Tüm kalemler (" + kap.kalemler.length + ")" });
    d.addEventListener("click", function () { acik = !acik; liste.hidden = !acik; d.setAttribute("aria-expanded", String(acik)); d.textContent = acik ? "Kalemleri gizle" : "Tüm kalemler (" + kap.kalemler.length + ")"; });
    ic.appendChild(d); ic.appendChild(liste);
  }

  /* ---------- uyarılar ---------- */
  function uyarilar() {
    var u = durum.rapor.uyarilar, ul = $("uyarilar"), ONEM = { acil: "Acil", orta: "Orta", bilgi: "Bilgi" };
    ul.innerHTML = "";
    if (!u.liste.length) ul.appendChild(el("li", { metin: "Uyarı yok." }));
    u.liste.forEach(function (x) {
      ul.appendChild(el("li", { sinif: x.onem }, [ikon("uyari"), el("div", null, [el("span", { sinif: "onem", metin: ONEM[x.onem] || x.onem }), m(x.metin)])]));
    });
    $("tum-uyarilar").hidden = u.toplam <= u.liste.length;
    $("tum-uyarilar").textContent = "Toplam " + u.toplam + " uyarı var; hepsi ayrıntılı modda.";
  }

  /* ---------- sahiplik ---------- */
  function sahiplik() {
    var liste = durum.rapor.sahiplik.filter(function (s) { return !durum.ertelenen[s.etiket + "|" + s.ag]; });
    $("sahiplik-bolum").hidden = !liste.length;
    var kap = $("sahiplik"), DURUM = { tahmin: "Tahmin: büyük olasılıkla senin", benim: "Sen doğruladın: senin", benim_degil: "Sen işaretledin: senin değil" };
    kap.innerHTML = "";
    liste.forEach(function (s) {
      var kart = el("div", { sinif: "kart" }), durumP = el("p", { sinif: "durum", metin: DURUM[s.durum] || s.durum }), sec = el("div", { sinif: "secenekler" });
      kart.appendChild(el("div", { sinif: "adres", metin: s.kisa + " · " + s.ag }));
      kart.appendChild(el("p", { metin: s.kanit }));
      kart.appendChild(durumP);
      function dugmeler() {
        sec.innerHTML = "";
        [["benim", "Benim"], ["benim_degil", "Benim değil"]].forEach(function (d, i) {
          var b = el("button", { type: "button", sinif: i === 0 ? "birincil" : "", metin: d[1] });
          b.addEventListener("click", function () { isaretle(s, d[0], durumP, sec); });
          sec.appendChild(b);
        });
        if (s.durum === "tahmin") {
          var sd = el("button", { type: "button", metin: "Şimdi değil" });
          sd.addEventListener("click", function () { durum.ertelenen[s.etiket + "|" + s.ag] = true; sahiplik(); duyur("Soru kapatıldı; hiçbir şey kaydedilmedi."); });
          sec.appendChild(sd);
        }
      }
      if (s.durum === "tahmin") dugmeler(); else { var dg = el("button", { type: "button", metin: "Değiştir" }); dg.addEventListener("click", dugmeler); sec.appendChild(dg); }
      kart.appendChild(sec);
      kap.appendChild(kart);
    });
  }
  function isaretle(s, sahip, durumP, sec) {
    sec.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
    durumP.textContent = "Kaydediliyor…";
    fetch("/api/isaret", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ adres_etiket: s.etiket, ag: s.ag, sahip: sahip }) })
      .then(function (y) { if (!y.ok) throw new Error(); return y.json(); })
      .then(function () { duyur("Kaydedildi. Toplamlar veri tarafında yeniden hesaplanıyor."); return yukle(); })
      .catch(function () { durumP.textContent = "Kaydedilemedi; yeniden dene."; sec.querySelectorAll("button").forEach(function (b) { b.disabled = false; }); });
  }

  /* ---------- ayrıntılı mod ---------- */
  var TUR = { cekim: "Çekim", yatirma: "Yatırma", takas: "Takas", gonderim: "Gönderim", giris: "Giriş", ucret: "Ücret",
    bota_giris: "Bota giriş", bottan_donus: "Bottan dönüş", alim: "Alım", satim: "Satım", aktarim: "Aktarım", taninmadi: "Tanınmadı" };
  durum.sekme = "hareketler";
  function saatTr(iso) {
    var d = new Date(iso);
    return iso && !isNaN(d) ? d.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  }
  function gorunum() {
    var ayr = location.hash === "#ayrintilar";
    $("pano").hidden = ayr; $("ayrinti").hidden = !ayr;
    if (ayr) { $("git-ayrinti").setAttribute("aria-current", "page"); $("git-genel").removeAttribute("aria-current"); ayrintiYukle(); }
    else { $("git-genel").setAttribute("aria-current", "page"); $("git-ayrinti").removeAttribute("aria-current"); }
  }
  function ayrintiYukle() {
    var q = new URLSearchParams();
    if (durum.oturum) q.set("oturum", durum.oturum);
    q.set("gizli", durum.gizli ? "1" : "0");
    $("ayrinti").setAttribute("aria-busy", "true");
    return fetch("/api/ayrinti?" + q.toString(), { cache: "no-store" })
      .then(function (y) { if (!y.ok) throw new Error(); return y.json(); })
      .then(function (a) { durum.ayrinti = a; durum.oturum = a.oturum; ayrintiCiz(); })
      .catch(function () { $("ayrinti-durum").textContent = "Ayrıntılar okunamadı. Sunucu çalışıyor mu?"; })
      .finally(function () { $("ayrinti").setAttribute("aria-busy", "false"); });
  }
  function ayrintiCiz() {
    var a = durum.ayrinti;
    $("ayrinti-durum").textContent = "Rapor " + gunTr(a.oturum) + (a.gizli ? " · gizli mod açık" : "");
    Array.prototype.forEach.call($("ayrinti-sekmeler").querySelectorAll("button"), function (b) {
      var secili = b.getAttribute("data-sekme") === durum.sekme;
      b.setAttribute("aria-selected", String(secili));
      $("sekme-" + b.getAttribute("data-sekme")).hidden = !secili;
    });
    hareketlerCiz(a); botCiz(a); kanitCiz(a);
  }
  function tabloKur(basliklar, satirlar) {
    var t = el("table"), b = el("tbody");
    t.appendChild(el("thead", null, [el("tr", null, basliklar.map(function (h) { return el("th", { metin: h }); }))]));
    satirlar.forEach(function (s) { b.appendChild(s); });
    t.appendChild(b);
    return el("div", { sinif: "tablo-sar" }, [t]);
  }
  function hareketlerCiz(a) {
    var k = $("sekme-hareketler"), h = a.hareketler;
    k.innerHTML = "";
    k.appendChild(el("div", { sinif: "bolum-ust" }, [el("h2", { metin: "Defter" }),
      el("span", { sinif: "donem", metin: (h.pencere || "") + " · " + h.toplam + " satır" + (h.toplam > h.satirlar.length ? " (ilk " + h.satirlar.length + ")" : "") })]));
    if (!h.satirlar.length) k.appendChild(el("p", { sinif: "not", metin: "Bu rapor gününde defter satırı yok." }));
    else k.appendChild(tabloKur(["Zaman", "Ne oldu", "Miktar", "Dolar", "Ağ / hesap", "Okuma", "İşlem"], h.satirlar.map(function (s) {
      var ne = el("td", null, [(TUR[s.tur] || s.tur) + (s.karsi ? " · " + s.karsi : "")]);
      if (s.supheli) ne.appendChild(el("span", { sinif: "rozet-k hata", metin: "şüpheli" }));
      if (s.durum !== "ok") ne.appendChild(el("span", { sinif: "rozet-k", metin: s.durum }));
      return el("tr", { sinif: s.supheli ? "supheli" : "" }, [el("td", { sinif: "mono", metin: saatTr(s.zaman) }), ne,
        el("td", { sinif: "hucre-sag", metin: m(s.miktar) || "" }), el("td", { sinif: "hucre-sag", metin: s.dolar ? m(s.dolar) : "fiyat yok" }),
        el("td", { metin: (s.ag || s.kaynak) + " · " + s.hesap }), el("td", { sinif: "mono", metin: s.kaynak_okuma }),
        el("td", { sinif: "mono", metin: s.islem || "—" })]);
    })));
    k.appendChild(el("h2", { metin: "Doğrulanmış cümleler" }));
    var ul = el("div");
    a.cumleler.forEach(function (c) {
      ul.appendChild(el("div", { sinif: "cumle" }, [ikon("gelen"), el("p", { metin: m(c.metin) }),
        el("small", { metin: cumleEtiketi(c) + " · " + (c.model === "kalip" ? "kalıp" : c.model) + " · " + c.yer + " · olgu " + c.olgular.join(", ") })]));
    });
    if (!a.cumleler.length) ul.appendChild(el("p", { sinif: "not", metin: "Bu rapor için cümle yok." }));
    k.appendChild(ul);
  }
  function botCiz(a) {
    var k = $("sekme-bot"), b = a.bot;
    k.innerHTML = "";
    if (!b.olgu) { k.appendChild(el("p", { sinif: "not", metin: "Bu raporda bot kaydıyla hesap arasında uyuşmazlık yok." })); return; }
    var o = b.olgu;
    k.appendChild(el("h2", { metin: o.bot + " botu" }));
    var dl = el("dl", { sinif: "bilgi" });
    [["Kurulum / durdurma", o.kurulus + " · " + o.durdurma], ["Durdurma tipi", o.durdurma_tipi], ["Yatırım", m(o.yatirim)],
     ["Borsanın kaydı", m(o.kayit_sonuc)], ["Hesaba dönen", m(o.donen_kote) + " ve " + m(o.donen_coin)],
     ["Hesaba dönen paraya göre", m(o.gercek_sonuc)], ["Fark", m(o.fark) + " · " + o.neden]].forEach(function (x) {
      if (x[1] && x[1].indexOf("undefined") < 0) { dl.appendChild(el("dt", { metin: x[0] })); dl.appendChild(el("dd", { metin: x[1] })); }
    });
    k.appendChild(dl);
    k.appendChild(el("p", { sinif: "kucuk-not", metin: "Sayıları kod hesaplar (olgu " + b.olgu_no + "); kayıt, botun değil hesaba dönen paranın kaydıyla karşılaştırılır." }));
    var bas = el("div", { sinif: "bolum-ust" }, [el("h2", { metin: "proof1'ın araştırma izi" })]);
    if (b.kayit) bas.appendChild(el("span", { sinif: "rozet-k", metin: "kayıt · önceden alınmış gerçek yanıtlar" }));
    k.appendChild(bas);
    if (!b.iz.length) { k.appendChild(el("p", { sinif: "not", metin: "Bu rapor için araştırma izi yok. Anlatıcı PROOF1_ARASTIR ile çalışınca yazılır." })); return; }
    k.appendChild(el("p", { sinif: "not", metin: "Hedef: kayıt hesaba dönen parayla tutuyor mu? Yalnız okuma araçları kullanılır; başka araç ATK'ya iletilmez." }));
    var ol = el("ol", { sinif: "iz" });
    b.iz.forEach(function (s, i) {
      var hata = s.sonuc && s.sonuc !== "ok" && i < b.iz.length - 1;
      var rozet = s.sonuc === "ok" ? el("span", { sinif: "rozet-k tamam", metin: "tamam" })
        : hata ? el("span", { sinif: "rozet-k hata", metin: s.sonuc.indexOf("reddedildi") === 0 ? "reddedildi" : "başarısız" }) : null;
      var dl2 = el("dl");
      [["Gerekçe", s.dusunce], ["Gözlem", m(s.gozlem)], ["Karar", s.karar], [i === b.iz.length - 1 ? "Sonuç" : "Durum", m(s.sonuc)]].forEach(function (x) {
        if (x[1]) { dl2.appendChild(el("dt", { metin: x[0] })); dl2.appendChild(el("dd", { metin: x[1] })); }
      });
      ol.appendChild(el("li", { sinif: (hata ? "hata " : "") + (i === b.iz.length - 1 ? "son" : "") }, [
        el("div", { sinif: "ust-satir" }, [s.sira + ".", el("span", { sinif: "arac-adi", metin: s.arac }), rozet]), dl2]));
    });
    k.appendChild(ol);
  }
  function kanitCiz(a) {
    var k = $("sekme-kanitlar"), kn = a.kanit, mu = a.muhur, bu = a.butce;
    k.innerHTML = "";
    var izgara = el("div", { sinif: "kanit-izgara" });
    // OKX ve zincir çağrıları
    var b1 = el("div", { sinif: "blok", style: "grid-column:1/-1" });
    b1.appendChild(el("h3", { metin: "Çağrılar: OKX TR, ATK, OnchainOS, zincir" }));
    b1.appendChild(el("p", { sinif: "olcu" }, [el("b", { metin: String(kn.toplam) }), "çağrı · " + kn.gruplar.reduce(function (s, g) { return s + g.hata; }, 0) + " hata · ",
      el("span", { sinif: "rozet-k " + (kn.salt_okunur_hepsi ? "tamam" : "hata"), metin: kn.salt_okunur_hepsi ? "hepsi salt okunur" : "salt okunur olmayan çağrı var" })]));
    b1.appendChild(tabloKur(["Kaynak", "Araç / uç", "Çağrı", "Hata", "Ort. süre", "Kullanılan alanlar", "Salt okunur"], kn.gruplar.slice(0, 12).map(function (g) {
      return el("tr", null, [el("td", { metin: g.kaynak }), el("td", { sinif: "mono", metin: g.ad }), el("td", { sinif: "hucre-sag", metin: String(g.cagri) }),
        el("td", { sinif: "hucre-sag", metin: String(g.hata) }), el("td", { sinif: "hucre-sag", metin: g.ort_ms + " ms" }),
        el("td", { sinif: "mono", metin: g.alanlar.slice(0, 6).join(", ") + (g.alanlar.length > 6 ? " …" : "") }),
        el("td", { metin: g.salt_okunur ? "evet" : "hayır" })]);
    })));
    if (kn.gruplar.length > 12) b1.appendChild(el("p", { sinif: "kucuk-not", metin: (kn.gruplar.length - 12) + " araç/uç daha var." }));
    if (kn.hatalar.length) {
      b1.appendChild(el("p", { sinif: "not", metin: "Son başarısız çağrılar (hata, akışı durdurmaz; adım günlüğe yazılır):" }));
      var ul = el("ul", { sinif: "kucuk-not" });
      kn.hatalar.forEach(function (h) { ul.appendChild(el("li", { metin: h.kaynak + " · " + h.ad + " · kod " + h.kod + " · " + h.sure_ms + " ms" })); });
      b1.appendChild(ul);
    }
    izgara.appendChild(b1);
    // Mühür
    var b2 = el("div", { sinif: "blok" }), dl = el("dl", { sinif: "bilgi" });
    b2.appendChild(el("h3", { metin: "Mühür · Avalanche" }));
    function satir(x, y, link) {
      dl.appendChild(el("dt", { metin: x }));
      var dd = el("dd", { sinif: "mono" });
      if (link) { var aa = el("a", { href: link, target: "_blank", rel: "noopener noreferrer", metin: y }); dd.appendChild(aa); } else dd.textContent = y;
      dl.appendChild(dd);
    }
    satir("Ağ", mu.ag + " (chainId " + mu.chain_id + ")");
    satir("ERC-8004 kimliği", mu.agent_id ? "agentId " + mu.agent_id : "yok", mu.kimlik_gezgin);
    if (mu.sozlesme) satir("Mühür sözleşmesi", mu.sozlesme.slice(0, 6) + "…" + mu.sozlesme.slice(-4), mu.sozlesme_gezgin);
    satir("Rapor günü", gunTr(mu.gun));
    var dogru = el("p", { sinif: "kucuk-not" });
    if (mu.gun_muhru) {
      satir("Kök", mu.gun_muhru.kok.slice(0, 10) + "…" + mu.gun_muhru.kok.slice(-6));
      satir("Önceki kök", mu.gun_muhru.onceki_kok.slice(0, 10) + "…");
      satir("İşlem", mu.gun_muhru.islem.slice(0, 10) + "…", mu.gun_muhru.gezgin);
      dogru.textContent = "Zincirde henüz doğrulanmadı.";
    } else {
      dogru.textContent = "Bu gün henüz mühürlenmedi." + (mu.son.length ? " Son mühür: " + gunTr(mu.son[0].gun) + "." : "");
    }
    b2.appendChild(dl);
    b2.appendChild(dogru);
    if (mu.gun_muhru) {
      var dg = el("button", { type: "button", sinif: "baglanti", metin: "Zincirde doğrula" });
      var METIN = { dogrulandi: "Doğrulandı: zincirdeki kök yerel kayıtla aynı.", uyusmuyor: "Uyuşmuyor: zincirdeki kök yerel kayıttan farklı.",
        zincirde_yok: "Zincirde bu gün için kök yok.", baglanilamadi: "Zincire bağlanılamadı; doğrulama yapılamadı.",
        yerel_kayit_yok: "Yerel mühür kaydı yok.", ayar_yok: "Mühür ayarları eksik (PROOF1_AGENT_ID, PROOF1_SEAL_ADDRESS)." };
      dg.addEventListener("click", function () {
        dogru.textContent = "Zincire soruluyor…";
        fetch("/api/muhur-dogrula?gun=" + encodeURIComponent(mu.gun), { cache: "no-store" }).then(function (y) { return y.json(); })
          .then(function (d) { dogru.textContent = METIN[d.durum] || d.durum; duyur(dogru.textContent); })
          .catch(function () { dogru.textContent = METIN.baglanilamadi; });
      });
      b2.appendChild(dg);
    }
    b2.appendChild(el("p", { sinif: "not", metin: mu.not }));
    izgara.appendChild(b2);
    // Bütçe
    var b3 = el("div", { sinif: "blok" });
    b3.appendChild(el("h3", { metin: "Model bütçesi · " + bu.ay }));
    b3.appendChild(el("p", { sinif: "olcu" }, [el("b", { metin: bu.harcanan }), "/ " + bu.tavan + " tavan"]));
    var oran = Math.min(100, (parseFloat(bu.harcanan.replace(/\./g, "").replace(",", ".")) / parseFloat(bu.tavan.replace(",", "."))) * 100 || 0);
    b3.appendChild(el("div", { sinif: "cubuk", role: "img", "aria-label": "Bütçenin %" + Math.round(oran) + "'i kullanıldı" }, [el("span", { style: "width:" + oran.toFixed(1) + "%" })]));
    var dl3 = el("dl", { sinif: "bilgi" });
    [["Kalan", bu.kalan], ["Çağrı", String(bu.cagri)], ["Şu anki kip", bu.kip === "kalip" ? "kalıp cümle (tavan)" : bu.kip],
     ["Durumlar", Object.keys(bu.durumlar).map(function (d) { return d + ": " + bu.durumlar[d]; }).join(" · ") || "—"]].forEach(function (x) {
      dl3.appendChild(el("dt", { metin: x[0] })); dl3.appendChild(el("dd", { metin: x[1] }));
    });
    b3.appendChild(dl3);
    b3.appendChild(el("p", { sinif: "not", metin: "Kullanıcı başına ayda 35 TL sert tavan. Harcama tavanın %80'ine gelince Haiku, tavanda kalıp cümle kullanılır; tavan hiçbir çağrıyla aşılmaz." }));
    izgara.appendChild(b3);
    k.appendChild(izgara);
  }
  Array.prototype.forEach.call($("ayrinti-sekmeler").querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () { durum.sekme = b.getAttribute("data-sekme"); if (durum.ayrinti) ayrintiCiz(); });
  });
  window.addEventListener("hashchange", gorunum);

  /* ---------- kontroller ---------- */
  $("gizli").addEventListener("click", function () {
    durum.gizli = !durum.gizli;
    this.setAttribute("aria-checked", String(durum.gizli));
    $("gizli-serit").hidden = !durum.gizli;
    duyur(durum.gizli ? "Gizli mod açık: tutarlar gizli" : "Gizli mod kapalı: tutarlar görünür");
    if (location.hash === "#ayrintilar") ayrintiYukle(); else yukle();
  });
  $("salt-okunur").addEventListener("click", function () {
    var a = $("salt-okunur-aciklama"); a.hidden = !a.hidden; this.setAttribute("aria-expanded", String(!a.hidden));
  });
  Array.prototype.forEach.call($("aralik").querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () {
      if (b.getAttribute("aria-disabled") === "true") duyur(b.textContent + ": bu aralık için okuma yok; tüm dönem gösteriliyor.");
    });
  });
  // Yedek ekran kaydı için: ?kayit=1 → ekranda kalıcı "KAYIT" şeridi (canlı ile karıştırılmasın).
  if (new URLSearchParams(location.search).get("kayit") === "1") {
    $("kayit-serit").hidden = false;
    document.title = "proof1 · kayıt";
  }
  $("panel-kapat").addEventListener("click", panelKapat);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") panelKapat(); });
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      if (durum.rapor && durum.dar !== ($("sema").clientWidth < 520)) { durum.dar = !durum.dar; sema(); }
    }).observe($("sema"));
  }
  yukle().then(function () { if (location.hash === "#ayrintilar") gorunum(); });
})();
