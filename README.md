# proof1

**Paran nerede, nereden nereye gitti?** proof1 kendisi bulur; üç saniyede anlaşılan tek resimde gösterir.

Agentic Hackathon Ankara · 17 Ekim 2026 · Buğra & Merve

proof1, birkaç yere dağılmış parasını bot da kullanarak yöneten OKX TR kullanıcısı içindir. Adresleri borsanın çekim kaydından kendisi bulur (kullanıcı adres yazmaz, cüzdan bağlamaz), zincirde paranın neye dönüştüğünü cümleyle anlatır, her sabah 09:00'da Telegram'a yazar ve bot kaydı ile hesaba dönen para uyuşmadığında hemen uyarır.

## Salt okuma (mimari kural)

**proof1 yalnız okur.** Emir vermez, bot kurmaz ya da durdurmaz, para çekmez ya da taşımaz, öğüt vermez. Bu bir talimat değil, mimari:

| Kaynak | Nasıl bağlanır | Neden yazamaz |
|---|---|---|
| OKX Agent Trade Kit (ATK) | yerel MCP: `okx-trade-mcp --site tr --read-only --modules market,account,spot,bot.grid` | sunucu salt okuma kipinde 43 araç açar, hiçbiri emir vermez; istemci (`veri/atk.py`) listede yazma aracı görürse bağlantıyı reddeder |
| OKX TR imzalı uçlar | `veri/okx_imzali.py`, OKX v5 HMAC | yalnız `GET`, yalnız izinli uç listesi (çekim, yatırma, fonlama kaydı, bakiye); listede olmayan uç çağrılamaz |
| OnchainOS | `veri/zincir/onchainos.py` | yalnız `GET`, izinli uç listesi; ücretsiz kota dolarsa durur (x402 ödemesi kurulmaz) |
| Zincir gezginleri | Routescan, Etherscan V2, TronGrid, açık RPC | okuma API'leri; özel anahtar yok |
| Telegram | proof1'ın kendi botu → kullanıcının sohbeti | yalnız mesaj gönderir; token hiçbir kayda yazılmaz |

Her dış çağrı `cagri` tablosuna yazılır (kaynak, araç/uç, süre ms, kullanılan alanlar, sonuç, `salt_okunur`); parametreler maskelenir. Bu kayıt panodaki **OKX kanıt paneli**dir (`python -m veri.kanit`).

## Klasörler

| Klasör | Sahibi | İçerik |
|---|---|---|
| `veri/` | Buğra | borsa okuyucu (ATK + OKX TR), zincir okuyucu ve çözücü, defter, adres/sahiplik, bot karşılaştırıcı, köprü, olgular |
| `calistir/` | Buğra | sabah işi, Telegram, canlı bot izleyicisi |
| `anlatim/` | Merve | anlatıcı ajan, sayı denetimi |
| `pano/` | Merve | pano (tek görsel, basit/ayrıntılı, “benim” işareti) |
| `muhur/` | Merve | ERC-8004 kaydı ve günlük mühür (Avalanche Fuji) |
| `ortak/` | ikisi | `SOZLESME.md` (tek bağ), `ornek/proof1_ornek.db` |

## Kurulum

```bash
python -m pip install -r veri/requirements.txt      # Python 3.13; yalnız `requests`
npm install -g @okx_ai/okx-trade-mcp                # ATK 1.4.8 (okx, okx-trade-mcp)
cp .env.ornek .env                                   # değerleri insan doldurur; depoya girmez
```

OKX anahtarları `.env`'de yoksa ATK profil klasörleri kullanılır (`OKX_TR_ANA_PROFIL`, `OKX_TR_ALT_PROFIL`; öntanımlı `~/okx-ana`, `~/okx-atk`). İçerikleri hiçbir yere basılmaz. İki hesap da **yalnız okuma** anahtarıyla okunur: çekim/yatırma kaydı ana hesapta, botlar alt hesapta.

