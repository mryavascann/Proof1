# proof1 · Sözleşme (v0 · 17 Ekim 2026)

Buğra (veri) ile Merve (anlatım ve yüz) arasındaki **tek** bağ. Bu dosyayı ajanlar değiştirmez; değişiklik gerekiyorsa insanlar konuşur.

## Genel

- **Veri dosyası:** tek SQLite dosyası, yolu `PROOF1_DB` (öntanımlı `data/proof1.db`, depoya girmez). Örnek: `ortak/ornek/proof1_ornek.db` (adresler `BENIM_1`… yer tutucu, güncel bakiye yok).
- **Her tabloyu tek taraf yazar** (aşağıda “Yazan”). Öbür taraf yalnız okur. Tabloyu yazan taraf oluşturur (`CREATE TABLE IF NOT EXISTS`).
- **Zaman:** `TEXT`, ISO-8601 UTC, ör. `2026-10-11T12:32:05.123Z`. Gösterimde Europe/Istanbul'a çevrilir.
- **Gün:** `TEXT`, `YYYY-MM-DD`, Europe/Istanbul günü (sabah 09:00 fotoğrafının günü).
- **Tutar:** `TEXT`, nokta ondalıklı, işaretli ondalık sayı (ör. `-0.1`, `0.98280221`). Kayan nokta yok; okurken `Decimal`. Bilinmeyen dolar değeri `NULL` (uydurulmaz).
- **JSON alanları:** `TEXT`, UTF-8 JSON.
- **Oturum:** `TEXT`, bir çalıştırmanın kimliği, ör. `sabah-2026-10-17`, `canli-<algoId>`. `cagri`, `olgu`, `uyari`, `cumle`, `iz` satırları oturuma bağlanır.
- **Gizlilik:** tam adres yalnız `adres.adres` alanında (yalnız yerel veritabanında). Diğer her yerde `adres.etiket` (`BENIM_1`, `ADRES_7`…) ya da `adres.kisa` (`0xABCD…1234`) kullanılır.

## Tablolar

### `hareket` · yazan Buğra
Borsa ve zincirdeki her para hareketi, tek satır = tek varlığın tek yönlü değişimi.

| alan | tip | açıklama |
|---|---|---|
| id | INTEGER PK | |
| zaman | TEXT | |
| kaynak | TEXT | `borsa` \| `zincir` |
| hesap | TEXT | `ana` \| `alt` \| `cuzdan` |
| adres_id | INTEGER NULL | `hesap='cuzdan'` ise `adres.id` |
| ag | TEXT NULL | borsa ağ adı (`AVAX-Avalanche C-Chain`) ya da zincir anahtarı (`avalanche`) |
| varlik | TEXT | `AVAX`, `USDC`, `TRY`… |
| miktar | TEXT | işaretli: giren `+`, çıkan `-` |
| dolar | TEXT NULL | o anki dolar karşılığı (işaretli); fiyat yoksa `NULL` |
| tur | TEXT | `cekim`, `yatirma`, `takas`, `gonderim`, `giris`, `ucret`, `bota_giris`, `bottan_donus`, `alim`, `satim`, `aktarim`, `taninmadi` |
| islem_kimligi | TEXT NULL | `txId` / `billId` / `ordId` |
| karsi | TEXT NULL | karşı taraf: `adres.etiket`, `ana`/`alt`, bot `algoId` ya da `NULL` |
| supheli | INTEGER | 1 = şüpheli token / adres zehirleme kalıbı |
| durum | TEXT | `ok` \| `okunamadi` |
| kaynak_okuma | TEXT | hangi araç/uç: `withdrawal-history`, `account_get_bills`, `onchainos:transactions-by-address`… |
| ham_kimlik | TEXT UNIQUE | tekrar yazmayı önleyen kaynak kimliği |

### `adres` · yazan Buğra
| alan | tip | açıklama |
|---|---|---|
| id | INTEGER PK | |
| adres | TEXT | tam adres (örnek veritabanında yer tutucu) |
| etiket | TEXT UNIQUE | `BENIM_1`… (tahmin “benim”), `ADRES_1`… (diğerleri) |
| kisa | TEXT | `0xABCD…1234` |
| ag | TEXT | zincir anahtarı (`ethereum`, `arbitrum`, `chiliz`, `polygon`, `tron`, `avalanche`…) |
| katman | INTEGER | okunabilen en derin katman: 1 çekim, 2 bakiye, 3 sonrası |
| tahmin | TEXT | `benim` \| `belli_degil` |
| kanit | TEXT | Türkçe kanıt cümlesi (adres içermez) |
| cekim_sayisi | INTEGER | |
| cekim_dolar | TEXT NULL | |
| ilk_cekim, son_cekim | TEXT | zaman |
| gezgin_url | TEXT NULL | gezgin bağlantısı (tam adres yalnız burada) |

### `fotograf` · yazan Buğra
| alan | tip | açıklama |
|---|---|---|
| gun | TEXT | |
| zaman | TEXT | fotoğrafın çekildiği an |
| yer | TEXT | `borsa:ana`, `borsa:alt`, `adres:<etiket>` |
| varlik | TEXT | |
| miktar | TEXT | **seviye** (gizli modda gösterilmez) |
| fiyat | TEXT NULL | dolar fiyatı; yoksa `NULL` |
| dolar | TEXT NULL | miktar × fiyat |

### `kopru` · yazan Buğra
Dün 09:00 → bugün 09:00. `kapsam` başına: `baslangic` + kalemler = `bitis`.

