/* proof1 · tarayıcıda hızlı görünüm (herkese açık demo sayfası).
   Kullanıcı yalnız "Okuma" yetkili OKX TR anahtarını yapıştırır. İstekleri bu sekme imzalar ve doğrudan tr.okx.com'a
   gönderir (OKX TR tarayıcı isteklerine izin veriyor). Sunucumuz yok: anahtar hiçbir yere gitmez ve kaydedilmez,
   sekme kapanınca biter. Yalnız okuma uçları çağrılır; işlem ya da çekim yetkili anahtar ilk çağrıda reddedilir.
   Okunanlar: çekimler, yatırmalar, hesap değeri ve çekim günündeki dolar karşılığı (günlük mum). Bot karşılaştırması,
   zincir taraması ve mühür bilgisayardaki proof1'dadır. Sayıları kod hesaplar; model yok. */
(function () {
  "use strict";
  var TABAN = "https://tr.okx.com";
  var UCLAR = { zaman: "/api/v5/public/time", ayar: "/api/v5/account/config", cekim: "/api/v5/asset/withdrawal-history",
    yatirma: "/api/v5/asset/deposit-history", deger: "/api/v5/asset/asset-valuation", mum: "/api/v5/market/history-candles" };
  var IZINLI = Object.keys(UCLAR).map(function (k) { return UCLAR[k]; });
  var DOLAR_GIBI = { USDT: 1, USDC: 1, DAI: 1, FDUSD: 1 };
  var AYLAR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  // OKX `chain` alanındaki ağ kısmı → ad (veri/aglar.py ile aynı)
  var AGLAR = { "ERC20": "Ethereum", "Arbitrum One": "Arbitrum", "Polygon": "Polygon", "Avalanche C-Chain": "Avalanche",
    "Chiliz Chain": "Chiliz", "TRC20": "Tron", "BSC": "BNB Chain", "Base": "Base", "Optimism": "Optimism", "Solana": "Solana" };
  var TAKMA = { "BEP20": "BSC", "BNB Smart Chain": "BSC", "OPTIMISM": "Optimism", "Arbitrum": "Arbitrum One",
    "AVAX C-Chain": "Avalanche C-Chain", "Chiliz": "Chiliz Chain", "TRON": "TRC20" };
  var YAZMA = "Bu anahtarın işlem ya da çekim yetkisi var. proof1 yalnız “Okuma” yetkili anahtarla çalışır.";
  var TANIMADI = "OKX anahtarı tanımadı: anahtar, gizli anahtar ya da parola yanlış.";
  var TANIMA = ["50100", "50101", "50103", "50104", "50105", "50106", "50107", "50111", "50112", "50113", "50114"];
  var KOD_METNI = {
    "50102": "Bilgisayarının saati kaymış görünüyor; saati düzeltip yeniden dene.",
    "50110": "Bu anahtar belirli IP adreslerine bağlı. IP kısıtı olmayan bir okuma anahtarı aç ya da bu ağın IP'sini ekle.",
    "50011": "OKX şu an yoğun; birkaç saniye sonra yeniden dene."
  };

  function sayi(x) { var n = parseFloat(x); return isFinite(n) ? n : 0; }
  function trSayi(n, ondalik) {
    return new Intl.NumberFormat("tr-TR", { minimumFractionDigits: ondalik || 0, maximumFractionDigits: ondalik || 0 }).format(n);
  }
  function miktarTr(x) { return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 8 }).format(sayi(x)); }
  function dolar(n) { return trSayi(Math.round(n)) + " $"; }
  function gunTr(ms) { var d = new Date(ms); return d.getDate() + " " + AYLAR[d.getMonth() + 1] + " " + d.getFullYear(); }
  function gunBasi(ms) { var d = new Date(ms); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); }
  function agAdi(chain) {
    var k = String(chain || "");
    k = k.indexOf("-") >= 0 ? k.slice(k.indexOf("-") + 1) : k;
    k = TAKMA[k] || k;
    return AGLAR[k] || k || "Bilinmeyen";
  }
  function b64(buf) {
    var s = "", b = new Uint8Array(buf);
    for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
    return btoa(s);
  }
  function bekle(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function hataMetni(http, kod) {
    kod = String(kod || "");
    if (KOD_METNI[kod]) return KOD_METNI[kod];
    if (TANIMA.indexOf(kod) >= 0 || http === 401) return TANIMADI;
    if (http === 429) return KOD_METNI["50011"];
    return "OKX'ten okunamadı (kod " + (kod || http) + ").";
  }

  // İmzalı GET istemcisi. Gizli anahtar dışa aktarılamayan bir CryptoKey'e çevrilir; hiçbir yere yazılmaz.
  function istemci(apiKey, gizliAnahtar, parola) {
    var enc = new TextEncoder(), fark = 0, son = 0, kayit = {};
    var anahtar = crypto.subtle.importKey("raw", enc.encode(gizliAnahtar), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    function iz(yol) {
      return kayit[yol] || (kayit[yol] = { kaynak: "OKX TR", ad: "GET " + yol, cagri: 0, hata: 0, sure: [], alanlar: {}, salt_okunur: true });
    }
    function get(yol, params, imzali) {
      if (IZINLI.indexOf(yol) < 0) return Promise.reject(new Error("izinli olmayan uç"));
      var q = new URLSearchParams(params || {}).toString(), tam = yol + (q ? "?" + q : "");
      var bekleme = Math.max(0, son + 180 - Date.now());      // saniyede en çok ~5 istek: OKX'in en dar sınırı (çekim geçmişi 6/sn) altında
      son = Date.now() + bekleme;
      return bekle(bekleme).then(function () {
        if (!imzali) return {};
        var ts = new Date(Date.now() + fark).toISOString();
        return anahtar.then(function (k) { return crypto.subtle.sign("HMAC", k, enc.encode(ts + "GET" + tam)); }).then(function (imza) {
          return { "OK-ACCESS-KEY": apiKey, "OK-ACCESS-SIGN": b64(imza), "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": parola };
        });
      }).then(function (basliklar) {
        var t0 = performance.now(), k = iz(yol);
        return fetch(TABAN + tam, { method: "GET", headers: basliklar, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" })
          .then(function (y) {
            return y.json().catch(function () { return {}; }).then(function (g) {
              k.cagri++; k.sure.push(performance.now() - t0);
              if (!y.ok || String(g.code) !== "0") {
                k.hata++;
                var e = new Error(hataMetni(y.status, g.code)); e.kod = String(g.code || y.status);
                throw e;
              }
              (g.data || []).slice(0, 2).forEach(function (s) {
                if (s && typeof s === "object" && !Array.isArray(s)) Object.keys(s).forEach(function (a) { k.alanlar[a] = 1; });
              });
              return g.data || [];
            });
          }, function () { k.cagri++; k.hata++; throw new Error("OKX TR'ye ulaşılamadı; bağlantını kontrol et."); });
      });
    }
    function saatAyarla() {
      return get(UCLAR.zaman, null, false).then(function (d) { if (d[0]) fark = sayi(d[0].ts) - Date.now(); }, function () {});
    }
    return { get: get, kayit: kayit, saatAyarla: saatAyarla };
  }

  function sayfala(c, yol) {                             // `after` ile geriye doğru (veri/okx_imzali.py ile aynı)
    var hepsi = [];
    function sayfa(after, n) {
      var p = { limit: "100" };
      if (after) p.after = after;
      return c.get(yol, p, true).then(function (s) {
        hepsi = hepsi.concat(s);
        if (s.length < 100 || n >= 30) return hepsi;
        return sayfa(String(Math.min.apply(null, s.map(function (x) { return sayi(x.ts); }))), n + 1);
      });
    }
    return sayfa(null, 1);
  }

  // Çekim ve yatırma günlerinin günlük kapanışı (UTC). USDT çifti yoksa fiyat yok: dolar uydurulmaz.
  function fiyatlar(c, kayitlar, ilerleme) {
    var istek = {}, sonuc = {}, yok = {};
    kayitlar.forEach(function (k) {
      var ccy = String(k.ccy || "").toUpperCase();
      if (ccy && !DOLAR_GIBI[ccy]) istek[ccy + "|" + gunBasi(sayi(k.ts))] = 1;
    });
    var anahtarlar = Object.keys(istek), i = 0;
    function sonraki() {
      if (i >= anahtarlar.length) return Promise.resolve(sonuc);
      var a = anahtarlar[i++], ccy = a.split("|")[0], gun = +a.split("|")[1];
      if (ilerleme) ilerleme(i, anahtarlar.length);
      if (yok[ccy]) return sonraki();
      return c.get(UCLAR.mum, { instId: ccy + "-USDT", bar: "1Dutc", after: String(gun + 86400000), limit: "1" }, false)
        .then(function (d) { if (d[0]) sonuc[a] = sayi(d[0][4]); }, function (e) { if (e.kod === "51001") yok[ccy] = 1; })
        .then(sonraki);
    }
    return sonraki();
  }
  function dolarDegeri(k, fiyat) {
    var ccy = String(k.ccy || "").toUpperCase(), m = sayi(k.amt);
    if (DOLAR_GIBI[ccy]) return m;
    var f = fiyat[ccy + "|" + gunBasi(sayi(k.ts))];
    return f ? m * f : null;
  }

  // Panonun /api/rapor ve /api/ayrinti biçiminde nesneler (pano.js aynı çizer).
  function kur(cekim, yatirma, hesapDegeri, fiyat, kayit, muhur) {
    var tamam = cekim.filter(function (k) { return String(k.state) === "2"; });      // çekimde 2 = tamamlandı
    var giren = yatirma.filter(function (k) { return String(k.state) === "2"; });    // yatırmada 2 = hesaba geçti
    var gruplar = {}, adresler = {}, toplam = 0, fiyatsiz = 0, ilk = Infinity, sonT = 0, girenDolar = 0;
    tamam.forEach(function (k) {
      var ag = agAdi(k.chain), d = dolarDegeri(k, fiyat), ts = sayi(k.ts), to = String(k.to || "").toLowerCase();
      var g = gruplar[ag] || (gruplar[ag] = { ad: ag, deger: 0, sayi: 0, adres: {}, enBuyuk: null });
      g.sayi++;
      if (to) { g.adres[to] = 1; adresler[to] = 1; }
      if (d === null) fiyatsiz++; else { g.deger += d; toplam += d; }
      if (!g.enBuyuk || (d || 0) > (g.enBuyuk.d || 0)) g.enBuyuk = { d: d, amt: k.amt, ccy: k.ccy, ts: ts };
      ilk = Math.min(ilk, ts); sonT = Math.max(sonT, ts);
    });
    giren.forEach(function (k) { var d = dolarDegeri(k, fiyat); if (d !== null) girenDolar += d; });
    var bugun = new Date().toISOString().slice(0, 10), oturum = "tarayici-" + bugun;
    var liste = Object.keys(gruplar).map(function (ad) {
      var g = gruplar[ad], n = Object.keys(g.adres).length, eb = g.enBuyuk;
      return { id: ad.toLowerCase().replace(/[^a-z0-9]+/g, "-"), ad: ad, tutar: dolar(g.deger), deger: g.deger,
        cekim_sayisi: String(g.sayi), olgular: [],
        kapsam: { adres: n, benim_tahmini: 0, katmanlar: ["Çekim görüldü"], eksik: ["Zincir taraması"], yalniz_cekim: true },
        cumleler: [{ metin: g.sayi + " çekim, " + n + " adres. En büyük çekim " + miktarTr(eb.amt) + " " + eb.ccy + " (" + gunTr(eb.ts) + ").",
          model: "kod", denetim: "kod", olgular: [] }] };
    }).sort(function (a, b) { return b.deger - a.deger || +b.cekim_sayisi - +a.cekim_sayisi; });
    if (liste.length > 5) {
      var kalan = liste.slice(4);
      liste = liste.slice(0, 4).concat([{ id: "diger", ad: "Diğer", tutar: null, cekim_sayisi: null, olgular: [], kapsam: null, alt: kalan,
        deger: kalan.reduce(function (s, g) { return s + g.deger; }, 0), cumleler: [].concat.apply([], kalan.map(function (g) { return g.cumleler; })) }]);
    }
    var donem = tamam.length ? gunTr(ilk) + " – " + gunTr(sonT) : null;
    var ozet = tamam.length ? [{ metin: "OKX TR'den " + tamam.length + " çekimle yaklaşık " + dolar(toplam) + " çıktı" +
      (liste[0] ? "; en çok " + liste[0].ad + " ağına (" + liste[0].tutar + ")." : "."), model: "kod", denetim: "kod", olgular: [] }] : [];
    var kartlar = [
      { ton: "giris", ust: "Hesaba giriş", buyuk: dolar(girenDolar), alt: giren.length + " yatırma · yatırma günündeki fiyatla", sekme: "hareketler" },
      { ton: "cikis", ust: "Hesaptan çıkış", buyuk: dolar(toplam), alt: tamam.length + " çekim · çekim günündeki fiyatla", sekme: "hareketler" },
      { ton: "bilgi", ust: "Hızlı görünüm", metin: "Bot karşılaştırması, zincir taraması ve mühür bilgisayardaki proof1'da.", sekme: "kanitlar" }
    ];
    function rapor(gizli) {
      var r = { oturum: oturum, veri_turu: "tarayıcı", uretim: new Date().toISOString(), gizli: gizli, tarayici: true, ozet: ozet,
        akis: { donem: donem, birim: "USD", gruplar: liste,
          kaynak: { ad: "OKX TR", tutar: dolar(toplam), cekim_sayisi: String(tamam.length), adres_sayisi: String(Object.keys(adresler).length), olgular: [] },
          not: "Çekim günündeki fiyatla dolar karşılığı (günlük kapanış); bugünkü bakiye değil." +
            (fiyatsiz ? " " + fiyatsiz + " çekimin fiyatı bulunamadı; toplama girmedi." : "") },
        kopru: null, uyarilar: { liste: [], toplam: 0, acil: 0 }, sahiplik: [], kartlar: kartlar };
      if (!gizli && hesapDegeri !== null) {      // gizli modda bakiye hiç konmaz (yerel panoyla aynı kural)
        r.kopru = { gun: bugun, not: "", kapsamlar: { borsa: { ad: "Borsadaki hesap", ozet: [], kalemler: [
          { kalem: "bitis", ad: "Şimdi", varliklar: [], dolar: trSayi(hesapDegeri, 2) + " $", aciklama: "OKX TR hesap değeri (USDT karşılığı)", olgular: [] }] } } };
      }
      return r;
    }
    var satirlar = tamam.map(function (k) {
      var d = dolarDegeri(k, fiyat);
      return { zaman: new Date(sayi(k.ts)).toISOString(), tur: "cekim", karsi: null, miktar: "−" + miktarTr(k.amt) + " " + k.ccy,
        dolar: d === null ? null : "−" + trSayi(d, 2) + " $", ag: agAdi(k.chain), kaynak: "borsa", hesap: "OKX TR",
        kaynak_okuma: "OKX TR", islem: k.txId || null, supheli: false, durum: "ok" };
    }).concat(giren.map(function (k) {
      var d = dolarDegeri(k, fiyat);
      return { zaman: new Date(sayi(k.ts)).toISOString(), tur: "yatirma", karsi: null, miktar: miktarTr(k.amt) + " " + k.ccy,
        dolar: d === null ? null : trSayi(d, 2) + " $", ag: agAdi(k.chain), kaynak: "borsa", hesap: "OKX TR",
        kaynak_okuma: "OKX TR", islem: k.txId || null, supheli: false, durum: "ok" };
    })).sort(function (a, b) { return a.zaman < b.zaman ? 1 : -1; });
    var gruplarK = Object.keys(kayit).map(function (yol) {
      var k = kayit[yol], s = k.sure.length ? k.sure : [0];
      return { kaynak: k.kaynak, ad: k.ad, cagri: k.cagri, hata: k.hata, salt_okunur: true, alanlar: Object.keys(k.alanlar).sort(),
        ort_ms: Math.round(s.reduce(function (a, b) { return a + b; }, 0) / s.length), en_cok_ms: Math.round(Math.max.apply(null, s)) };
    });
    function ayrinti(gizli) {
      return { oturum: oturum, gizli: gizli, cumleler: ozet, uyarilar: [], bot: { olgu: null, iz: [], yok: true }, butce: null,
        hareketler: { pencere: donem, satirlar: satirlar.slice(0, 300), toplam: satirlar.length },
        kanit: { gruplar: gruplarK, hatalar: [], toplam: gruplarK.reduce(function (s, g) { return s + g.cagri; }, 0),
          salt_okunur_hepsi: true, denetim_kaydi: [], bildirim: { cagri: 0, hata: 0 } },
        muhur: muhur };
    }
    return { rapor1: rapor(true), rapor0: rapor(false), ayrinti1: ayrinti(true), ayrinti0: ayrinti(false) };
  }

  // ilerleme(sira, ek): 1 anahtar · 2 çekim/yatırma · 3 dolar karşılığı (ek: "12/40") · 4 çizim
  function tara(kimlik, ilerleme, ekler) {
    var c = istemci(kimlik.api_key, kimlik.secret_key, kimlik.passphrase), adim = ilerleme || function () {};
    kimlik = null;
    var veri = {};
    adim(1);
    return c.saatAyarla().then(function () { return c.get(UCLAR.ayar, null, true); }).then(function (ayar) {
      var yetkiler = String((ayar[0] || {}).perm || "").toLowerCase().split(",").map(function (s) { return s.trim(); });
      if (yetkiler.indexOf("trade") >= 0 || yetkiler.indexOf("withdraw") >= 0) throw new Error(YAZMA);
      if (!yetkiler.join("")) throw new Error("Anahtarın yetkisi okunamadı; yalnız Okuma yetkili bir anahtar dene.");
      adim(2);
      return sayfala(c, UCLAR.cekim);
    }).then(function (cekim) {
      veri.cekim = cekim;
      return sayfala(c, UCLAR.yatirma);
    }).then(function (yatirma) {
      veri.yatirma = yatirma;
      return c.get(UCLAR.deger, { ccy: "USDT" }, true).then(function (d) { return d[0] ? sayi(d[0].totalBal) : null; }, function () { return null; });
    }).then(function (deger) {
      veri.deger = deger;
      adim(3);
      var tamam = veri.cekim.concat(veri.yatirma).filter(function (k) { return String(k.state) === "2"; });
      return fiyatlar(c, tamam, function (i, n) { adim(3, i + "/" + n); });
    }).then(function (fiyat) {
      adim(4);
      return kur(veri.cekim, veri.yatirma, veri.deger, fiyat, c.kayit, (ekler && ekler.muhur) || null);
    });
  }

  // Test için: imzanın OKX belgesindeki biçimle aynı olduğunu tarayıcı dışında da karşılaştırabilmek
  function imzala(gizliAnahtar, metin) {
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(gizliAnahtar), { name: "HMAC", hash: "SHA-256" }, false, ["sign"])
      .then(function (k) { return crypto.subtle.sign("HMAC", k, enc.encode(metin)); }).then(b64);
  }

  window.Proof1Tarayici = { tara: tara, imzala: imzala, agAdi: agAdi };
})();
