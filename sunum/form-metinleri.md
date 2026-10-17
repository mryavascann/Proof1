# Başvuru formu metinleri

## Avalanche'ta deploy ettiğiniz akıllı kontrat adresi

```
0x7C5aB869e8d972885673f19B848084279AAD0d48
```

Proof1Muhur, Avalanche Fuji test ağı (chainId 43113). Gezgin: https://testnet.snowtrace.io/address/0x7C5aB869e8d972885673f19B848084279AAD0d48

Sözleşme 17 Ekim 13:48'de dağıtıldı. ERC-8004 kaydı (agentId 263) 13:46'da, ilk deneme mührü 13:53'te gönderildi; hepsi bugün. Deneme mührünün içindeki "11 Ekim", mühürlenen örnek defterin gün etiketidir, işlemin tarihi değildir. 16 Ekim'in gerçek defteri de bugün mühürlendi ve zincirde doğrulandı: https://testnet.snowtrace.io/tx/0x5135feef5860b1689908ab2f56def30363fb22ca424ca8f0b109177e91b2ef34

## Proje açıklaması

proof1, OKX TR kullanıcısının parasını kendisi izleyen ve yalnız okuyan bir yapay zekâ ajanıdır. Borsadan çıkan her çekimi zincirde takip eder. Adresleri kullanıcıya sormadan çekim kaydından bulur, paranın hangi ağa gittiğini tek bir hareketli akış şemasında gösterir; işi bilmeyen biri üç saniyede anlar. Her sabah Telegram'a Türkçe özet yazar, bir bot durdurulduğunda saniyeler içinde uyarır. Gerçek örnek: borsanın bot kaydı +99,89 TL kâr diyordu, hesaba dönen paraya göre sonuç −0,22 TL zarardı. proof1 bu farkı yakaladı ve nedenini kendisi araştırdı.

Borsa tarafını OKX Agent Trade Kit ile (salt okuma kipinde), zincir tarafını OKX OnchainOS ile okur. Cümleleri Claude Sonnet 5.5 yazar; her sayıyı kod olgularla karşılaştırır, tutmayan cümle gösterilmez. proof1 emir vermez, bot kurmaz, para taşımaz; işlem ya da çekim yetkisi olan anahtarı reddeder. Her günün defter kökü Avalanche Fuji'deki mühür sözleşmesine yazılır (ERC-8004 agentId 263). Böylece borsanın kaydı sonradan değişse bile "dün ne yazıyordu" tartışmasız kalır. Herkes kendi hesabını yalnız Okuma yetkili anahtarla, kendi bilgisayarında bağlar; anahtar cihazdan çıkmaz.

Canlı demo: https://proof1-ivory.vercel.app · Kod: https://github.com/mryavascann/Proof1

## Kısa açıklama (tek cümle gerekirse)

proof1, OKX TR'deki paranın nereye gittiğini zincirde kendisi izleyen, bot kayıtlarındaki hatayı yakalayan ve günün defterini Avalanche'a mühürleyen, yalnız okuyan bir yapay zekâ ajanıdır.