| alan | tip | açıklama |
|---|---|---|
| gun | TEXT | bugünün günü |
| kapsam | TEXT | `borsa` \| `servet` |
| sira | INTEGER | |
| kalem | TEXT | `baslangic`, `aktarim`, `disari`, `iceri`, `bot`, `fiyat`, `takas`, `ucret`, `aciklanamayan`, `izlenemeyen`, `bitis` |
| tutar | TEXT | dolar, işaretli (`baslangic`/`bitis` seviyedir → gizli) |
| varlik_tutar | TEXT NULL | JSON `{"AVAX": "-0.998"}` coin cinsinden |
| aciklama | TEXT | Türkçe kısa açıklama |
| olgular | TEXT | JSON liste `["o3","o4"]` |

### `olgu` · yazan Buğra
Anlatıcının tek girdisi. Sayıları Buğra'nın kodu hesaplar; model sayı üretmez.

| alan | tip | açıklama |
|---|---|---|
| oturum | TEXT | |
| no | TEXT | `o1`, `o2`… (oturum içinde tekil) |
| tur | TEXT | `cekim`, `takas`, `gonderim`, `taninmadi`, `kopru`, `bot_uyusmazlik`, `bot_tutuyor`, `adres_ozet`, `okunamayan_ag`, `supheli`… |
| alanlar | TEXT | JSON nesne; **sayılar Türkçe biçimli metin**: `{"miktar": "0,9828 AVAX", "tarih": "11 Ekim 2026 15:32"}` |
| gizli | INTEGER | 1 = seviye/yüzde içerir; gizli modda kullanılmaz |
| kaynak | TEXT | JSON liste: dayandığı `hareket.id` / `fotograf` / `cagri.id` |

### `uyari` · yazan Buğra
| alan | tip | açıklama |
|---|---|---|
| id | INTEGER PK | |
| oturum | TEXT | |
| zaman | TEXT | |
| tur | TEXT | `bot_uyusmazlik`, `adres_zehirleme`, `supheli_token`, `aciklanamayan`, `okunamayan_ag` |
| onem | TEXT | `acil` \| `orta` \| `bilgi` |
| olgular | TEXT | JSON liste |
| gonderildi | TEXT NULL | Telegram'a gidiş zamanı |

### `cagri` · yazan Buğra
OKX kanıt paneli. Her dış çağrı bir satır.

| alan | tip | açıklama |
|---|---|---|
| id | INTEGER PK | |
| oturum | TEXT | |
| zaman | TEXT | |
| kaynak | TEXT | `ATK` \| `OKX TR` \| `OnchainOS` \| `zincir` \| `Telegram` |
| ad | TEXT | araç ya da uç adı (`account_get_bills`, `GET /api/v5/asset/withdrawal-history`) |
| parametreler | TEXT | JSON, **maskeli** (adres → `0xABCD…1234`, anahtar yok) |
| sure_ms | INTEGER | |
| alanlar | TEXT | JSON liste: cevaptan kullanılan alanlar |
| satir | INTEGER NULL | dönen satır sayısı |
| sonuc | TEXT | `ok` \| `hata` |
| kod | TEXT NULL | hata kodu / HTTP durumu |
| salt_okunur | INTEGER | 1 |

### `cumle` · yazan Merve
| alan | tip | açıklama |
|---|---|---|
| id | INTEGER PK | |
| oturum | TEXT | |
| olgular | TEXT | JSON liste |
| metin | TEXT | |
| model | TEXT | `claude-sonnet-5-5` \| `claude-haiku-5-5` \| `kalip` |
| denetim | TEXT | `gecti` \| `kalip` |
| yer | TEXT | `telegram` \| `pano` \| `bant:<etiket>` |
| zaman | TEXT | |

### `isaret` · yazan Merve
| alan | tip | açıklama |
|---|---|---|
| adres_etiket | TEXT | `adres.etiket` |
| ag | TEXT | |
| sahip | TEXT | `benim` \| `benim_degil` |
| zaman | TEXT | en son satır geçerli |

### `muhur` · yazan Merve
| gun TEXT | kok TEXT | onceki_kok TEXT | islem_kimligi TEXT | agent_id TEXT | ag TEXT (`fuji`) | sozlesme TEXT | zaman TEXT |
|---|---|---|---|---|---|---|---|

### `iz` · yazan Merve
| iz_no TEXT | oturum TEXT | hedef TEXT | sira INTEGER | dusunce TEXT | arac TEXT | gozlem TEXT | karar TEXT | sonuc TEXT | zaman TEXT |
|---|---|---|---|---|---|---|---|---|---|

### `butce` · yazan Merve
| kullanici TEXT | ay TEXT | model TEXT | girdi_parca INTEGER | cikti_parca INTEGER | tutar_tl TEXT | tavan_tl TEXT (`35`) | durum TEXT |
|---|---|---|---|---|---|---|---|

## Çalıştırma bağı

1. Buğra'nın sabah işi (`python -m calistir.sabah`) `olgu`/`uyari`/`kopru` satırlarını `oturum` ile yazar.
2. `ANLATICI_KOMUT` doluysa (ör. `python -m anlatim.anlat --oturum {oturum}`) çalıştırır, **5 saniye** bekler, sonra `cumle` tablosundan `oturum` ve `yer='telegram'` ve `denetim='gecti'` satırını okur. Yoksa kalıp cümle.
3. Telegram mesajı: tek cümle + “Panoyu aç” → `PANO_URL/?oturum=<oturum>`.
4. Canlı bot izleyicisi aynı akışı `oturum=canli-<algoId>` ile çalıştırır.
