# proof1 · demo akışı (Merve'nin parçaları)

Sunum Buğra'nın bilgisayarından. Bu dosya teknik adım listesidir; konuşma metni insanlarda.

## Sunumdan önce (bir kez)

1. `git pull origin main`, sonra `python -m pip install -r anlatim/requirements.txt -r muhur/requirements.txt`.
2. `.env`: `ANLATICI_KOMUT`, `ANTHROPIC_API_KEY`, `PROOF1_AGENT_ID=263`,
   `PROOF1_SEAL_ADDRESS=0x7C5aB869e8d972885673f19B848084279AAD0d48`, `FUJI_RPC_URL` (publicnode),
   `PROOF1_ARASTIR=canli` (bot kimliği olguda yoksa `kayit`). Mühür buradan atılacaksa `PROOF1_FUJI_PRIVATE_KEY`.
3. Testler yeşil: `python -m unittest discover -s anlatim/testler -t .` (pano ve muhur için de).
4. Sabah işi: `python -m calistir.sabah` → Telegram mesajı. Elle tetiklendiyse mesajda gerçek çalışma saati görünür;
   zamanlanmış çalışmış gibi sunulmaz.
5. Kalıba düştüyse nedeni: `data/anlatici_gunluk.jsonl` son satırları.
6. Günün mührü (gerçek defterle, **gün başına tek hak**): önce `python -m muhur.muhurle --gun 2026-10-17`
   (kuru), sonra `--gonder`. Çıkan işlem bağlantısını açık tut.
7. Pano: `python -m pano.sunucu` (telefon gösterilecekse `--host 0.0.0.0`, aynı Wi-Fi'de bilgisayarın yerel IP'si).
8. Canlı an için ayrı bir terminalde izleyici açık kalsın: `python -m calistir.izle` (bot durunca saniyeler içinde Telegram).
   Demo botunu insan kurar (OKX uygulaması ya da kendi terminali); proof1 bot kurmaz, durdurmaz, bu komutlar depoda yoktur.
9. İnternet: hareket kütüphanesi (GSAP) ve yazı tipleri CDN'den gelir; bağlantı yoksa pano hareketsiz ama eksiksiz çizilir.

## Sahnede (devirdeki 7. bölümle aynı sıra)

| # | Ne gösterilir | Nereden |
|---|---|---|
| 1 | Telegram'daki otomatik mesaj, "Panoyu aç" | Telegram Desktop → bağlantı localhost'ta açılır |
| 2 | Sade sayfa: akış şeması (altın taneler paranın yönü), kırmızı “Bot kaydı tutmuyor” işareti, en çok 3 kart; gizli mod açık | Sade |
| 3 | Ethereum bandının üstüne gel (diğerleri söner), tıkla → MOCA cümlesi ve dönem notu | Bant çekmecesi |
| 4 | Canlı an: Buğra botu durdurur → Telegram uyarısı; panoyu yenileyince acil kart | Telegram, Sade |
| 5 | Yetki ve sınırlar: alt çubukta “Salt okunur”; çağrıların hepsi salt okunur; bütçe 35 TL tavan | Detay → Kanıt ve mühür |
| 6 | ERC-8004 NFT (agentId 263) ve son mühür; "Zincirde doğrula" | Detay → Kanıt ve mühür; gezgin bağlantıları |
| 6b | Araştırma izi: hedef → araç → gözlem → karar → sonuç, başarısız adım dahil; OKX kanıt tablosu | Detay → Bot, Kanıt ve mühür |
| 7 | Hata davranışı: "tanıyamadım" cümlesi, kalıp cümle etiketi, okunamayan katman | Bant çekmecesi, Detay → Hareketler |
| 8 | Herkes kendi hesabını görür: hesap menüsü → “Kendi hesabını bağla” (yalnız Okuma yetkili anahtar; sahnede anahtar girilmez) | Sağ üst menü |

## Yedek ekran kaydı (canlı an aksarsa)

1. Prova sırasında yukarıdaki akışı ekran kaydına al; pano adresine `&kayit=1` ekle
   (ör. `http://localhost:3003/?oturum=sabah-2026-10-17&kayit=1`). Ekranın üstünde kalıcı **KAYIT** şeridi görünür.
2. Kayıtta gizli mod açık kalsın; adresler zaten kısaltılmış. Telegram penceresinde gerçek adres ya da bakiye
   görünmediğini kontrol et.
3. Kayıt dosyası depoya girmez (`.gitignore`: `*.mp4`, `*.mov`).
4. Kayıt sahnede kullanılırsa "kayıt" olduğu söylenir; şerit zaten ekranda.

## Bilinen sınırlar

- Kayıtlı yanıtlarla (`anlatim/kayit/bot_16_ekim.json`) üretilen iz "kayıt" etiketlidir; canlı değildir.
- `grid_get_sub_orders` için kayıtlı yanıt yok; kayıt kipinde bu adım "başarısız" görünür ve iz sonraki okumayla
  devam eder. Bu, uydurulmuş bir hata değil, kayıt kipinin gerçek davranışıdır.
