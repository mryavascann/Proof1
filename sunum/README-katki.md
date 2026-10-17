# proof1 · Merve'nin parçaları — README katkısı

Kök README'ye insan aktarır.

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
| İlk mühür (**örnek veri**, 11 Ekim 2026, 13 satır) | kök `0xd68d…a74c` · [`0x0613…6ea1`](https://testnet.snowtrace.io/tx/0x0613b3a427fbf1dce91c79a2cc994b17f760eeb30951f72ee437827895b76ea1) |

Sözleşme: yalnız ERC-8004 kimliğin sahibi yazar; her gün bir kez, üzerine yazılamaz, geriye tarih yok. Zincire yalnız kök gider; adres ya da tutar gitmez. Mühür, defterin o gün var olduğunu ve sonradan değişmediğini kanıtlar; içeriğin doğruluğunu kanıtlamaz.

Kök: günün her hareket satırı için yaprak = sha256(tuz ‖ kanonik satır); tuzlar yalnız yerelde. Yapraklardan Merkle kökü, sonra sha256(merkle ‖ önceki mühür kökü). Bir satır, diğerleri açılmadan kanıtlanabilir. Kurallar: `muhur/kok.py` başındaki not.

Doğrulama:
- `cd muhur && set -a; . ../.env; set +a; forge test` → 17 test (yerel, Fuji çatalı, zincirdeki gerçek kayıt ve mühür sözleşmesi)
- `python -m unittest discover -s muhur/testler -t .` → 17 test (kök, tuz, Merkle kanıtı, mühürleme akışı)
