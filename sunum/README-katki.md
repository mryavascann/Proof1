# proof1 · Merve'nin parçaları — README katkısı

Kök README'ye insan aktarır. Klasörler: `anlatim/` (anlatıcı, sayı denetimi, araştırma izi), `pano/` (pano),
`muhur/` (ERC-8004 kimliği ve günlük mühür), `sunum/` (bu dosya, demo akışı).

## Kurulum

```bash
python -m pip install -r anlatim/requirements.txt -r muhur/requirements.txt
```

`.env` (depoya girmez; değerleri insan yazar):

| Değişken | Ne için | Not |
|---|---|---|
| `ANLATICI_KOMUT` | Sabah işi anlatıcıyı çağırır | `python -m anlatim.anlat --oturum {oturum}` |
| `ANTHROPIC_API_KEY` | Anlatıcı modeli | Yoksa her cümle doğrulanmış kalıp olur |
| `PROOF1_KULLANICI`, `PROOF1_USD_TRY` | Bütçe (ayda 35 TL tavan) ve TL kuru | Öntanımlı `bugra`, `49.367` |
| `PROOF1_ARASTIR` | Bot uyuşmazlığında araştırma izi | `canli` (ATK --read-only), `kayit` (kayıtlı gerçek yanıtlar) ya da boş |
| `PROOF1_AGENT_ID`, `PROOF1_SEAL_ADDRESS` | Mühür ve pano kanıt paneli | `263`, `0x7C5aB869e8d972885673f19B848084279AAD0d48` |
| `FUJI_RPC_URL` | Avalanche Fuji | `https://avalanche-fuji-c-chain-rpc.publicnode.com` (resmi uç etkinlik ağında hız sınırına takıldı) |
| `PROOF1_FUJI_PRIVATE_KEY` | Yalnız mühür yazarken | proof1'ın kendi test cüzdanı; yalnız Fuji |
| `PROOF1_TUZ` | Mühür tuzları | Öntanımlı `data/muhur_tuzlari.json`; silinirse eski kökler yeniden üretilemez |

## Çalıştırma

```bash
python -m anlatim.anlat --oturum sabah-2026-10-17          # cümleler (sabah işi bunu kendisi çağırır)
python -m anlatim.arastir --oturum sabah-2026-10-17 --canli # araştırma izi (ya da --kayit anlatim/kayit/bot_16_ekim.json)
python -m pano.sunucu                                      # pano: http://localhost:3003 (--host 0.0.0.0: aynı Wi-Fi'deki telefon)
python -m muhur.muhurle --gun 2026-10-17                    # mühür kökünü yalnız hesaplar
python -m muhur.muhurle --gun 2026-10-17 --gonder           # Fuji'ye yazar
```

Panoda `?kayit=1` ekranda kalıcı **KAYIT** şeridi gösterir (yedek ekran kaydı için).

## Anlatıcı ve sayı denetimi

- Model sayı üretmez. Kod modele numaralı olgular verir; model her cümlede dayandığı olguları söyler.
- `anlatim/denetim.py` cümledeki her sayıyı, atıf yapılan yetkili olgularda **aynı değer, birim ve işaretle** arar; tarih ve saat bütün olarak, "verip/aldın" rolleri doğru alana bağlanır. Gizli değer, başka görevin olgusu ya da kendi hesapladığı yüzde reddedilir; o zaman olgu alanlarını harfiyen kopyalayan kalıp cümle yazılır. Reddedilen ham cümle saklanmaz.
- Telegram cümlesi önce ve tek olguyla istenir (bot uyuşmazlığı varsa yalnız o), 3 sn zaman aşımı; pano ve bant cümleleri sonra.
- Model: `claude-sonnet-5-5`; harcama tavanın %80'ine gelince `claude-haiku-5-5`; 35 TL tavanda kalıp. Her çağrı `butce` tablosuna.
- Kalıba düşme nedeni `data/anlatici_gunluk.jsonl` dosyasına yazılır (ham cümle yazılmaz).

## Araştırma izi (Agentic Design)

Bot kaydı tutmadığında proof1 yalnız `grid_get_order_details`, `grid_get_sub_orders`, `account_get_bills` ile kendisi araştırır; başka araç ATK'ya hiç iletilmez. Her adım `iz` tablosuna: hedef → kısa gerekçe → araç → gözlem → karar → sonuç, başarısız çağrı ve sonrası dahil. Gözlem sayıları koddan gelir; modelin kararını kod olgularla doğrular. Kayıtlı yanıtla üretilen iz panoda "kayıt" etiketiyle görünür.

## Pano