Telegram: BotFather'da bot aç → token'ı `.env`'e yaz → Telegram'dan bota `/start` → `python -m calistir.telegram_kimlik` (sohbet kimliğini `.env`'e yazar).

## Çalıştırma

```bash
python -m calistir.sabah                 # sabah işi: defter → adres → zincir → fotoğraf → köprü → bot → olgu → anlatıcı → Telegram
python -m calistir.sabah --gonderme      # aynısı, mesajı yalnız ekrana yazar
python -m calistir.sabah --taze          # zincir önbelleğini (15 dk) atlayıp her şeyi yeniden okur
python -m calistir.izle --algo <algoId>  # canlı bot izleyicisi: bot durdurulunca saniyeler içinde Telegram
python -m veri.kanit sabah-2026-10-17    # OKX kanıt paneli özeti
python -m veri.ornek                     # Merve için örnek veritabanını yeniden üret
python -m unittest discover -s veri/testler -t .          # çevrimdışı testler
CANLI=1 python -m unittest discover -s veri/testler -t .  # + gerçek hesapla kabul testleri
```

Sabah işi `ANLATICI_KOMUT` doluysa Merve'nin anlatıcısını çalıştırır (`{oturum}` yer tutucusu), 5 saniye bekler, `cumle` tablosundan denetimden geçmiş cümleyi alır; yoksa kalıp cümle gider. Gizli bir değer cümleye sızarsa yine kalıp cümle gider.

## Örnek veri ve canlı veri

| | Örnek veri | Canlı veri |
|---|---|---|
| Dosya | `ortak/ornek/proof1_ornek.db` (depoda) | `data/proof1.db` (`PROOF1_DB`, depoya girmez) |
| Adresler | yer tutucu: `BENIM_1`, `ADRES_7`, `KARSI_1` | tam adres yalnız yerel veritabanında; panoda kısaltılır (`0xABCD…1234`) |
| İşlem kimlikleri | `TX_…` | gerçek (yalnız yerel) |
| Bakiye seviyesi | yok | `fotograf` tablosunda; gizli modda gösterilmez |
| Kaynak | gerçek borsa satırlarının kesiti + devir metninde doğrulanmış zincir olayları | sabah işinin o günkü okuması |

Ekranda gösterilen bir kayıt (önceden alınmış görüntü/çıktı) her zaman **“kayıt”** etiketiyle gösterilir.

## OKX araçları

**ATK (salt okuma MCP):** `account_get_bills`, `account_get_bills_archive` (defter, 7 gün / 3 ay), `account_get_balance`, `account_get_asset_balance`, `account_get_balance_all` (sabah fotoğrafı), `grid_get_orders` (etkin/geçmiş), `grid_get_order_details`, `grid_get_sub_orders`, `spot_get_fills`, `spot_get_orders`, `market_get_ticker`, `market_get_candles` (o anın dolar ve TL fiyatı), `market_get_instruments`, `trade_get_history` (ATK'nın kendi denetim kaydı).

**OKX TR imzalı uçlar (ATK'da yok):** `GET /api/v5/asset/withdrawal-history` (alıcı adres, `txId`, ağ, tutar, ücret), `GET /api/v5/asset/deposit-history`, `GET /api/v5/asset/bills`, `GET /api/v5/asset/balances`, `GET /api/v5/account/balance`. İstekler saniyede ~2,5 ile sınırlı (tr.okx.com yoğun okumada bağlantıyı kesiyor).

**OnchainOS:** `GET /api/v6/dex/post-transaction/transactions-by-address`, `GET /api/v6/dex/balance/all-token-balances-by-address`, `GET /api/v6/dex/balance/supported/chain`.

**Diğer zincir kaynakları:** Routescan (Ethereum, Avalanche, Chiliz; anahtarsız), Etherscan V2 (Ethereum, Arbitrum, Polygon; ücretsiz anahtar), TronGrid, açık RPC'ler (işlem göndereni). Okunamayan ağ sessizce kaybolmaz: “bu ağda yalnız çekimi görüyorum” olarak görünür, köprüde “izlenemeyen” satırına düşer.

## Nasıl hesaplıyor

- **Adresler:** çekim kaydının alıcıları (büyük/küçük harf birleştirilir). Bir adres hem çekim almış hem de borsaya yatırma yapmışsa (gönderen, yatırmanın `txId`'sinden zincirde bulunur) “büyük olasılıkla senin” — kanıtıyla. Kesin karar kullanıcının.
- **Zincir çözücü:** her işlemde kullanıcının adresine giren ve çıkan + ağ ücreti → “verdi / aldı / ücret”. Tanınmayan giriş “tanıyamadım” olur; sahte token (görünmez karakter, alan adı isimli, resmi olmayan sözleşmeli USDC/USDT) ve adres zehirleme (ilk ve son 4 karakteri tanıdık adrese benzeyen gönderen) işaretlenir. EVM adresleri okunabilen her ağda okunur.
- **Defter:** “önceki bakiye + değişim = yeni bakiye” her para biriminde denetlenir (ana ve alt hesabın işlem defteri, ana hesabın fonlama defteri); bot aktarımlarında hesap ve botun iç defteri ayrı zincirdir. TL banka yatırması/çekimi fonlama defterinden gelir; Lira Boost kazancı “dışarıdan gelen”, vergisi “ücret”tir.
- **Zincir kapanışı:** her okunan adres-ağ için defterdeki yerel coin, zincirdeki bakiyeyle karşılaştırılır; kapanmayan kısım olgu olarak “bu kadarını açıklayamadım” diye gösterilir.
- **Bot karşılaştırıcı:** gerçek sonuç = hesaba dönen TL + dönen coin × fiyat − yatırım (fiyat: durdurma dakikasının en düşük/en yüksek aralığı); borsanın kaydı (`totalPnl`) ile farkı 1 TL'yi geçerse acil uyarı.
- **Dünle karşılaştırma (köprü):** dün 09:00 → bugün 09:00, `borsa` ve `servet` kapsamı; dünkü toplam + kalemler = bugünkü toplam, kapanmayan kısım “açıklayamadığım”.
- **Olgular:** sayıları kod hesaplar ve Türkçe biçimde metne çevirir (`0,9828 AVAX`, `1.587 MOCA`); model sayı üretmez, her cümle olgu numarasına dayanır.

## Avalanche

proof1, Avalanche Fuji'de resmi ERC-8004 Identity sözleşmesine kayıtlı bir ajandır; her günün defterinin kökü kimliğe bağlı mühür sözleşmesine yazılır (`muhur/`, Merve).

| | Adres | Gezgin |
|---|---|---|
| ERC-8004 Identity (Fuji) | `0x8004A818BFB912233c491871b3d84c89A494BD9e` | https://testnet.snowtrace.io/address/0x8004A818BFB912233c491871b3d84c89A494BD9e |
| ERC-8004 Reputation (Fuji) | `0x8004B663056A597Dffe9eCcC1965A193B7388713` | https://testnet.snowtrace.io/address/0x8004B663056A597Dffe9eCcC1965A193B7388713 |
| proof1 agentId ve mühür sözleşmesi | `muhur/` dağıtımından sonra eklenecek | — |

Mühür, defterin o gün var olduğunu ve sonradan değişmediğini kanıtlar; doğru olduğunu kanıtlamaz. Zincire adres ya da tutar yazılmaz, yalnız kök.

## Güvenlik ve gizlilik

- Anahtarlar yalnız `.env`'de; kodda, kayıtta, ekran çıktısında ve hata mesajında yok.
- Adresler ve güncel bakiye depoya, ekran görüntüsüne ve sunuma girmez; örnek veride yer tutucu kullanılır.
- Tüm tutarlar `Decimal`; kayan nokta yok. Dış API cevabı doğrulanır, bozuk satır “okunamadı” olur, uygulama çökmez.
- Fiyatı olmayan şeye dolar uydurulmaz (“bilinmiyor”); tanınmayan işlem tahminle doldurulmaz.
