# proof1

**Paran nerede, nereden nereye gitti?** proof1 kendisi bulur; üç saniyede anlaşılan tek resimde gösterir.

Agentic Hackathon Ankara · 17 Ekim 2026 · Buğra & Merve

> **proof1 yalnız okur.** Emir vermez, bot kurmaz/durdurmaz, para çekmez/taşımaz, öğüt vermez. OKX araç seti (ATK) `--read-only` kipinde bağlanır; OKX TR uçları yalnız `GET` ile, izinli uç listesinden çağrılır.

## Klasörler

| Klasör | Sahibi | İçerik |
|---|---|---|
| `veri/` | Buğra | borsa okuyucu (ATK + OKX TR), zincir okuyucu, defter, bot karşılaştırıcı, köprü, olgular |
| `calistir/` | Buğra | sabah işi, Telegram, canlı bot izleyicisi |
| `anlatim/` | Merve | anlatıcı ajan, sayı denetimi |
| `pano/` | Merve | pano (tek görsel, basit/ayrıntılı) |
| `muhur/` | Merve | ERC-8004 kaydı ve günlük mühür (Avalanche Fuji) |
| `ortak/` | ikisi | `SOZLESME.md` (tek bağ), `ornek/proof1_ornek.db` |

## Kurulum (veri tarafı)

```bash
python -m pip install -r veri/requirements.txt
cp .env.ornek .env   # değerleri insan doldurur
python -m unittest discover -s veri/testler -t .
```

_Taslak — çalıştırma adımları, OKX araç listesi, örnek/canlı veri ayrımı ve kontrat adresleri B10'da eklenecek._