- **Genel Bakış:** tek akış şeması (OKX TR → Sen → ağlar), yanında doğrulanmış özet cümle; giren bant yeşil, çıkışlar kırmızı. Bir banda dokununca o paranın cümleleri, ağın okunabilen katmanları ve dönem notu açılır. Dünden bugüne köprüsü (ayrı dönem), en çok 3 uyarı, "Bu adres senin mi?".
- **Ayrıntılar:** defter satırları ve doğrulanmış cümleler; bot incelemesi (araştırma izi); kanıtlar (OKX TR / ATK / OnchainOS / zincir çağrıları, süre, alanlar, hata, salt okunur; Fuji mühür paneli ve "Zincirde doğrula"; model bütçesi).
- **Gizli mod** öntanımlı açık: bakiye seviyeleri ve yüzdeler rapora hiç girmez; giren, çıkan ve aktarım tutarları görünür.
- Pano Buğra'nın tablolarını salt okur; yalnız `isaret` tablosuna ("benim / benim değil") yazar. Tam adres yalnız gezgin bağlantısının hedefinde.

## Avalanche Fuji · ERC-8004 kimliği

| | |
|---|---|
| Ağ | Avalanche Fuji C-Chain (chainId 43113) |
| Identity Registry (resmi, v2.0.0) | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| proof1 agentId | **263** |
| proof1 test cüzdanı (NFT sahibi) | `0x09a292458F780a28622062DaC6560Fa6b87B3ed6` |
| Kayıt işlemi | [`0x9809…c81e`](https://testnet.snowtrace.io/tx/0x980921762cbd2b01335347c5fc1b52d8d8b7e06b1897d41e41e9987d4bbdc81e) (blok 59594785) |
| NFT | [testnet.snowtrace.io/nft/0x8004…BD9e/263](https://testnet.snowtrace.io/nft/0x8004A818BFB912233c491871b3d84c89A494BD9e/263) |

Kayıt dosyası (`muhur/kayit/kayit.json`) ve görsel zincire `data:` URI olarak gömülü; `tokenURI(263)` dosyanın kendisini döndürür. Görsel geçicidir; asıl görsel gelince `setAgentURI` ile güncellenecek.

## Günlük mühür

| | |
|---|---|
| Mühür sözleşmesi `Proof1Muhur` | [`0x7C5aB869e8d972885673f19B848084279AAD0d48`](https://testnet.snowtrace.io/address/0x7C5aB869e8d972885673f19B848084279AAD0d48) |
| Deploy işlemi | [`0x6382…9a09`](https://testnet.snowtrace.io/tx/0x6382f45f82190887171fdfd230f49ea2088d63e857df4a59c2964ee995bb9a09) |
| Kimliğe bağlama | `setMetadata(263, "proof1.seal", …)` [`0x2ef7…999f`](https://testnet.snowtrace.io/tx/0x2ef71ece22162c054f4ea64fca9eff9a71b4d793a9214d63ac1d69f672d2999f) · kayıt dosyasında `services` ve `registrations` [`0xbd28…fb12`](https://testnet.snowtrace.io/tx/0xbd2841c8e77716bb650f0937300988c3253556e8e667a90d4851d029974cfb12) |
| İlk mühür (**örnek veri**, 11 Ekim 2026, o günkü örnek defterin 13 satırı) | kök `0xd68d…a74c` · [`0x0613…6ea1`](https://testnet.snowtrace.io/tx/0x0613b3a427fbf1dce91c79a2cc994b17f760eeb30951f72ee437827895b76ea1) · zincirde `rootOf` ile doğrulandı |

Sözleşme: yalnız ERC-8004 kimliğin sahibi yazar; her gün bir kez, üzerine yazılamaz, geriye tarih yok. Zincire yalnız kök gider; adres ya da tutar gitmez. Mühür, defterin o gün var olduğunu ve sonradan değişmediğini kanıtlar; içeriğin doğruluğunu kanıtlamaz.

Kök: günün her hareket satırı için yaprak = sha256(tuz ‖ kanonik satır); tuzlar yalnız yerelde. Yapraklardan Merkle kökü, sonra sha256(merkle ‖ önceki mühür kökü). Bir satır, diğerleri açılmadan kanıtlanabilir. Kurallar: `muhur/kok.py` başındaki not.

## Örnek, kayıt ve canlı veri

| | Nerede görünür |
|---|---|
| Örnek veri (`ortak/ornek/proof1_ornek.db`) | Pano üstünde "Örnek veri" |
| Kayıtlı yanıt (`anlatim/kayit/bot_16_ekim.json`) | Araştırma izinde "[kayıt]" ve "kayıt" rozeti |
| Yedek ekran kaydı | Panoda `?kayit=1` ile kalıcı "KAYIT" şeridi |
| Canlı veri (`data/proof1.db`, depoya girmez) | Pano üstünde "Canlı veri" |

## Testler

```bash
python -m unittest discover -s anlatim/testler -t .
python -m unittest discover -s pano/testler -t .
python -m unittest discover -s muhur/testler -t .
cd muhur && forge test      # Foundry; .env yüklüyken Fuji çatalı ve zincirdeki gerçek kayıt
```
