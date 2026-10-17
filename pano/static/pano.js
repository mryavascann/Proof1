(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var AYLAR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  var BASLIK = "Paran <em>nereye</em> gitti?", ALT_BASLIK = "proof1, borsadan çıkan parayı zincirde izler. Yalnız okur.";
  var HAREKETSIZ = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  // GSAP CDN'den gelir. Yoksa (çevrimdışı) sayfa eksiksiz çizilir, yalnız giriş hareketi olmaz.
  var G = window.gsap || null;
  var ilkSorgu = new URLSearchParams(location.search);
  // Herkese açık demo (Vercel, python -m pano.statik): sunucu yok, uçlar önceden üretilmiş JSON dosyaları, yalnız örnek veri.
  var STATIK = document.documentElement.getAttribute("data-statik") === "1";
  var durum = {
    rapor: null, ayrinti: null, gizli: true, secili: null, dar: null, ilk: true, kopruKapsam: "servet", ertelenen: {},
    oturum: ilkSorgu.get("oturum"), hesap: ilkSorgu.get("hesap"), bantlar: [], geo: null, sekme: "ozet",
    hesaplar: [], tarama: null, split: null, tarayici: null, tarayiciAktif: false
  };
  if (G && !HAREKETSIZ) {
    document.body.classList.add("bekle");
    setTimeout(function () { document.body.classList.remove("bekle"); }, 2500);   // ne olursa olsun sahne görünür
  }

  /* ---------- yardımcılar ---------- */
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function el(etiket, ozellik, cocuklar) {
    var e = document.createElement(etiket);
    if (ozellik) Object.keys(ozellik).forEach(function (k) {
      var v = ozellik[k];
      if (v == null || v === false) return;
      if (k === "metin") e.textContent = v;
      else if (k === "sinif") e.className = v;
      else e.setAttribute(k, v);
    });
    (cocuklar || []).forEach(function (c) {
      if (c == null || c === "") return;
      e.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
    return e;
  }
  function ikon(ad) {
    var s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("class", "i"); s.setAttribute("aria-hidden", "true");
    var u = document.createElementNS("http://www.w3.org/2000/svg", "use"); u.setAttribute("href", "#i-" + ad); s.appendChild(u);
    return s;
  }
  function duyur(m) { $("duyuru").textContent = m; }
  function gunTr(oturum) {
    var x = /(\d{4})-(\d{2})-(\d{2})$/.exec(oturum || "");
    return x ? (+x[3]) + " " + AYLAR[+x[2]] + " " + x[1] : oturum;
  }
  function zamanTr(iso) {
    var d = new Date(iso);
    return iso && !isNaN(d) ? d.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) : "";
  }
  function saatTr(iso) {
    var d = new Date(iso);
    return iso && !isNaN(d) ? d.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  }
  function kisaKimlik(k) { k = String(k || ""); return !k ? "—" : k.length > 14 ? k.slice(0, 8) + "…" + k.slice(-4) : k; }
  // Para girişi (+) altın, hesaptan çıkış (−) mavi. Sayı değişmez; yalnız işaretine göre renk sınıfı.
  function isaretli(e, metin) {
    var m = String(metin == null ? e.textContent : metin).trim();
    if (/^[−-]\s*\d/.test(m)) e.classList.add("eksi");
    else if (/^\+?\s*\d/.test(m) && !/^0([,.]0+)?(\s|$)/.test(m)) e.classList.add("arti");
    return e;
  }
  function borsaBakiyesi() {                // bugün 09.00 borsa seviyesi; gizli modda sunucu rapora hiç koymaz
    var k = durum.rapor && durum.rapor.kopru, kap = k && k.kapsamlar.borsa;
    var b = kap && kap.kalemler.filter(function (x) { return x.kalem === "bitis"; })[0];
    return b && b.dolar ? kurus(b.dolar) : null;
  }
  // "11.499,8898 $" → "11.499,89 $": yalnız gösterim yuvarlaması; tutarı kod hesaplar
  function kurus(m) {
    var x = /^([+\-−]?[\d.]+),(\d{3,})(.*)$/.exec(String(m));
    if (!x) return m;
    var n = parseFloat(x[1].replace(/\./g, "").replace("−", "-") + "." + x[2]);
    return new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) + x[3];
  }
  function eksi(m) { return String(m == null ? "" : m).replace(/^-/, "−"); }
  function cumleEtiketi(c) {
    return c.denetim === "gecti" ? "sayılar olgularla doğrulandı" : c.denetim === "kod" ? "kod hesapladı" : "doğrulanmış kalıp cümle";
  }
  function f(x) { return Math.round(x * 10) / 10; }

  // Her istek seçili hesabı taşır (kendi hesabını bağlayan kişinin panosu ayrı veritabanından okunur).
  function api(yol, params, secenek) {
    if (STATIK) return statikVeri(yol, params, secenek);
    var q = new URLSearchParams(params || {});
    if (durum.hesap) q.set("hesap", durum.hesap);
    var s = q.toString();
    return fetch(yol + (s ? "?" + s : ""), Object.assign({ cache: "no-store" }, secenek || {})).then(function (y) {
      return y.json().catch(function () { return {}; }).then(function (g) {
        if (!y.ok) { var e = new Error(g.hata || "okunamadı"); e.kod = y.status; throw e; }
        return g;
      });
    });
  }

  function statikVeri(yol, params, secenek) {
    var g = params && params.gizli === "0" ? "0" : "1";
    if (durum.tarayiciAktif && durum.tarayici) {           // kendi hesabı: yalnız bu sekmenin belleğinde
      var t = durum.tarayici, nesne = { "/api/rapor": g === "1" ? t.rapor1 : t.rapor0, "/api/ayrinti": g === "1" ? t.ayrinti1 : t.ayrinti0 }[yol];
      return nesne && !(secenek && secenek.method) ? Promise.resolve(nesne) : Promise.reject(new Error("Demoda yok."));
    }
    var dosya = { "/api/rapor": "rapor-" + g, "/api/ayrinti": "ayrinti-" + g }[yol];
    if (!dosya || (secenek && secenek.method)) return Promise.reject(new Error("Demoda yok."));
    return fetch("/veri/" + dosya + ".json", { cache: "no-store" }).then(function (y) {
      if (!y.ok) throw new Error("Veri kaynağı hazırlanmadı.");
      return y.json();
    });
  }

  /* ---------- veri ---------- */
  function yukle(animasyonlu) {
    var p = { gizli: durum.gizli ? "1" : "0" };
    if (durum.oturum) p.oturum = durum.oturum;
    $("sade").setAttribute("aria-busy", "true");
    return api("/api/rapor", p).then(function (r) {
      durum.rapor = r; durum.oturum = r.oturum;
      document.body.classList.remove("veri-yok");
      ciz(animasyonlu);
      ayrintiYukle(true);                  // detay sekmeleri ve mühür rozeti arka planda hazırlanır
    }).catch(function (e) {
      document.body.classList.remove("bekle");
      if (durum.rapor) return;             // önceki rapor ekranda kalır
      document.body.classList.add("veri-yok");
      if (durum.split) { durum.split.revert(); durum.split = null; }
      var hazirlanmadi = e.message === "Veri kaynağı hazırlanmadı." || e.kod === 404;
      $("baslik").textContent = hazirlanmadi ? "Henüz tarama yok." : "Pano verisine ulaşılamadı.";
      $("alt-baslik").textContent = hazirlanmadi ? "Sabah işini çalıştır ya da kendi hesabını bağla." : "Sunucu çalışıyor mu?";
    }).finally(function () { $("sade").setAttribute("aria-busy", "false"); });
  }

  function ciz(animasyonlu) {
    var r = durum.rapor, a = r.akis;
    if (!durum.split) $("baslik").innerHTML = BASLIK;          // sabit metin; veri içermez
    $("alt-baslik").textContent = ALT_BASLIK;
    $("donem").textContent = [a.donem, "çekimler", r.veri_turu === "örnek" ? "örnek veri" : ""].filter(Boolean).join("  ·  ");
    $("durum-satiri").textContent = (r.veri_turu === "örnek" ? "Örnek veri" : "Canlı veri") + " · " + gunTr(r.oturum) +
      (r.uretim ? " · son okuma " + zamanTr(r.uretim) : "");
    durum.dar = $("akis").clientWidth < 640;
    sema();
    kartlar();
    if (durum.secili !== null) panelAc(durum.secili, true);
    if ((animasyonlu || durum.ilk) && G && !HAREKETSIZ) giris();
    else { document.body.classList.remove("bekle"); Akis.yogunluk(1, true); }
    durum.ilk = false;
  }

  /* ---------- akış şeması: OKX TR → Sen → ağlar ---------- */
  function bantYolu(b) {
    var xm = (b.x1 + b.x2) / 2;
    return "M" + b.x1 + "," + f(b.a0) + " C" + xm + "," + f(b.a0) + " " + xm + "," + f(b.b0) + " " + b.x2 + "," + f(b.b0) +
      " L" + b.x2 + "," + f(b.b1) + " C" + xm + "," + f(b.b1) + " " + xm + "," + f(b.a1) + " " + b.x1 + "," + f(b.a1) + " Z";
  }
  function kenarYolu(b) {
    var xm = (b.x1 + b.x2) / 2;
    return "M" + b.x1 + "," + f(b.a0) + " C" + xm + "," + f(b.a0) + " " + xm + "," + f(b.b0) + " " + b.x2 + "," + f(b.b0) +
      " M" + b.x1 + "," + f(b.a1) + " C" + xm + "," + f(b.a1) + " " + xm + "," + f(b.b1) + " " + b.x2 + "," + f(b.b1);
  }

  function sema() {
    var r = durum.rapor, a = r.akis, kutu = $("sema"), dar = durum.dar, gruplar = a.gruplar, n = gruplar.length;
    kutu.innerHTML = "";
    if (!n) { kutu.appendChild(el("p", { sinif: "not", metin: "Bu dönemde çekim akışı yok." })); durum.geo = null; Akis.kur(null); return; }
    var W = dar ? 640 : 1000, nw = dar ? 9 : 10;
    var xL = dar ? 18 : 236, xM = dar ? 262 : 520, xR = dar ? 430 : 770, ust = dar ? 186 : 64, aralik = dar ? 18 : 22;
    var toplam = gruplar.reduce(function (s, g) { return s + g.deger; }, 0) || 1;
    var Hb = Math.max(dar ? 320 : 300, n * (dar ? 70 : 62));
    var k = (Hb - aralik * (n - 1)) / toplam, y = ust;
    var sag = gruplar.map(function (g) { var t = Math.max(3, g.deger * k), o = { g: g, y0: y, y1: y + t, t: t }; y += t + aralik; return o; });
    var akisT = sag.reduce(function (s, o) { return s + o.t; }, 0);
    var mTop = ust + (y - aralik - ust - akisT) / 2;
    var etiketY = [], son = -Infinity, adim = dar ? 64 : 60;
    sag.forEach(function (o) { var v = Math.max((o.y0 + o.y1) / 2, son + adim); etiketY.push(v); son = v; });
    var acil = r.uyarilar.liste.filter(function (x) { return x.tur === "bot_uyusmazlik"; });
    var H = Math.max(y - aralik, son + 34, mTop + akisT + (acil.length ? 74 : 20)) + 10;

    var kaynakB = { x1: xL + nw, a0: mTop, a1: mTop + akisT, x2: xM, b0: mTop, b1: mTop + akisT };
    kaynakB.L = (kaynakB.x2 - kaynakB.x1) * 1.03;
    var bantlar = [{ tur: "kaynak", b: kaynakB }], my = mTop;
    sag.forEach(function (o) {
      var b = { x1: xM + nw, a0: my, a1: my + o.t, x2: xR, b0: o.y0, b1: o.y1 };
      b.L = Math.sqrt(Math.pow(b.x2 - b.x1, 2) + Math.pow((b.b0 + b.b1 - b.a0 - b.a1) / 2, 2)) * 1.08;
      my += o.t;
      bantlar.push({ tur: "grup", g: o.g, b: b });
    });
    durum.bantlar = bantlar;
    durum.geo = { vbW: W, vbH: H, kaynak: kaynakB, sag: bantlar.slice(1).map(function (x) { return x.b; }) };

    var kay = a.kaynak, s = "";
    s += "<defs>" +
      '<linearGradient id="g-akis" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#f6b445"/><stop offset="1" stop-color="#ffd98e"/></linearGradient>' +
      '<linearGradient id="g-kenar" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#f6b445" stop-opacity=".95"/><stop offset="1" stop-color="#ffd98e" stop-opacity=".35"/></linearGradient>' +
      '<linearGradient id="g-cikis" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#7cb8ff"/><stop offset="1" stop-color="#b3d4ff"/></linearGradient>' +
      '<linearGradient id="g-cikis-kenar" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#7cb8ff" stop-opacity=".95"/><stop offset="1" stop-color="#b3d4ff" stop-opacity=".4"/></linearGradient>' +
      '<filter id="parilti" x="-300%" y="-20%" width="700%" height="140%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
      '<filter id="parilti-k" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
      '<clipPath id="perde" clipPathUnits="userSpaceOnUse"><rect id="perde-rect" x="0" y="-20" width="' + W + '" height="' + f(H + 40) + '"/></clipPath>' +
      "</defs>";
    s += '<g clip-path="url(#perde)">';
    bantlar.forEach(function (x, i) {
      var aria = x.tur === "kaynak" ? kay.ad + " → Sen: " + (kay.tutar || "") + ", " + kay.cekim_sayisi + " çekim"
        : "Sen → " + x.g.ad + ": " + (x.g.tutar || (x.g.alt || []).map(function (z) { return z.ad + " " + z.tutar; }).join(", ")) +
          (x.g.cekim_sayisi ? ", " + x.g.cekim_sayisi + " çekim" : "");
      s += '<g class="bant' + (i === 0 ? " kaynak" : "") + '" tabindex="' + (i === 0 ? 0 : -1) + '" role="button" data-i="' + i + '" aria-label="' + esc(aria) + '">' +
        '<path class="b" d="' + bantYolu(x.b) + '"/><path class="kenar" d="' + kenarYolu(x.b) + '"/>' +
        '<path d="' + bantYolu(x.b) + '" fill="none" stroke="transparent" stroke-width="12" pointer-events="stroke"/></g>';
    });
    s += "</g>";
    // düğümler
    s += '<rect class="dugum kaynak" x="' + xL + '" y="' + f(mTop) + '" width="' + nw + '" height="' + f(akisT) + '" rx="' + nw / 2 + '"/>';
    s += '<rect class="dugum sen" x="' + xM + '" y="' + f(mTop) + '" width="' + nw + '" height="' + f(akisT) + '" rx="' + nw / 2 + '"/>';
    sag.forEach(function (o) {
      s += '<rect class="dugum" x="' + xR + '" y="' + f(o.y0) + '" width="' + nw + '" height="' + f(o.t) + '" rx="' + f(Math.min(nw / 2, o.t / 2)) + '"/>';
    });
    // kaynak etiketi (dar ekranda düğümün üstünde)
    var sx = dar ? xL : xL - 22, anc = dar ? "start" : "end", ky = dar ? mTop - 132 : mTop + akisT / 2 - 24;
    s += '<g class="etiket sol"><text x="' + sx + '" y="' + f(ky) + '" text-anchor="' + anc + '" class="ad">' + esc(kay.ad) + "</text>" +
      '<text x="' + sx + '" y="' + f(ky + 46) + '" text-anchor="' + anc + '" class="tutar buyuk" data-sayi="' + esc(kay.tutar || "") + '">' + esc(kay.tutar || "") + "</text>" +
      '<text x="' + sx + '" y="' + f(ky + 72) + '" text-anchor="' + anc + '" class="kucuk" data-sayi="' + esc(kay.cekim_sayisi + " çekim") + '">' + esc(kay.cekim_sayisi + " çekim") + "</text></g>";
    var bakiye = borsaBakiyesi();
    s += '<g class="bakiye' + (bakiye ? "" : " gizli") + '" role="button" tabindex="0" aria-label="' + esc(bakiye ? "OKX TR bakiyesi " + bakiye + "; gizlemek için dokun" : "OKX TR bakiyesi gizli; göstermek için dokun") + '">' +
      '<text x="' + sx + '" y="' + f(ky + 102) + '" text-anchor="' + anc + '">' +
      esc(bakiye ? "Bakiye " + bakiye : r.gizli ? "Bakiye gizli" : r.veri_turu === "örnek" ? "Bakiye örnek veride yok" : "Bakiye okunamadı") + "</text></g>";
    // Sen
    s += '<g class="etiket orta"><text x="' + (xM + nw / 2) + '" y="' + f(mTop - 36) + '" text-anchor="middle" class="sen-ad">Sen</text>' +
      '<text x="' + (xM + nw / 2) + '" y="' + f(mTop - 14) + '" text-anchor="middle" class="kucuk" data-sayi="' + esc(kay.adres_sayisi + " adres") + '">' +
      esc(kay.adres_sayisi + " adres") + "</text>" +
      (r.kalan && r.kalan.dolar ? '<text x="' + (xM + nw / 2) + '" y="' + f(mTop + akisT + 26) + '" text-anchor="middle" class="kucuk">' + esc("cüzdanlarda ≈ " + r.kalan.dolar) + "</text>" : "") + "</g>";
    // ağlar
    sag.forEach(function (o, i) {
      var ly = etiketY[i], lx = xR + nw + 16, orta = (o.y0 + o.y1) / 2, g = o.g;
      s += '<g class="etiket sag" data-i="' + (i + 1) + '">';
      if (Math.abs(ly - orta) > 4) s += '<path class="ince" d="M' + (xR + nw + 3) + "," + f(orta) + " L" + (lx - 5) + "," + f(ly - 8) + '"/>';
      s += '<text x="' + lx + '" y="' + f(ly - 8) + '" class="ad"' + (g.id !== "diger" ? ' lang="en"' : "") + ">" + esc(g.ad) + "</text>";   // ARBITRUM, ARBİTRUM değil
      if (g.tutar) {
        s += '<text x="' + lx + '" y="' + f(ly + 22) + '" class="tutar"><tspan data-sayi="' + esc(g.tutar) + '">' + esc(g.tutar) + "</tspan>" +
          (g.cekim_sayisi && !dar ? '<tspan class="kucuk" dx="10">' + esc(g.cekim_sayisi + " çekim") + "</tspan>" : "") + "</text>";
      } else {
        s += '<text x="' + lx + '" y="' + f(ly + 16) + '" class="kucuk">' + esc((g.alt || []).map(function (z) { return z.ad; }).join(" · ")) + "</text>";
      }
      s += "</g>";
    });
    // Bot kaydı tutmuyorsa kırmızı işaret borsanın üstünde (botlar borsada çalışır)
    if (acil.length) {
      var mx = xL + nw / 2, iy = mTop + akisT + 40, sayi = r.uyarilar.acil > 1 ? " · " + r.uyarilar.acil : "";
      s += '<g class="isaret" tabindex="0" role="button" aria-label="' + esc(acil[0].baslik + sayi + ": ayrıntıyı aç") + '">' +
        '<path class="cizgi" d="M' + mx + "," + f(mTop + akisT + 6) + " V" + f(iy - 9) + '"/>' +
        '<circle class="halka" cx="' + mx + '" cy="' + f(iy) + '" r="6"/><circle class="cekirdek" cx="' + mx + '" cy="' + f(iy) + '" r="5"/>' +
        '<text x="' + (dar ? mx + 16 : mx - 16) + '" y="' + f(iy + 5) + '" text-anchor="' + (dar ? "start" : "end") + '">' + esc(acil[0].baslik + sayi) + "</text></g>";
    }
    kutu.innerHTML = '<svg viewBox="0 0 ' + W + " " + f(H) + '" class="' + (dar ? "dar" : "") + '" role="presentation">' + s + "</svg>";
    var bk = kutu.querySelector(".bakiye");
    if (bk) {
      bk.addEventListener("click", function () { $("gizli").click(); });
      bk.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("gizli").click(); } });
    }
    bagla();
    Akis.kur(durum.geo);
  }

  function okumaMetni(i) {
    var x = durum.bantlar[i], kay = durum.rapor.akis.kaynak;
    if (x.tur === "kaynak") return "<b class=\"giris\">" + esc(kay.tutar || "") + "</b><span>" + esc(kay.ad) + " → Sen · " + esc(kay.cekim_sayisi) + " çekim</span>";
    var g = x.g;
    if (g.tutar) return "<b class=\"cikis\">" + esc(g.tutar) + "</b><span>Sen → " + esc(g.ad) + " · " + esc(g.cekim_sayisi) + " çekim</span>";
    return "<b>" + esc(g.ad) + "</b><span>" + esc((g.alt || []).map(function (z) { return z.ad + " " + z.tutar; }).join(" · ")) + "</span>";
  }

  function bagla() {
    var svg = $("sema").querySelector("svg");
    if (!svg) return;
    var gs = Array.prototype.slice.call(svg.querySelectorAll(".bant"));
    var etiketler = Array.prototype.slice.call(svg.querySelectorAll(".etiket.sag"));
    var okuma = $("okuma"), akis = $("akis");
    function goster(i, olay, sessiz) {
      svg.classList.add("vurgu");
      gs.forEach(function (g, j) { g.classList.toggle("secili", j === i); });
      etiketler.forEach(function (e) { e.classList.toggle("secili", i === 0 || +e.getAttribute("data-i") === i); });
      Akis.vurgula(i);
      if (sessiz) { okuma.hidden = true; return; }
      okuma.innerHTML = okumaMetni(i);
      okuma.hidden = false;
      var kr = akis.getBoundingClientRect(), x, y;
      if (olay && olay.clientX != null) { x = olay.clientX - kr.left; y = olay.clientY - kr.top; }
      else { var br = gs[i].getBoundingClientRect(); x = br.left + br.width / 2 - kr.left; y = br.top + br.height / 2 - kr.top; }
      okuma.style.left = Math.max(110, Math.min(kr.width - 110, x)) + "px";
      okuma.style.top = y + "px";
    }
    function birak() {
      if (durum.secili !== null) return goster(durum.secili, null, true);
      svg.classList.remove("vurgu");
      gs.forEach(function (g) { g.classList.remove("secili"); });
      etiketler.forEach(function (e) { e.classList.remove("secili"); });
      Akis.vurgula(null);
      okuma.hidden = true;
    }
    // Dinleyiciler her SVG'ye yalnız bir kez eklenir. Eskiden panelAc/panelKapat her çağrıda yeniden ekliyordu:
    // her tıklama dinleyici sayısını katlıyor, bantlar arasında hızlı tıklayınca sayfa donuyordu (17 Ekim provası).
    if (svg.getAttribute("data-bagli") !== "1") {
      svg.setAttribute("data-bagli", "1");
      gs.forEach(function (g, i) {
        g.addEventListener("mousemove", function (e) { goster(i, e); });
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
      var isaret = svg.querySelector(".isaret");
      if (isaret) {
        isaret.addEventListener("click", function () { kip(true, "bot"); });
        isaret.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); kip(true, "bot"); } });
      }
    }
    if (durum.secili !== null && gs[durum.secili]) goster(durum.secili, null, true); else birak();
  }

  /* ---------- parçacıklar: para altın taneler hâlinde akar ---------- */
  // Her tane kaynak bandında bir şeritte doğar; Sen düğümüne vardığında o yükseklikteki ağ bandına geçer.
  // Böylece taneler ağlara tutarla orantılı dağılır (kalın bant = çok tane); sayı uydurulmaz, yalnız geometri kullanılır.
  var Akis = (function () {
    var cv = $("parcacik"), ctx = cv.getContext("2d"), geo = null, parcalar = [], olcek = 1, dpr = 1;
    var calisiyor = false, onceki = 0, yog = 0, hedefYog = 0, vurgu = null, HIZ = 118;
    function taneCiz(ic, orta, dis) {
      var c = document.createElement("canvas"); c.width = c.height = 48;
      var g = c.getContext("2d"), r = g.createRadialGradient(24, 24, 0, 24, 24, 24);
      r.addColorStop(0, ic); r.addColorStop(0.16, orta);
      r.addColorStop(0.42, dis + ".32)"); r.addColorStop(1, dis + "0)");
      g.fillStyle = r; g.fillRect(0, 0, 48, 48);
      return c;
    }
    var tane = taneCiz("rgba(255,244,214,1)", "rgba(255,216,142,.95)", "rgba(246,180,69,");        // giriş (sana gelen): altın
    var taneCikis = taneCiz("rgba(232,243,255,1)", "rgba(179,212,255,.95)", "rgba(124,184,255,");  // çıkış (ağlara giden): mavi
    function bz(p0, p1, p2, p3, t) { var u = 1 - t; return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3; }
    function nokta(b, t, s) {
      var xm = (b.x1 + b.x2) / 2, ya = b.a0 + s * (b.a1 - b.a0), yb = b.b0 + s * (b.b1 - b.b0);
      return [bz(b.x1, xm, xm, b.x2, t), bz(ya, ya, yb, yb, t)];
    }
    function hedef(y) {
      for (var i = 0; i < geo.sag.length; i++) if (y < geo.sag[i].a1) return i;
      return geo.sag.length - 1;
    }
    function yeni(p, rastgele) {
      var k = geo.kaynak;
      p.s = 0.04 + Math.random() * 0.92;
      var y = k.a0 + p.s * (k.a1 - k.a0), h = hedef(y), b = geo.sag[h];
      p.h = h;
      p.s2 = Math.min(0.94, Math.max(0.06, (y - b.a0) / Math.max(0.001, b.a1 - b.a0)));
      p.asama = 0; p.t = rastgele ? Math.random() : 0;
      p.v = 0.72 + Math.random() * 0.6; p.r = 1 + Math.random() * 1.6; p.parla = Math.random() < 0.1;
      return p;
    }
    function boyut() {
      if (!geo) return;
      var w = $("sema").clientWidth;
      if (!w) return;
      var h = w * geo.vbH / geo.vbW;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      cv.style.width = w + "px"; cv.style.height = h + "px";
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      olcek = w / geo.vbW;
    }
    function kur(g) {
      geo = g; parcalar = [];
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, cv.width, cv.height);
      if (!g || HAREKETSIZ) return;
      boyut();
      var n = durum.dar ? 90 : 170;
      for (var i = 0; i < n; i++) {
        var p = yeni({}, true);
        if (Math.random() < 0.5) { p.asama = 1; p.t = Math.random(); }
        parcalar.push(p);
      }
      if (!calisiyor) { calisiyor = true; onceki = performance.now(); requestAnimationFrame(kare); }
    }
    function kare(simdi) {
      requestAnimationFrame(kare);
      var dt = Math.min(0.05, Math.max(0, (simdi - onceki) / 1000)); onceki = simdi;
      if (!geo || document.hidden || $("sade").hidden) return;
      yog += (hedefYog - yog) * Math.min(1, dt * 2.4);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, cv.width, cv.height);
      if (yog < 0.01) return;
      ctx.setTransform(dpr * olcek, 0, 0, dpr * olcek, 0, 0);
      ctx.globalCompositeOperation = "lighter";
      for (var i = 0; i < parcalar.length; i++) {
        var p = parcalar[i], b = p.asama === 0 ? geo.kaynak : geo.sag[p.h];
        p.t += dt * p.v * HIZ / b.L;
        if (p.t >= 1) {
          if (p.asama === 0) { p.asama = 1; p.t -= 1; b = geo.sag[p.h]; }
          else { yeni(p, false); b = geo.kaynak; }
        }
        var s = p.asama === 0 ? p.s : p.s2, a = yog;
        if (vurgu !== null && vurgu !== 0) a *= p.h + 1 === vurgu ? 1 : 0.12;
        if (p.asama === 0 && p.t < 0.07) a *= p.t / 0.07;          // borsadan çıkarken belirir
        if (p.asama === 1 && p.t > 0.9) a *= (1 - p.t) / 0.1;      // ağa varınca söner
        for (var k = 0; k < 4; k++) {
          var tt = p.t - k * 0.016;
          if (tt < 0) break;
          var xy = nokta(b, tt, s), boy = p.r * (p.parla ? 4.4 : 3.2) * (1 - k * 0.2);
          ctx.globalAlpha = Math.max(0, a * (k === 0 ? 0.95 : 0.3 * (1 - k * 0.25)));
          ctx.drawImage(p.asama === 0 ? tane : taneCikis, xy[0] - boy, xy[1] - boy, boy * 2, boy * 2);
        }
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    }
    return {
      kur: kur, boyut: boyut,
      vurgula: function (i) { vurgu = i; },
      yogunluk: function (v, hemen) { hedefYog = v; if (hemen) yog = v; }
    };
  })();

  /* ---------- giriş hareketi (GSAP) ---------- */
  // Para hangi sırayla aktıysa öyle çizilir: borsa → Sen → ağlar; sayılar koddan gelen değere sayarak varır.
  function sayac(t, tl, an) {
    var metin = t.getAttribute("data-sayi") || "", m = /^([+\-−]?)(\d{1,3}(?:\.\d{3})+|\d+)(,\d+)?(.*)$/.exec(metin);
    if (!m) return;
    var ondalik = m[3] ? m[3].length - 1 : 0, hedef = parseFloat(m[2].replace(/\./g, "") + (m[3] ? "." + m[3].slice(1) : ""));
    var bicim = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: ondalik, maximumFractionDigits: ondalik }), o = { v: 0 };
    t.textContent = m[1] + bicim.format(0) + m[4];
    tl.to(o, { v: hedef, duration: 1.8, ease: "power3.out",
      onUpdate: function () { t.textContent = m[1] + bicim.format(o.v) + m[4]; },
      onComplete: function () { t.textContent = metin; } }, an);
  }
  function giris() {
    var svg = $("sema").querySelector("svg");
    if (!svg || !durum.geo) { document.body.classList.remove("bekle"); return; }
    Akis.yogunluk(0, true);
    var tl = G.timeline({ defaults: { ease: "expo.out" } }), b = $("baslik");
    if (window.SplitText && !durum.split) {
      try { G.registerPlugin(window.SplitText); durum.split = new window.SplitText(b, { type: "words", mask: "words" }); } catch (e) { durum.split = null; }
    }
    if (durum.split) tl.from(durum.split.words, { yPercent: 118, duration: 1.25, stagger: 0.08 }, 0);
    else tl.from(b, { autoAlpha: 0, y: 18, duration: 0.9 }, 0);
    tl.from(["#donem", "#alt-baslik"], { autoAlpha: 0, y: 12, duration: 0.9, stagger: 0.06, clearProps: "all" }, 0.15);
    var perde = svg.querySelector("#perde-rect");
    if (perde) tl.fromTo(perde, { attr: { width: 0 } }, { attr: { width: durum.geo.vbW }, duration: 1.5, ease: "power3.inOut" }, 0.3);
    tl.from(svg.querySelectorAll(".dugum"), { scaleY: 0, transformOrigin: "50% 50%", duration: 1, stagger: 0.07 }, 0.25);
    tl.from(svg.querySelectorAll(".etiket"), {
      autoAlpha: 0, duration: 1, stagger: 0.06, clearProps: "opacity,visibility,transform",
      x: function (i, e) { return e.classList.contains("sol") ? -16 : e.classList.contains("sag") ? 16 : 0; },
      y: function (i, e) { return e.classList.contains("orta") ? 10 : 0; }
    }, 0.55);
    Array.prototype.forEach.call(svg.querySelectorAll("[data-sayi]"), function (t) { sayac(t, tl, 0.6); });
    tl.from(svg.querySelectorAll(".bakiye"), { autoAlpha: 0, x: -16, duration: 1, clearProps: "all" }, 0.8);
    tl.from(".lejant", { autoAlpha: 0, y: 8, duration: 0.8, clearProps: "all" }, 1.05);
    tl.from(".kus-golge", { autoAlpha: 0, duration: 2.2, ease: "power2.out", clearProps: "opacity,visibility" }, 0.4);
    tl.add(function () { Akis.yogunluk(1); }, 0.7);
    tl.from(svg.querySelectorAll(".isaret"), { autoAlpha: 0, scale: 0.3, transformOrigin: "50% 50%", duration: 0.9, ease: "back.out(2.2)", clearProps: "all" }, 1.45);
    tl.from("#kartlar > *", { autoAlpha: 0, y: 28, duration: 1, stagger: 0.09, clearProps: "all" }, 1.15);   // :hover yükselmesi çalışsın
    tl.from("#detaya-in", { autoAlpha: 0, y: 14, duration: 0.8, clearProps: "all" }, 1.45);
    document.body.classList.remove("bekle");
  }

  /* ---------- kartlar: en çok üç ---------- */
  function kart(ton, ust, buyuk, alt, sekme, metinli) {
    var b = el("button", { type: "button", sinif: "kart " + ton });
    b.appendChild(el("span", { sinif: "kart-ust" }, [ust]));
    if (buyuk) b.appendChild(el("span", { sinif: "kart-buyuk" }, buyuk));
    if (alt) b.appendChild(el("span", { sinif: metinli ? "kart-metin" : "kart-alt", metin: alt }));
    b.addEventListener("click", function () { kip(true, sekme); });
    return b;
  }
  function kisa(m) {
    m = String(m || "");
    var i = m.indexOf(";");
    return (i > 20 ? m.slice(0, i) : m).replace(/\s*ayrıntı defterde\.?$/, "").trim();
  }
  function aciklanamayan() {
    var k = durum.rapor.kopru;
    if (!k) return null;
    var kap = k.kapsamlar.servet || k.kapsamlar[Object.keys(k.kapsamlar)[0]];
    var o = kap && kap.ozet.filter(function (x) { return x.ad === "Açıklanamayan"; })[0];
    return o ? o.dolar || null : null;
  }
  function kartlar() {
    var r = durum.rapor, u = r.uyarilar, k = $("kartlar"), liste = [];
    k.innerHTML = "";
    if (r.kartlar) {
      r.kartlar.forEach(function (x) {
        k.appendChild(kart(x.ton, x.ust, x.buyuk ? [el("span", { metin: x.buyuk })] : null, x.buyuk ? x.alt : x.metin, x.sekme, !x.buyuk));
      });
      return;
    }
    var bot = u.liste.filter(function (x) { return x.tur === "bot_uyusmazlik" && x.kayit; })[0];
    if (bot) {
      liste.push(kart("acil", bot.baslik + (u.acil > 1 ? " · " + u.acil : ""),
        [el("span", { metin: bot.kayit }), ikon("ok"), el("span", { sinif: "kotu", metin: bot.gercek })], "borsanın kaydı → hesaba dönen", "bot"));
    }
    u.liste.filter(function (x) { return x !== bot && x.tur !== "bot_uyusmazlik"; }).slice(0, bot ? 1 : 2).forEach(function (x) {
      liste.push(kart(x.onem, x.baslik || "Uyarı", null, kisa(x.metin), "uyarilar", true));
    });
    var ac = aciklanamayan();
    if (ac) {
      var kapandi = /^0( |$)/.test(ac);
      liste.push(kart(kapandi ? "tamam" : "orta", kapandi ? "Defter kapandı" : "Açıklanamayan fark", [el("span", { metin: ac })],
        "dün → bugün, açıklanamayan tutar", "ozet"));
    }
    if (!liste.length) liste.push(kart("tamam", "Uyarı yok", [el("span", { metin: "Sorun görmedim" })], "", "uyarilar"));
    liste.slice(0, 3).forEach(function (x) { k.appendChild(x); });
  }

  /* ---------- bant çekmecesi ---------- */
  function cumleler(liste) {
    var d = el("div");
    if (!liste.length) { d.appendChild(el("p", { sinif: "not", metin: "Bu bant için cümle yok." })); return d; }
    liste.forEach(function (c, i) {
      d.appendChild(el("div", { sinif: "cumle", hidden: i >= 3 ? "" : null }, [el("p", { metin: c.metin }),
        el("small", { metin: cumleEtiketi(c) + " · olgu " + c.olgular.join(", ") })]));
    });
    if (liste.length > 3) {
      var b = el("button", { type: "button", sinif: "baglanti", metin: "Hepsi (" + liste.length + ")" });
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(d.querySelectorAll(".cumle[hidden]"), function (x) { x.hidden = false; });
        b.remove();
      });
      d.appendChild(b);
    }
    return d;
  }
  function kapsamCipleri(k) {
    var d = el("div", { sinif: "cipler" });
    if (!k || !k.adres) { d.appendChild(el("span", { sinif: "cip yok", metin: "kayıtlı adres yok" })); return d; }
    d.appendChild(el("span", { sinif: "cip" }, [k.adres + " adres" + (k.benim_tahmini ? " · " + k.benim_tahmini + " senin (tahmin)" : "")]));
    k.katmanlar.forEach(function (x) { d.appendChild(el("span", { sinif: "cip" }, [ikon("tamam"), x])); });
    k.eksik.forEach(function (x) { d.appendChild(el("span", { sinif: "cip yok" }, [ikon("eksik"), x + ": okunamadı"])); });
    return d;
  }
  function panelAc(i, sessiz) {
    var x = durum.bantlar[i], r = durum.rapor, ic = $("panel-icerik");
    if (!x) return;
    durum.secili = i;
    ic.innerHTML = "";
    if (x.tur === "kaynak") {
      var kay = r.akis.kaynak;
      $("panel-baslik").textContent = kay.ad + " → Sen";
      ic.appendChild(el("p", { sinif: "buyuk-sayi", metin: kay.tutar || "—" }));
      ic.appendChild(el("p", { sinif: "meta", metin: kay.cekim_sayisi + " çekim · " + kay.adres_sayisi + " adres" }));
      ic.appendChild(el("p", { sinif: "not", metin: r.akis.not }));
      ic.appendChild(el("h3", { metin: "Ne oldu" }));
      ic.appendChild(cumleler(r.ozet || []));
    } else {
      var g = x.g;
      $("panel-baslik").textContent = "Sen → " + g.ad;
      if (g.tutar) ic.appendChild(el("p", { sinif: "buyuk-sayi cikis", metin: g.tutar }));
      if (g.cekim_sayisi) ic.appendChild(el("p", { sinif: "meta", metin: g.cekim_sayisi + " çekim · çekim anındaki dolar karşılığı" }));
      (g.alt || [g]).forEach(function (z) {
        ic.appendChild(el("h3", { metin: g.alt ? z.ad + " · " + z.tutar + " · " + z.cekim_sayisi + " çekim" : "Okunan katmanlar" }));
        ic.appendChild(kapsamCipleri(z.kapsam));
        ic.appendChild(el("h3", { metin: "Ne oldu" }));
        ic.appendChild(cumleler(z.cumleler));
      });
    }
    $("panel").hidden = false;
    if (!sessiz) { $("panel").focus(); duyur($("panel-baslik").textContent + " açıldı"); }
    bagla();
  }
  function panelKapat() {
    if ($("panel").hidden) return;
    var i = durum.secili;
    durum.secili = null;
    $("panel").hidden = true;
    bagla();
    var gs = $("sema").querySelectorAll(".bant");
    Array.prototype.forEach.call(gs, function (g) { g.setAttribute("tabindex", "-1"); });
    if (gs[i]) { gs[i].setAttribute("tabindex", "0"); gs[i].focus({ preventScroll: true }); }
  }

  /* ---------- sade / detay ---------- */
  function kip(detay, sekme) {
    if (sekme) durum.sekme = sekme;
    var simdiDetay = !$("detay").hidden;
    function uygula() {
      $("sade").hidden = detay; $("detay").hidden = !detay;
      $("sade-dugme").setAttribute("aria-selected", String(!detay));
      $("detay-dugme").setAttribute("aria-selected", String(detay));
      if (detay) { $("panel").hidden = true; durum.secili = null; if (durum.ayrinti) ayrintiCiz(); }
    }
    if (simdiDetay !== detay && document.startViewTransition && !HAREKETSIZ) document.startViewTransition(uygula); else uygula();
    var hash = detay ? "#detay" : "";
    if (location.hash !== hash) history.replaceState(null, "", location.pathname + location.search + hash);
    if (detay) { if (!durum.ayrinti || durum.ayrinti.gizli !== durum.gizli) ayrintiYukle(); }
    else if (durum.rapor && durum.rapor.gizli !== durum.gizli) yukle();
    else setTimeout(Akis.boyut, 50);
    window.scrollTo(0, 0);
  }
  function sekmeleriGuncelle() {
    Array.prototype.forEach.call($("ayrinti-sekmeler").querySelectorAll("button"), function (b) {
      var secili = b.getAttribute("data-sekme") === durum.sekme;
      b.setAttribute("aria-selected", String(secili));
      $("sekme-" + b.getAttribute("data-sekme")).hidden = !secili;
    });
  }
  function ayrintiYukle(arkaPlan) {
    var p = { gizli: durum.gizli ? "1" : "0" };
    if (durum.oturum) p.oturum = durum.oturum;
    if (!arkaPlan) $("detay").setAttribute("aria-busy", "true");
    return api("/api/ayrinti", p).then(function (a) {
      durum.ayrinti = a;
      muhurRozeti();
      if (!$("detay").hidden) ayrintiCiz();
    }).catch(function (e) {
      if (!arkaPlan) $("ayrinti-durum").textContent = e.message === "Veri kaynağı hazırlanmadı." ? e.message : "Ayrıntılar okunamadı.";
    }).finally(function () { $("detay").setAttribute("aria-busy", "false"); });
  }
  function ayrintiCiz() {
    var a = durum.ayrinti;
    $("ayrinti-durum").textContent = gunTr(a.oturum) + (a.gizli ? " · gizli mod" : "");
    sekmeleriGuncelle();
    ozetCiz(); uyarilarCiz(a); botCiz(a); hareketlerCiz(a); kanitCiz(a);
  }
  function muhurRozeti() {
    var a = durum.ayrinti, r = $("muhur-rozet"), mu = a && a.muhur;
    r.innerHTML = "";
    if (mu && mu.gun_muhru) {
      r.appendChild(ikon("muhur"));
      r.appendChild(el("a", { href: mu.gun_muhru.gezgin, target: "_blank", rel: "noopener noreferrer", metin: gunTr(mu.gun) + " Avalanche'ta mühürlü" }));
    } else if (mu && mu.son && mu.son.length) {
      r.appendChild(ikon("muhur"));
      r.appendChild(el("a", { href: mu.son[0].gezgin, target: "_blank", rel: "noopener noreferrer", metin: "Son mühür " + gunTr(mu.son[0].gun) + " · Avalanche" }));
    }
    r.hidden = !r.childNodes.length;
  }
  function tabloKur(basliklar, satirlar) {
    var t = el("table"), b = el("tbody");
    t.appendChild(el("thead", null, [el("tr", null, basliklar.map(function (h) { return el("th", { metin: h }); }))]));
    satirlar.forEach(function (s) { b.appendChild(s); });
    t.appendChild(b);
    return el("div", { sinif: "tablo-sar" }, [t]);
  }

  // Özet: dün → bugün köprüsü, akış tablosu, "bu adres senin mi?"
  function ozetCiz() {
    var k = $("sekme-ozet"), r = durum.rapor;
    k.innerHTML = "";
    if (!r) return;
    var iz = el("div", { sinif: "izgara" });
    var b1 = el("div", { sinif: "blok" });
    if (r.tarayici) {
      var bk = borsaBakiyesi();
      b1.appendChild(el("h3", { metin: "Hesap" }));
      b1.appendChild(el("p", { sinif: "olcu" }, [el("b", { metin: bk || "gizli" }), bk ? "OKX TR hesap değeri, şimdi" : "Gizli mod: bakiye gösterilmez"]));
      b1.appendChild(el("p", { sinif: "not", metin: "Dünle karşılaştırma (köprü) bilgisayardaki proof1'da yapılır." }));
    } else {
      b1.appendChild(el("h3", { metin: "Dün 09.00 → bugün 09.00" }));
      kopruCiz(b1);
    }
    iz.appendChild(b1);
    var b2 = el("div", { sinif: "blok" });
    b2.appendChild(el("h3", { metin: "Akış · " + (r.akis.donem || "") }));
    b2.appendChild(akisTablosu());
    b2.appendChild(el("p", { sinif: "not", metin: r.akis.not }));
    iz.appendChild(b2);
    k.appendChild(iz);
    sahiplikCiz(k);
  }
  function kopruCiz(kutu) {
    var k = durum.rapor.kopru;
    if (!k) { kutu.appendChild(el("p", { sinif: "not", metin: "Karşılaştırma için iki günlük okuma gerekiyor." })); return; }
    var adlar = Object.keys(k.kapsamlar);
    if (adlar.indexOf(durum.kopruKapsam) < 0) durum.kopruKapsam = adlar[0];
    var sek = el("div", { sinif: "sekmeler kucuk", role: "tablist" });
    adlar.forEach(function (ad) {
      var b = el("button", { type: "button", role: "tab", "aria-selected": String(ad === durum.kopruKapsam), metin: ad === "borsa" ? "Borsa" : "Toplam" });
      b.addEventListener("click", function () { durum.kopruKapsam = ad; ozetCiz(); });
      sek.appendChild(b);
    });
    kutu.appendChild(sek);
    var kap = k.kapsamlar[durum.kopruKapsam], satirlar = el("div", { sinif: "satirlar", style: "margin-top:10px" });
    kap.ozet.forEach(function (o) {
      satirlar.appendChild(el("div", { sinif: "satir" }, [el("span", null, [o.ad, el("small", { metin: o.varliklar.join(" · ") || "değişim yok" })]),
        isaretli(el("span", { sinif: "sag", metin: o.dolar || "fiyat yok" }))]));
    });
    kutu.appendChild(satirlar);
    var liste = el("div", { sinif: "satirlar", hidden: "" }), d = el("button", { type: "button", sinif: "baglanti", metin: "Tüm kalemler (" + kap.kalemler.length + ")" });
    kap.kalemler.forEach(function (x) {
      liste.appendChild(el("div", { sinif: "satir" }, [el("span", null, [x.ad, el("small", { metin: x.aciklama })]),
        isaretli(el("span", { sinif: "sag" }, [x.varliklar.join(" · ") || "0", el("small", { metin: x.dolar || "fiyat yok" })]), x.dolar)]));
    });
    d.addEventListener("click", function () {
      liste.hidden = !liste.hidden;
      d.textContent = liste.hidden ? "Tüm kalemler (" + kap.kalemler.length + ")" : "Kalemleri gizle";
    });
    kutu.appendChild(d); kutu.appendChild(liste);
  }
  function akisTablosu() {
    var r = durum.rapor, kay = r.akis.kaynak, satirlar = [el("tr", null, [el("td", { metin: kay.ad + " → Sen" }),
      el("td", { sinif: "hucre-sag", metin: kay.tutar || "" }), el("td", { sinif: "hucre-sag", metin: kay.cekim_sayisi })])];
    r.akis.gruplar.forEach(function (g) {
      (g.alt || [g]).forEach(function (x) {
        satirlar.push(el("tr", null, [el("td", { metin: "Sen → " + x.ad }), el("td", { sinif: "hucre-sag", metin: x.tutar || "" }),
          el("td", { sinif: "hucre-sag", metin: x.cekim_sayisi || "" })]));
      });
    });
    return tabloKur(["Akış", "Tutar", "Çekim"], satirlar);
  }
  function sahiplikCiz(k) {
    var liste = durum.rapor.sahiplik.filter(function (s) { return !durum.ertelenen[s.etiket + "|" + s.ag]; });
    if (!liste.length) return;
    k.appendChild(el("h2", { metin: "Bu adres senin mi?" }));
    var izg = el("div", { sinif: "izgara" });
    var DURUM = { tahmin: "Tahmin: büyük olasılıkla senin", benim: "Sen doğruladın: senin", benim_degil: "Sen işaretledin: senin değil" };
    liste.forEach(function (s) {
      var kart = el("div", { sinif: "kart-sahip" }), durumP = el("p", { metin: DURUM[s.durum] || s.durum }), sec = el("div", { sinif: "secenekler" });
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
          sd.addEventListener("click", function () { durum.ertelenen[s.etiket + "|" + s.ag] = true; ozetCiz(); duyur("Soru kapatıldı; hiçbir şey kaydedilmedi."); });
          sec.appendChild(sd);
        }
      }
      if (s.durum === "tahmin") dugmeler();
      else { var dg = el("button", { type: "button", metin: "Değiştir" }); dg.addEventListener("click", dugmeler); sec.appendChild(dg); }
      kart.appendChild(sec);
      izg.appendChild(kart);
    });
    k.appendChild(izg);
    k.appendChild(el("p", { sinif: "not", metin: "Yanıtın yalnız proof1'ın kendi kaydına yazılır; para taşınmaz." }));
  }
  function isaretle(s, sahip, durumP, sec) {
    if (STATIK) { durumP.textContent = "Demoda yanıt kaydedilmez."; return; }
    Array.prototype.forEach.call(sec.querySelectorAll("button"), function (b) { b.disabled = true; });
    durumP.textContent = "Kaydediliyor…";
    api("/api/isaret", null, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ adres_etiket: s.etiket, ag: s.ag, sahip: sahip }) })
      .then(function () { duyur("Kaydedildi."); return yukle(); })
      .catch(function () {
        durumP.textContent = "Kaydedilemedi; yeniden dene.";
        Array.prototype.forEach.call(sec.querySelectorAll("button"), function (b) { b.disabled = false; });
      });
  }

  function uyarilarCiz(a) {
    var k = $("sekme-uyarilar"), g = a.uyarilar || [], ONEM = { acil: "Acil", orta: "Orta", bilgi: "Bilgi" };
    k.innerHTML = "";
    var toplam = g.reduce(function (s, x) { return s + x.sayi; }, 0);
    k.appendChild(el("div", { sinif: "bolum-ust" }, [el("h2", { metin: "Uyarılar" }), el("span", { sinif: "soluk", metin: toplam + " uyarı · " + g.length + " tür" })]));
    if (!g.length) { k.appendChild(el("p", { sinif: "not", metin: "Bu raporda uyarı yok." })); return; }
    var ul = el("ul", { sinif: "uyarilar" });
    g.forEach(function (x) {
      ul.appendChild(el("li", { sinif: x.onem }, [ikon("uyari"), el("div", null, [
        el("span", { sinif: "onem", metin: (x.baslik || ONEM[x.onem] || x.onem) + (x.sayi > 1 ? " · " + x.sayi + " kez" : "") + (x.canli ? " · canlı" : "") }),
        x.metin, el("small", { metin: (ONEM[x.onem] || x.onem) + " · son " + saatTr(x.son) })])]));
    });
    k.appendChild(ul);
  }

  function botCiz(a) {
    var k = $("sekme-bot"), b = a.bot;
    k.innerHTML = "";
    if (b.yok) { k.appendChild(el("p", { sinif: "not", metin: "Bot karşılaştırması bilgisayardaki proof1'da yapılır; bu hızlı görünüm yalnız çekim, yatırma ve hesap değerini okur." })); return; }
    if (!b.olgu) { k.appendChild(el("p", { sinif: "not", metin: "Bu raporda bot kaydıyla hesap arasında uyuşmazlık yok." })); return; }
    var o = b.olgu;
    k.appendChild(el("h2", { metin: o.bot + " botu" }));
    k.appendChild(el("div", { sinif: "karsilastir" }, [
      el("div", { sinif: "taraf" }, [el("small", { metin: "Borsanın kaydı" }), el("b", { metin: eksi(o.kayit_sonuc) })]),
      ikon("ok"),
      el("div", { sinif: "taraf kotu" }, [el("small", { metin: "Hesaba dönen paraya göre" }), el("b", { metin: eksi(o.gercek_sonuc) })]),
      el("p", { metin: "Fark " + o.fark + (o.neden ? " · " + o.neden : "") })]));
    var dl = el("dl", { sinif: "bilgi", style: "margin-top:20px" });
    [["Kurulum", o.kurulus], ["Durdurma", (o.durdurma || "") + (o.durdurma_tipi ? " · " + o.durdurma_tipi : "")], ["Yatırım", o.yatirim],
     ["Hesaba dönen", (o.donen_kote || "") + (o.donen_coin ? " ve " + o.donen_coin : "")]].forEach(function (x) {
      if (x[1]) { dl.appendChild(el("dt", { metin: x[0] })); dl.appendChild(el("dd", { metin: x[1] })); }
    });
    k.appendChild(dl);
    k.appendChild(el("p", { sinif: "not", metin: "Sayıları kod hesaplar (olgu " + b.olgu_no + ")." }));
    var bas = el("div", { sinif: "bolum-ust" }, [el("h2", { metin: "Araştırma izi" })]);
    if (b.kayit) bas.appendChild(el("span", { sinif: "rozet-k", metin: "kayıt: önceden alınmış gerçek yanıtlar" }));
    k.appendChild(bas);
    if (!b.iz.length) { k.appendChild(el("p", { sinif: "not", metin: "Bu rapor için araştırma izi yok." })); return; }
    var ol = el("ol", { sinif: "iz" });
    b.iz.forEach(function (s, i) {
      var sonuncu = i === b.iz.length - 1, hata = s.sonuc && s.sonuc !== "ok" && !sonuncu;
      var rozet = s.sonuc === "ok" ? el("span", { sinif: "rozet-k tamam", metin: "tamam" })
        : hata ? el("span", { sinif: "rozet-k hata", metin: s.sonuc.indexOf("reddedildi") === 0 ? "reddedildi" : "başarısız" }) : null;
      var dl2 = el("dl");
      [["Neden", s.dusunce], ["Gördü", s.gozlem], ["Karar", s.karar], [sonuncu ? "Sonuç" : "Durum", s.sonuc]].forEach(function (x) {
        if (x[1]) { dl2.appendChild(el("dt", { metin: x[0] })); dl2.appendChild(el("dd", { metin: x[1] })); }
      });
      ol.appendChild(el("li", { sinif: hata ? "hata" : "" }, [el("div", { sinif: "ust-satir" }, [s.sira + ".", el("span", { sinif: "arac-adi", metin: s.arac }), rozet]), dl2]));
    });
    k.appendChild(ol);
  }

  var TUR = { cekim: "Çekim", yatirma: "Yatırma", takas: "Takas", gonderim: "Gönderim", giris: "Giriş", ucret: "Ücret",
    bota_giris: "Bota giriş", bottan_donus: "Bottan dönüş", alim: "Alım", satim: "Satım", aktarim: "Aktarım", taninmadi: "Tanınmadı" };
  function hareketlerCiz(a) {
    var k = $("sekme-hareketler"), h = a.hareketler;
    k.innerHTML = "";
    k.appendChild(el("div", { sinif: "bolum-ust" }, [el("h2", { metin: "Defter" }),
      el("span", { sinif: "soluk", metin: (h.pencere || "") + " · " + h.toplam + " satır" + (h.toplam > h.satirlar.length ? " (ilk " + h.satirlar.length + ")" : "") })]));
    if (!h.satirlar.length) k.appendChild(el("p", { sinif: "not", metin: "Bu rapor gününde defter satırı yok." }));
    else k.appendChild(tabloKur(["Zaman", "Ne", "Miktar", "Dolar", "Nerede", "İşlem"], h.satirlar.map(function (s) {
      var ne = el("td", null, [(TUR[s.tur] || s.tur) + (s.karsi ? " · " + s.karsi : "")]);
      if (s.supheli) ne.appendChild(el("span", { sinif: "rozet-k hata", metin: "şüpheli" }));
      if (s.durum !== "ok") ne.appendChild(el("span", { sinif: "rozet-k", metin: s.durum }));
      return el("tr", { sinif: s.supheli ? "supheli" : "" }, [el("td", { sinif: "tek-satir", metin: saatTr(s.zaman) }), ne,
        isaretli(el("td", { sinif: "hucre-sag", metin: s.miktar || "" })), isaretli(el("td", { sinif: "hucre-sag", metin: s.dolar || "fiyat yok" })),
        el("td", { metin: (s.ag || s.kaynak) + " · " + s.hesap }), el("td", { sinif: "mono tek-satir", metin: kisaKimlik(s.islem) })]);
    })));
    k.appendChild(el("h2", { metin: "Doğrulanmış cümleler" }));
    var d = el("div");
    a.cumleler.forEach(function (c) {
      d.appendChild(el("div", { sinif: "cumle" }, [el("p", { metin: c.metin }),
        el("small", { metin: cumleEtiketi(c) + " · " + (c.model === "kalip" ? "kalıp" : c.model) + " · " + c.yer + " · olgu " + c.olgular.join(", ") })]));
    });
    if (!a.cumleler.length) d.appendChild(el("p", { sinif: "not", metin: "Bu rapor için cümle yok." }));
    k.appendChild(d);
  }

  function kanitCiz(a) {
    var k = $("sekme-kanitlar"), kn = a.kanit, mu = a.muhur, bu = a.butce;
    k.innerHTML = "";
    var iz = el("div", { sinif: "izgara" });
    var b1 = el("div", { sinif: "blok genis" });
    b1.appendChild(el("h3", { metin: "Okuma çağrıları" }));
    var hata = kn.gruplar.reduce(function (s, g) { return s + g.hata; }, 0);
    b1.appendChild(el("p", { sinif: "olcu" }, [el("b", { metin: String(kn.toplam) }), "çağrı · " + hata + " hata",
      el("span", { sinif: "rozet-k " + (kn.salt_okunur_hepsi ? "tamam" : "hata"), metin: kn.salt_okunur_hepsi ? "hepsi salt okunur" : "salt okunur olmayan çağrı var" })]));
    if (kn.bildirim && kn.bildirim.cagri) {
      b1.appendChild(el("p", { sinif: "not", metin: "Ayrıca " + kn.bildirim.cagri + " Telegram bildirimi: proof1'ın kendi botuna mesaj, borsaya yazmaz." }));
    }
    b1.appendChild(tabloKur(["Kaynak", "Araç / uç", "Çağrı", "Hata", "Ort.", "Kullanılan alanlar"], kn.gruplar.slice(0, 10).map(function (g) {
      return el("tr", null, [el("td", { metin: g.kaynak }), el("td", { sinif: "mono", metin: g.ad }), el("td", { sinif: "hucre-sag", metin: String(g.cagri) }),
        el("td", { sinif: "hucre-sag", metin: String(g.hata) }), el("td", { sinif: "hucre-sag", metin: g.ort_ms + " ms" }),
        el("td", { sinif: "mono", metin: g.alanlar.slice(0, 5).join(", ") + (g.alanlar.length > 5 ? " …" : "") })]);
    })));
    if (kn.gruplar.length > 10) b1.appendChild(el("p", { sinif: "not", metin: "+" + (kn.gruplar.length - 10) + " araç/uç daha." }));
    if (kn.denetim_kaydi && kn.denetim_kaydi.length) b1.appendChild(el("p", { sinif: "not", metin: "ATK'nın kendi denetim kaydında " + kn.denetim_kaydi.length + " okuma satırı var." }));
    iz.appendChild(b1);

    var b2 = el("div", { sinif: "blok" }), dl = el("dl", { sinif: "bilgi" });
    b2.appendChild(el("h3", { metin: "Mühür · Avalanche" }));
    function satir(x, y, link) {
      dl.appendChild(el("dt", { metin: x }));
      var dd = el("dd", { sinif: "mono" });
      if (link) dd.appendChild(el("a", { href: link, target: "_blank", rel: "noopener noreferrer", metin: y })); else dd.textContent = y;
      dl.appendChild(dd);
    }
    satir("Ağ", mu.ag + " · " + mu.chain_id);
    satir("ERC-8004", mu.agent_id ? "agentId " + mu.agent_id : "yok", mu.agent_id ? mu.kimlik_gezgin : null);
    if (mu.sozlesme) satir("Sözleşme", mu.sozlesme.slice(0, 6) + "…" + mu.sozlesme.slice(-4), mu.sozlesme_gezgin);
    satir("Gün", gunTr(mu.gun));
    var dogru = el("p", { sinif: "not" });
    var gosterilen = mu.gun_muhru || (mu.son && mu.son[0]) || null, hedefGun = gosterilen ? gosterilen.gun : mu.gun;
    if (!mu.gun_muhru) dogru.textContent = "Bu gün henüz mühürlenmedi." + (gosterilen ? " Son mühür yukarıda." : "");
    if (gosterilen) {
      if (!mu.gun_muhru) satir("Son mühür", gunTr(gosterilen.gun));
      satir("Kök", gosterilen.kok.slice(0, 10) + "…" + gosterilen.kok.slice(-6));
      satir("İşlem", gosterilen.islem.slice(0, 10) + "…", gosterilen.gezgin);
    }
    b2.appendChild(dl);
    b2.appendChild(dogru);
    if (gosterilen && !STATIK) {
      var dg = el("button", { type: "button", sinif: "baglanti", metin: "Zincirde doğrula" });
      var METIN = { dogrulandi: "Doğrulandı: zincirdeki kök yerel kayıtla aynı.", uyusmuyor: "Uyuşmuyor: zincirdeki kök farklı.",
        zincirde_yok: "Zincirde bu gün için kök yok.", baglanilamadi: "Zincire bağlanılamadı.",
        yerel_kayit_yok: "Yerel mühür kaydı yok.", ayar_yok: "Mühür ayarları eksik." };
      dg.addEventListener("click", function () {
        dogru.textContent = "Zincire soruluyor…";
        api("/api/muhur-dogrula", { gun: hedefGun }).then(function (d) { dogru.textContent = METIN[d.durum] || d.durum; duyur(dogru.textContent); })
          .catch(function () { dogru.textContent = METIN.baglanilamadi; });
      });
      b2.appendChild(dg);
    }
    b2.appendChild(el("p", { sinif: "not", metin: mu.not }));
    iz.appendChild(b2);

    if (!bu) { k.appendChild(iz); return; }
    var b3 = el("div", { sinif: "blok" });
    b3.appendChild(el("h3", { metin: "Anlatıcı bütçesi · " + bu.ay }));
    b3.appendChild(el("p", { sinif: "olcu" }, [el("b", { metin: bu.harcanan }), "/ " + bu.tavan]));
    var oran = Math.min(100, (parseFloat(bu.harcanan.replace(/\./g, "").replace(",", ".")) / parseFloat(bu.tavan.replace(/\./g, "").replace(",", "."))) * 100 || 0);
    b3.appendChild(el("div", { sinif: "cubuk", role: "img", "aria-label": "Bütçenin %" + Math.round(oran) + " kadarı kullanıldı" }, [el("span", { style: "width:" + oran.toFixed(1) + "%" })]));
    var dl3 = el("dl", { sinif: "bilgi" });
    [["Kalan", bu.kalan], ["Çağrı", String(bu.cagri)], ["Kip", bu.kip === "kalip" ? "kalıp cümle (tavan)" : bu.kip]].forEach(function (x) {
      dl3.appendChild(el("dt", { metin: x[0] })); dl3.appendChild(el("dd", { metin: x[1] }));
    });
    b3.appendChild(dl3);
    b3.appendChild(el("p", { sinif: "not", metin: "Aylık sert tavan: yaklaşınca küçük model, tavanda kalıp cümle." }));
    iz.appendChild(b3);
    k.appendChild(iz);
  }

  /* ---------- hesaplar: herkes kendi hesabını görür ---------- */
  function hesaplariYukle() {
    if (STATIK) {
      durum.hesaplar = [{ hesap: "ana", ad: "Örnek hesap" }].concat(durum.tarayici ? [{ hesap: "tarayici", ad: "Hesabım" }] : []);
      $("hesap-ad").textContent = durum.tarayiciAktif ? "Hesabım" : "Örnek hesap";
      menuCiz();
      return Promise.resolve();
    }
    return fetch("/api/hesaplar", { cache: "no-store" }).then(function (y) { return y.ok ? y.json() : []; }).catch(function () { return []; })
      .then(function (liste) {
        durum.hesaplar = Array.isArray(liste) && liste.length ? liste : [{ hesap: "ana", ad: "Ana hesap" }];
        var secili = durum.hesaplar.filter(function (h) { return h.hesap === (durum.hesap || "ana"); })[0];
        $("hesap-ad").textContent = secili ? secili.ad : durum.hesap ? "Hesap " + durum.hesap.slice(0, 4) : "Ana hesap";
        menuCiz();
      });
  }
  function menuCiz() {
    var m = $("hesap-menu");
    m.innerHTML = "";
    durum.hesaplar.forEach(function (h) {
      var secili = STATIK ? (h.hesap === "tarayici") === durum.tarayiciAktif : h.hesap === (durum.hesap || "ana");
      var b = el("button", { type: "button", role: "menuitemradio", "aria-checked": String(secili) }, [h.ad]);
      b.addEventListener("click", function () { menuKapat(); hesabaGec(h.hesap === "ana" ? null : h.hesap); });
      m.appendChild(b);
    });
    m.appendChild(el("hr"));
    var ekle = el("button", { type: "button", role: "menuitem", sinif: "ekle" }, [ikon("arti"), "Kendi hesabını bağla"]);
    ekle.addEventListener("click", function () { menuKapat(); baglaAc(); });
    m.appendChild(ekle);
  }
  function menuAc() {
    $("hesap-menu").hidden = false; $("hesap-dugme").setAttribute("aria-expanded", "true");
    var ilk = $("hesap-menu").querySelector("button"); if (ilk) ilk.focus();
  }
  function menuKapat() { $("hesap-menu").hidden = true; $("hesap-dugme").setAttribute("aria-expanded", "false"); }
  function hesabaGec(hesap) {
    if (STATIK) {
      durum.tarayiciAktif = hesap === "tarayici";
      $("kayit-serit").textContent = durum.tarayiciAktif ? "SENİN HESABIN · bu sekmede okundu, hiçbir yere kaydedilmedi" : "HERKESE AÇIK DEMO · anonim örnek veri";
      hesap = null;
    }
    durum.hesap = hesap; durum.oturum = null; durum.rapor = null; durum.ayrinti = null; durum.secili = null;
    $("panel").hidden = true;
    if (!STATIK) {
      var q = new URLSearchParams(location.search);
      q.delete("oturum");
      if (hesap) q.set("hesap", hesap); else q.delete("hesap");
      history.replaceState(null, "", location.pathname + (q.toString() ? "?" + q.toString() : ""));
    }
    hesaplariYukle();
    if (!$("detay").hidden) kip(false);
    yukle(true);
  }

  var ADIMLAR = ["Anahtar denetleniyor", "Borsa okunuyor", "Zincirler taranıyor", "Dolar karşılıkları", "Botlar ve köprü", "Hazır"];
  var ADIMLAR_TARAYICI = ["Anahtar denetleniyor", "Çekimler ve yatırmalar okunuyor", "Dolar karşılıkları", "Akış çiziliyor", "Hazır"];
  function baglaAc() {
    $("bagla-perde").hidden = false;
    $("bagla-demo").hidden = !STATIK;
    $("guven-yerel").hidden = STATIK;
    $("guven-statik").hidden = !STATIK;
    $("bagla-form").hidden = !!durum.tarama;
    $("bagla-ilerleme").hidden = !durum.tarama;
    if (!durum.tarama) setTimeout(function () { $("bagla-form").elements.api_key.focus(); }, 60);
  }
  function baglaKapat() { $("bagla-perde").hidden = true; $("hesap-dugme").focus(); }
  function ilerlemeCiz(sira, bitti, adimlar, ek) {
    var ol = $("ilerleme-adimlar");
    ol.innerHTML = "";
    (adimlar || ADIMLAR).forEach(function (ad, i) {
      var n = i + 1, sinif = bitti || n < sira ? "bitti" : n === sira ? "simdi" : "";
      ol.appendChild(el("li", { sinif: sinif }, [el("span", { sinif: "durum-i", "aria-hidden": "true" }), ad + (n === sira && ek ? " · " + ek : "")]));
    });
  }
  // Herkese açık sayfada: istekleri tarayıcı imzalar, doğrudan tr.okx.com'a gider (tarayici.js). Sunucu yok.
  function tarayicidaTara(kimlik) {
    taramaDurumu("tarayici");
    $("bagla-form").hidden = true; $("bagla-ilerleme").hidden = false;
    ilerlemeCiz(1, false, ADIMLAR_TARAYICI);
    var muhur = durum.ayrinti && durum.ayrinti.muhur;
    window.Proof1Tarayici.tara(kimlik, function (sira, ek) { ilerlemeCiz(sira, false, ADIMLAR_TARAYICI, ek); }, { muhur: muhur })
      .then(function (sonuc) {
        durum.tarayici = sonuc;
        taramaDurumu(null);
        ilerlemeCiz(5, true, ADIMLAR_TARAYICI);
        setTimeout(function () { baglaKapat(); hesabaGec("tarayici"); duyur("Hesabın okundu; akışın çizildi."); }, 600);
      })
      .catch(function (e) { taramaHatasi((e && e.message) || "Okunamadı."); });
  }
  function taramaDurumu(hesap) {
    durum.tarama = hesap;
    document.body.classList.toggle("taraniyor", !!hesap);
    $("hesap-dugme").title = hesap ? "Tarama sürüyor" : "";
  }
  function taramaHatasi(metin) {
    taramaDurumu(null);
    $("bagla-ilerleme").hidden = true;
    $("bagla-form").hidden = false;
    $("bagla-hata").textContent = metin;
    $("bagla-hata").hidden = false;
    $("bagla-perde").hidden = false;
  }
  function izle(hesap) {
    fetch("/api/hesap/durum?hesap=" + encodeURIComponent(hesap), { cache: "no-store" })
      .then(function (y) { return y.json(); })
      .then(function (d) {
        if (d.hata) return taramaHatasi(d.hata);
        ilerlemeCiz(d.sira || ADIMLAR.indexOf(d.adim) + 1, d.bitti);
        if (d.bitti) {
          taramaDurumu(null);
          setTimeout(function () { baglaKapat(); hesabaGec(hesap); duyur("Hesabın tarandı; panon açıldı."); }, 700);
          return;
        }
        setTimeout(function () { izle(hesap); }, 1000);
      })
      .catch(function () { setTimeout(function () { izle(hesap); }, 2000); });
  }
  $("bagla-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var form = e.target, hata = $("bagla-hata"), dugme = form.querySelector("button[type=submit]");
    var govde = JSON.stringify({ api_key: form.elements.api_key.value.trim(), secret_key: form.elements.secret_key.value.trim(),
      passphrase: form.elements.passphrase.value.trim() });
    var eksik = !form.elements.api_key.value.trim() || !form.elements.secret_key.value.trim() || !form.elements.passphrase.value.trim();
    var kimlik = STATIK ? JSON.parse(govde) : null;
    form.reset();                          // anahtar formda ve ekranda kalmaz; tarayıcıda hiçbir yere yazılmaz
    if (eksik) { govde = kimlik = null; hata.textContent = "Üç alan da gerekli."; hata.hidden = false; return; }
    if (STATIK) { govde = null; hata.hidden = true; tarayicidaTara(kimlik); kimlik = null; return; }
    hata.hidden = true;
    dugme.disabled = true;
    fetch("/api/hesap/bagla", { method: "POST", headers: { "content-type": "application/json" }, body: govde })
      .then(function (y) { return y.json().catch(function () { return {}; }).then(function (g) { if (!y.ok) throw new Error(g.hata || "Bağlanılamadı."); return g; }); })
      .then(function (g) {
        taramaDurumu(g.hesap);
        $("bagla-form").hidden = true; $("bagla-ilerleme").hidden = false;
        ilerlemeCiz(1, false);
        izle(g.hesap);
      })
      .catch(function (err) { hata.textContent = err.message === "Failed to fetch" ? "Sunucuya ulaşılamadı." : err.message; hata.hidden = false; })
      .finally(function () { dugme.disabled = false; govde = null; });
  });

  /* ---------- denetimler ---------- */
  $("gizli").addEventListener("click", function () {
    durum.gizli = !durum.gizli;
    this.setAttribute("aria-checked", String(durum.gizli));
    this.querySelector("use").setAttribute("href", durum.gizli ? "#i-goz-kapali" : "#i-goz");
    this.querySelector(".gizli-yazi").textContent = durum.gizli ? "Gizli" : "Açık";
    duyur(durum.gizli ? "Gizli mod açık: bakiyeler ve yüzdeler gizli" : "Gizli mod kapalı");
    if (!$("detay").hidden) ayrintiYukle(); else yukle();
  });
  $("sade-dugme").addEventListener("click", function () { kip(false); });
  $("detay-dugme").addEventListener("click", function () { kip(true); });
  $("detaya-in").addEventListener("click", function () { kip(true); });
  Array.prototype.forEach.call($("ayrinti-sekmeler").querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () { durum.sekme = b.getAttribute("data-sekme"); sekmeleriGuncelle(); });
  });
  window.addEventListener("hashchange", function () { kip(location.hash === "#detay" || location.hash === "#ayrintilar"); });
  $("hesap-dugme").addEventListener("click", function () { if ($("hesap-menu").hidden) menuAc(); else menuKapat(); });
  document.addEventListener("click", function (e) { if (!$("hesap-menu").hidden && !e.target.closest(".hesap")) menuKapat(); });
  $("bos-bagla").addEventListener("click", baglaAc);
  $("bagla-kapat").addEventListener("click", baglaKapat);
  $("bagla-perde").addEventListener("click", function (e) { if (e.target === this) baglaKapat(); });
  $("panel-kapat").addEventListener("click", panelKapat);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!$("bagla-perde").hidden) baglaKapat(); else if (!$("hesap-menu").hidden) menuKapat(); else panelKapat();
  });
  // Yedek ekran kaydı için: ?kayit=1 → ekranda kalıcı "KAYIT" şeridi (canlı ile karıştırılmasın).
  if (ilkSorgu.get("kayit") === "1") { $("kayit-serit").hidden = false; document.title = "proof1 · kayıt"; }
  if (STATIK) {
    $("kayit-serit").textContent = "HERKESE AÇIK DEMO · anonim örnek veri";
    $("kayit-serit").classList.add("demo");
    $("kayit-serit").hidden = false;
    durum.oturum = null;                   // demoda tek rapor var
  }
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      var w = $("akis").clientWidth;
      if (!durum.rapor || !w) return;
      if ((w < 640) !== durum.dar) { durum.dar = w < 640; sema(); } else Akis.boyut();
    }).observe($("akis"));
  }

  hesaplariYukle();
  var detaydaBasla = location.hash === "#detay" || location.hash === "#ayrintilar";
  yukle(!detaydaBasla).then(function () { if (detaydaBasla) kip(true); });
})();
