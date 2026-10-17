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

Kayıt dosyası (`muhur/kayit/kayit.json`) ve görsel zincire `data:` URI olarak gömülü; `tokenURI(263)` dosyanın kendisini döndürür. Görsel geçicidir; asıl görsel gelince `setAgentURI` ile güncellenecek. Mühür sözleşmesi adresi M2'de eklenecek.

Doğrulama: `cd muhur && set -a; . ../.env; set +a; forge test` (5 test; `test_GercekKayit` zincirdeki kaydı okur).
