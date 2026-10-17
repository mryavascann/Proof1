(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var SVGNS = "http://www.w3.org/2000/svg";
  var AYLAR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  var durum = {
    rapor: null, gizli: true, secili: null, dar: null, kopruKapsam: "servet", ertelenen: {},
    oturum: new URLSearchParams(location.search).get("oturum")
  };

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
    var s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("class", "i"); s.setAttribute("aria-hidden", "true");
    var u = document.createElementNS(SVGNS, "use"); u.setAttribute("href", "#i-" + ad); s.appendChild(u);
    return s;
  }
  function duyur(metin) { $("duyuru").textContent = metin; }
  function gunTr(oturum) {
    var m = /(\d{4})-(\d{2})-(\d{2})$/.exec(oturum || "");
    return m ? (+m[3]) + " " + AYLAR[+m[2]] + " " + m[1] : oturum;
  }
  function zamanTr(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
  }
  function cumleEtiketi(c) {
    return c.denetim === "gecti" ? "Sayılar olgularla doğrulandı" : "Doğrulanmış kalıp cümle";
  }

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
        $("baglam-satiri").textContent = "Veri okunamadı";
        $("ozet").textContent = e.message === "Veri kaynağı hazırlanmadı." ? e.message : "Pano verisine ulaşılamadı. Sunucu çalışıyor mu?";
        $("ozet-durum").textContent = "";
      })
      .finally(function () { $("pano").setAttribute("aria-busy", "false"); });
  }

  function ciz() {
    var r = durum.rapor;
    $("baglam-satiri").textContent = gunTr(r.oturum) + " · OKX TR ana hesap ve çekim adresleri · " +
      (r.veri_turu === "örnek" ? "Örnek veri" : "Canlı veri");
    $("durum-satiri").textContent = "Veri zamanı: " + (zamanTr(r.uretim) || "bilinmiyor");
    var ozet = r.ozet || [];
    $("ozet").textContent = ozet.length ? ozet.map(function (c) { return c.metin; }).join(" ") : "Bu oturum için özet cümle yok.";
    $("ozet-durum").textContent = ozet.length ? cumleEtiketi(ozet[0]) + " · olgu " + ozet[0].olgular.join(", ") : "";
    var kalan = $("kalan");
    if (r.kalan) { kalan.hidden = false; kalan.textContent = r.kalan.metin + " " + r.kalan.not; } else { kalan.hidden = true; }
    akis(); kopru(); uyarilar(); sahiplik();
  }

  /* ---------- akış şeması ---------- */
  function akis() {
    var a = durum.rapor.akis;
    $("akis-donem").textContent = (a.donem || "Dönem bilinmiyor") + " · " + a.birim;
    $("akis-not").textContent = a.not;
    durum.dar = $("sema").clientWidth < 520;
    sema();
    tablo();
  }

  function sema() {
    var a = durum.rapor.akis, kutu = $("sema"), dar = durum.dar;
    var gruplar = a.gruplar, n = gruplar.length;
    kutu.innerHTML = "";
    if (!n) { kutu.appendChild(el("p", { sinif: "not", metin: "Bu oturumda çekim akışı yok." })); return; }
    var W = dar ? 340 : 640, nodeW = 8, solX = dar ? 4 : 150, sagX = dar ? 190 : 430, bosluk = dar ? 12 : 16;
    var toplam = gruplar.reduce(function (s, g) { return s + g.deger; }, 0) || 1;
    var Hb = Math.max(dar ? 260 : 300, n * (dar ? 46 : 52));
    var k = (Hb - bosluk * (n - 1)) / toplam;
    var y = 0, sag = gruplar.map(function (g) {
      var t = Math.max(2, g.deger * k), o = { g: g, y0: y, y1: y + t, t: t }; y += t + bosluk; return o;
    });
    var solToplam = sag.reduce(function (s, o) { return s + o.t; }, 0);
    var solY = (y - bosluk - solToplam) / 2, sy = solY;
    // Etiketler üst üste binmesin: en az 36 px aralık.
    var etiketY = [], son = -Infinity;
    sag.forEach(function (o) { var m = Math.max((o.y0 + o.y1) / 2, son + 36); etiketY.push(m); son = m; });
    var H = Math.max(y - bosluk, son + 20) + 8;

    var s = '<svg viewBox="-2 -14 ' + (W + 4) + " " + (H + 18) + '" role="presentation">';
    var bantlar = "";
    sag.forEach(function (o, i) {
      var a0 = sy, a1 = sy + o.t; sy = a1;
      var f1 = solX + nodeW, f2 = sagX, fm = (f1 + f2) / 2;
      var p = "M" + f1 + "," + a0 + " C" + fm + "," + a0 + " " + fm + "," + o.y0 + " " + f2 + "," + o.y0 +
        " L" + f2 + "," + o.y1 + " C" + fm + "," + o.y1 + " " + fm + "," + a1 + " " + f1 + "," + a1 + " Z";
      var tutar = o.g.tutar || (o.g.alt ? o.g.alt.length + " ağ" : "");
      var aria = "OKX TR → " + o.g.ad + (o.g.tutar ? ": " + o.g.tutar : "") + (o.g.cekim_sayisi ? ", " + o.g.cekim_sayisi + " çekim" : "");
      bantlar += '<g class="bant ac" style="animation-delay:' + (i * 40) + 'ms" tabindex="' + (i === 0 ? 0 : -1) +
        '" role="button" data-i="' + i + '" aria-label="' + esc(aria) + '">' +
        '<path class="b" d="' + p + '" fill="var(--gelen)"/>' +
        '<path d="' + p + '" fill="none" stroke="transparent" stroke-width="12" pointer-events="stroke"/></g>';
      s += '<rect x="' + sagX + '" y="' + o.y0 + '" width="' + nodeW + '" height="' + o.t + '" rx="2" fill="var(--gelen)"/>';
      var ly = etiketY[i];
      if (Math.abs(ly - (o.y0 + o.y1) / 2) > 4) {
        s += '<path d="M' + (sagX + nodeW + 2) + "," + ((o.y0 + o.y1) / 2) + " L" + (sagX + nodeW + 6) + "," + (ly - 4) +
          '" stroke="var(--cizgi)" fill="none"/>';
      }
      s += '<text x="' + (sagX + nodeW + 10) + '" y="' + (ly - 3) + '" class="ad">' + esc(o.g.ad) + "</text>";
      s += '<text x="' + (sagX + nodeW + 10) + '" y="' + (ly + 13) + '" class="tutar">' + esc(tutar) + "</text>";
    });
    s = s.replace('role="presentation">', 'role="presentation">' + bantlar);
    s += '<rect x="' + solX + '" y="' + solY + '" width="' + nodeW + '" height="' + solToplam + '" rx="2" fill="var(--metin)"/>';
    if (!dar) {
      var kx = solX - 10, ky = solY + solToplam / 2 - 22, kay = a.kaynak;
      s += '<text x="' + kx + '" y="' + ky + '" text-anchor="end" class="ad">' + esc(kay.ad) + "</text>";
      s += '<text x="' + kx + '" y="' + (ky + 17) + '" text-anchor="end" class="tutar">' + esc(kay.cekim_sayisi + " çekim · " + kay.adres_sayisi + " adres") + "</text>";
      s += '<text x="' + kx + '" y="' + (ky + 34) + '" text-anchor="end" class="tutar">' + esc(kay.tutar || "") + "</text>";
    }
    s += "</svg>";
    if (dar) {
      var kay2 = a.kaynak;
      kutu.appendChild(el("p", { sinif: "not", metin: kay2.ad + " · " + kay2.cekim_sayisi + " çekim · " + kay2.adres_sayisi + " adres · " + (kay2.tutar || "") }));
    }
    var sar = document.createElement("div");
    sar.innerHTML = s;
    kutu.appendChild(sar.firstChild);
    baglaBantlar();
  }

  function baglaBantlar() {
    var svg = $("sema").querySelector("svg");
    var gs = Array.prototype.slice.call(svg.querySelectorAll(".bant"));
    function goster(i) {
      svg.classList.add("vurgu");
      gs.forEach(function (g, j) { g.classList.toggle("secili", j === i); });
      var g = durum.rapor.akis.gruplar[i];
      $("okuma").innerHTML = "<b>OKX TR → " + esc(g.ad) + "</b> · " +
        esc(g.tutar ? g.tutar + (g.cekim_sayisi ? " · " + g.cekim_sayisi + " çekim" : "") : g.alt.map(function (x) { return x.ad + " " + x.tutar; }).join(" · "));
    }
    function birak() {
      if (durum.secili !== null) return goster(durum.secili);
      svg.classList.remove("vurgu");
      gs.forEach(function (g) { g.classList.remove("secili"); });
      $("okuma").textContent = "Bir banda dokun ya da Tab ile seç: o paranın ayrıntısı açılır.";
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

  function kapsamListesi(kapsam) {
    var liste = el("div", { sinif: "kapsam" });
    if (!kapsam || !kapsam.adres) { liste.appendChild(el("p", { sinif: "not", metin: "Bu ağda kayıtlı adres yok." })); return liste; }
    liste.appendChild(el("p", { sinif: "not", metin: kapsam.adres + " adres" + (kapsam.benim_tahmini ? " · " + kapsam.benim_tahmini + " tanesi büyük olasılıkla senin (tahmin)" : "") }));
    kapsam.katmanlar.forEach(function (k) { liste.appendChild(el("div", { sinif: "katman" }, [ikon("tamam"), k])); });
    kapsam.eksik.forEach(function (k) { liste.appendChild(el("div", { sinif: "katman yok" }, [ikon("eksik"), k + ": okunamadı"])); });
    if (kapsam.yalniz_cekim) liste.appendChild(el("p", { sinif: "not", metin: "Bu ağda yalnız çekimi görüyorum." }));
    return liste;
  }

  function cumleListesi(cumleler) {
    var kap = el("div");
    if (!cumleler.length) { kap.appendChild(el("p", { sinif: "not", metin: "Bu bant için doğrulanmış cümle yok." })); return kap; }
    cumleler.forEach(function (c) {
      kap.appendChild(el("div", { sinif: "cumle" }, [
        el("p", { metin: c.metin }),
        el("small", { metin: cumleEtiketi(c) + " · olgu " + c.olgular.join(", ") + (c.donem_notu ? " · " + c.donem_notu : "") })
      ]));
    });
    return kap;
  }

  function panelAc(i) {
    var g = durum.rapor.akis.gruplar[i];
    durum.secili = i;
    $("panel-baslik").textContent = "OKX TR → " + g.ad;
    var ic = $("panel-icerik"); ic.innerHTML = "";
    var dl = el("dl", { sinif: "bilgi" });
    function satir(a, b) { dl.appendChild(el("dt", { metin: a })); dl.appendChild(el("dd", { metin: b })); }
    if (g.tutar) satir("Çekim toplamı", g.tutar + " (çekim anındaki dolar karşılığı)");
    if (g.cekim_sayisi) satir("Çekim sayısı", g.cekim_sayisi);
    satir("Dönem", durum.rapor.akis.donem || "bilinmiyor");
    satir("Kaynak", "olgu " + g.olgular.join(", "));
    ic.appendChild(dl);
    if (g.alt) {
      g.alt.forEach(function (x) {
        ic.appendChild(el("h4", { metin: x.ad + " · " + x.tutar + " · " + x.cekim_sayisi + " çekim" }));
        ic.appendChild(kapsamListesi(x.kapsam));
        ic.appendChild(cumleListesi(x.cumleler));
      });
    } else {
      ic.appendChild(el("h4", { metin: "Okunabilen katmanlar" }));
      ic.appendChild(kapsamListesi(g.kapsam));
      ic.appendChild(el("h4", { metin: "Ne oldu" }));
      ic.appendChild(cumleListesi(g.cumleler));
    }
    $("panel").hidden = false;
    document.querySelector(".akis-govde").classList.add("acik");
    $("panel").focus();
    duyur(g.ad + " ayrıntısı açıldı");
    if (durum.dar !== ($("sema").clientWidth < 520)) akis(); else baglaBantlar();
  }

  function panelKapat() {
    if ($("panel").hidden) return;
    var i = durum.secili;
    durum.secili = null;
    $("panel").hidden = true;
    document.querySelector(".akis-govde").classList.remove("acik");
    if (durum.dar !== ($("sema").clientWidth < 520)) akis(); else baglaBantlar();
    var g = $("sema").querySelector('.bant[data-i="' + i + '"]');
    if (g) { $("sema").querySelectorAll(".bant").forEach(function (b) { b.setAttribute("tabindex", "-1"); }); g.setAttribute("tabindex", "0"); g.focus(); }
  }

  function tablo() {
    var t = $("akis-tablo"); t.innerHTML = "";
    t.appendChild(el("thead", null, [el("tr", null, [el("th", { metin: "Kaynak → hedef" }), el("th", { metin: "Çekim (USD)" }),
      el("th", { metin: "Çekim sayısı" }), el("th", { metin: "Okunabilen katmanlar" })])]));
    var b = el("tbody");
    durum.rapor.akis.gruplar.forEach(function (g) {
      (g.alt || [g]).forEach(function (x) {
        b.appendChild(el("tr", null, [el("td", { metin: "OKX TR → " + x.ad }), el("td", { metin: x.tutar || "" }),
          el("td", { metin: x.cekim_sayisi || "" }), el("td", { metin: x.kapsam && x.kapsam.adres ? x.kapsam.katmanlar.join(", ") : "adres yok" })]));
      });
    });
    t.appendChild(b);
  }

  /* ---------- köprü ---------- */
  function kopru() {
    var k = durum.rapor.kopru, sek = $("kopru-sekmeler"), ic = $("kopru-icerik");
    sek.innerHTML = ""; ic.innerHTML = "";
    if (!k) { $("kopru-not").textContent = "Karşılaştırma için en az iki günlük okuma gerekiyor."; return; }
    $("kopru-not").textContent = k.not;
    var adlar = Object.keys(k.kapsamlar);
    if (adlar.indexOf(durum.kopruKapsam) < 0) durum.kopruKapsam = adlar[0];
    adlar.forEach(function (ad) {
      var b = el("button", { type: "button", role: "tab", "aria-selected": String(ad === durum.kopruKapsam), metin: k.kapsamlar[ad].ad });
      b.addEventListener("click", function () { durum.kopruKapsam = ad; kopru(); });
      sek.appendChild(b);
    });
    var kap = k.kapsamlar[durum.kopruKapsam];
    var satirlar = el("div", { sinif: "kopru-satirlar", role: "tabpanel" });
    if (!kap.ozet.length) satirlar.appendChild(el("p", { sinif: "not", metin: "Bu dönemde hareket yok; eldeki varlıkların fiyatı yine değişmiş olabilir." }));
    kap.ozet.forEach(function (o) {
      satirlar.appendChild(el("div", { sinif: "kopru-satir" }, [
        el("span", { metin: o.ad }),
        el("span", { sinif: "sag" }, [o.varliklar.length ? o.varliklar.join(" · ") : "değişim yok",
          el("small", { metin: o.dolar ? o.dolar : "Dolar karşılığı henüz yok" })])
      ]));
    });
    ic.appendChild(satirlar);
    var acik = false, liste = el("div", { sinif: "kopru-satirlar", hidden: "" });
    kap.kalemler.forEach(function (x) {
      liste.appendChild(el("div", { sinif: "kopru-satir" }, [
        el("span", null, [x.ad, el("small", { metin: " · " + x.aciklama })]),
        el("span", { sinif: "sag" }, [x.varliklar.length ? x.varliklar.join(" · ") : "0",
          el("small", { metin: (x.dolar || "Dolar karşılığı henüz yok") + " · olgu " + x.olgular.join(", ") })])
      ]));
    });
    var dugme = el("button", { type: "button", sinif: "baglanti", "aria-expanded": "false", metin: "Tüm kalemler (" + kap.kalemler.length + ")" });
    dugme.addEventListener("click", function () {
      acik = !acik; liste.hidden = !acik; dugme.setAttribute("aria-expanded", String(acik));
      dugme.textContent = acik ? "Kalemleri gizle" : "Tüm kalemler (" + kap.kalemler.length + ")";
    });
    ic.appendChild(dugme);
    ic.appendChild(liste);
  }

  /* ---------- uyarılar ---------- */
  function uyarilar() {
    var u = durum.rapor.uyarilar, ul = $("uyarilar");
    ul.innerHTML = "";
    if (!u.liste.length) { ul.appendChild(el("li", { metin: "Uyarı yok." })); }
    var ONEM = { acil: "Acil", orta: "Orta", bilgi: "Bilgi" };
    u.liste.forEach(function (x) {
      ul.appendChild(el("li", { sinif: x.onem }, [ikon("uyari"), el("div", null, [el("span", { sinif: "onem", metin: ONEM[x.onem] || x.onem }), x.metin])]));
    });
    var tum = $("tum-uyarilar");
    tum.hidden = u.toplam <= u.liste.length;
    tum.textContent = "Tüm uyarılar (" + u.toplam + ") · ayrıntılı modda";
  }

  /* ---------- sahiplik ---------- */
  function sahiplik() {
    var liste = durum.rapor.sahiplik.filter(function (s) { return !durum.ertelenen[s.etiket + "|" + s.ag]; });
    $("sahiplik-bolum").hidden = !liste.length;
    var kap = $("sahiplik"); kap.innerHTML = "";
    liste.forEach(function (s) {
      var kart = el("div", { sinif: "kart" });
      kart.appendChild(el("div", { sinif: "adres", metin: s.kisa + " · " + s.ag }));
      kart.appendChild(el("p", { metin: s.kanit }));
      var DURUM = { tahmin: "Tahmin: büyük olasılıkla senin", benim: "Sen doğruladın: senin", benim_degil: "Sen işaretledin: senin değil" };
      var durumP = el("p", { sinif: "durum", metin: DURUM[s.durum] || s.durum });
      kart.appendChild(durumP);
      var secenek = el("div", { sinif: "secenekler" });
      function dugmeler() {
        secenek.innerHTML = "";
        [["benim", "Benim"], ["benim_degil", "Benim değil"]].forEach(function (d, i) {
          var b = el("button", { type: "button", sinif: i === 0 ? "birincil" : "", metin: d[1] });
          b.addEventListener("click", function () { isaretle(s, d[0], durumP, secenek); });
          secenek.appendChild(b);
        });
        if (s.durum === "tahmin") {
          var sd = el("button", { type: "button", metin: "Şimdi değil" });
          sd.addEventListener("click", function () { durum.ertelenen[s.etiket + "|" + s.ag] = true; sahiplik(); duyur("Soru şimdilik kapatıldı; hiçbir şey kaydedilmedi."); });
          secenek.appendChild(sd);
        }
      }
      if (s.durum === "tahmin") dugmeler();
      else { var deg = el("button", { type: "button", metin: "Değiştir" }); deg.addEventListener("click", dugmeler); secenek.appendChild(deg); }
      kart.appendChild(secenek);
      kap.appendChild(kart);
    });
  }

  function isaretle(s, sahip, durumP, secenek) {
    secenek.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
    durumP.textContent = "Kaydediliyor…";
    fetch("/api/isaret", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ adres_etiket: s.etiket, ag: s.ag, sahip: sahip }) })
      .then(function (y) { if (!y.ok) throw new Error(); return y.json(); })
      .then(function () {
        duyur("Kaydedildi. Toplamlar veri tarafında yeniden hesaplanıyor.");
        return yukle();
      })
      .catch(function () {
        durumP.textContent = "Kaydedilemedi; yeniden dene.";
        secenek.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      });
  }

  /* ---------- üst bar ---------- */
  $("gizli").addEventListener("click", function () {
    durum.gizli = !durum.gizli;
    this.setAttribute("aria-checked", String(durum.gizli));
    $("gizli-serit").hidden = !durum.gizli;
    duyur(durum.gizli ? "Gizli mod açık" : "Gizli mod kapalı: bakiye seviyeleri görünür");
    yukle();
  });
  $("salt-okunur").addEventListener("click", function () {
    var a = $("salt-okunur-aciklama"); a.hidden = !a.hidden; this.setAttribute("aria-expanded", String(!a.hidden));
  });
  $("panel-kapat").addEventListener("click", panelKapat);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") panelKapat(); });
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      if (durum.rapor && durum.dar !== ($("sema").clientWidth < 520)) akis();
    }).observe($("sema"));
  }
  yukle();
})();
