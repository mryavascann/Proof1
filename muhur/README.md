# muhur/ · proof1'ın ERC-8004 kimliği ve günlük mühür (Avalanche Fuji)

Sahibi: Merve. Foundry projesi.

## Kurulum

```bash
cd muhur
git clone --depth 1 --branch v1.17.0 https://github.com/foundry-rs/forge-std lib/forge-std
```

(`forge install` bu klasörde depo kökünü bulup `lib/`'i köke kurduğu için doğrudan klonluyoruz.)

`.env` depo kökündedir ve depoya girmez. Gerekenler: `PROOF1_FUJI_PRIVATE_KEY`, `PROOF1_FUJI_ADDRESS`, `FUJI_RPC_URL`, kayıttan sonra `PROOF1_AGENT_ID`.

## Testler

```bash
cd muhur
set -a; . ../.env; set +a
forge test
```

Testler Fuji'yi çatallar; kayıt yerelde denenir, gaz harcanmaz. `PROOF1_AGENT_ID` doluysa `test_GercekKayit` zincirdeki gerçek kaydı okur.

## Kayıt (M1)

- Resmi Identity: `0x8004A818BFB912233c491871b3d84c89A494BD9e` (Fuji, `getVersion()` = `2.0.0`, kaynak: github.com/erc-8004/erc-8004-contracts).
- Kayıt dosyası `kayit/kayit.json`, görsel `kayit/gorsel.svg`; ikisi de zincire `data:` URI olarak gömülür.
- `kayit/gorsel.svg` geçici görseldir; asıl görsel gelince `setAgentURI` ile güncellenir.

```bash
cd muhur
set -a; . ../.env; set +a
forge script script/Kaydol.s.sol --rpc-url fuji --broadcast
```

`FUJI_RPC_URL` için `https://avalanche-fuji-c-chain-rpc.publicnode.com` kullanıyoruz: resmi `api.avax-test.network` etkinlik ağında hız sınırına (Cloudflare 1015) takıldı. Bu RPC bekleyen blokta durum vermediği için `forge script --broadcast` gaz tahmininde düşebiliyor. 17 Ekim kaydı şu yolla yapıldı (önce `eth_call` ile önizleme):

```bash
URI=$(forge script script/Kaydol.s.sol --sig 'agentURI()' --json | …)   # betiğin ürettiği data: URI
cast send 0x8004A818BFB912233c491871b3d84c89A494BD9e 'register(string)' "$URI" \
  --private-key "$PROOF1_FUJI_PRIVATE_KEY" --rpc-url "$FUJI_RPC_URL" --gas-limit 2000000
```

Sonuç: agentId **263**, sahibi proof1 test cüzdanı. Ayrıntı: `sunum/README-katki.md`.
