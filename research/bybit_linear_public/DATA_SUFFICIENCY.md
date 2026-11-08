# Veri yeterliliği

Bu dosya piyasa geçmişi üzerinde strateji performansı değildir. Toplama, değerlendirme değildir. Holdout strateji özelliği veya getiri için açılmadı.

- HyperGrok sabiti: `82bc645899b9581a693463b59553aa1329e021c4`
- Konfigürasyon SHA-256: `267d6c14a6975757a11dedaf877b6b3f0864a7db07887f550e8511a1551ba815`
- Manifest SHA-256: `3e3f4c7d1a731255b4aaf2336c7c35d6d987ba370ccd9567806051aba355e8cc`
- Manifest üretim zamanı (UTC): `2026-11-08T23:46:39.765Z`
- Toplama sonucu: `blocked`
- Çevrimdışı doğrulama: `consistent` (çıkış kodu 0). Bu, hash bütünlüğüdür; veri yeterliliği veya strateji PASS değildir.
- Katı birincil yeterlilik: **geçmedi**

## Karar

Gerekli tarihsel seri ve kimlik bu koşuda gözlenmedi. Katı kural bilinmeyeni geçirmez. Eksik gözlem sıfır işlem diye yazılmadı. Vekil fiyat, sıfır funding veya kısaltılmış dönem konmadı. Dört sembolün hiçbiri sessizce çıkarılmadı. SOLUSDT ve XRPUSDT koşullu aday olarak duruyor.

## Erişim engeli

Resmi koleksiyon aracı tek bir GET gönderdi ve durdu. Başka host, proxy veya bölge uç noktası denenmedi.

| Alan | Değer |
| --- | --- |
| İstek | `GET https://api.bybit.com/v5/market/instruments-info?category=linear&symbol=BTCUSDT` |
| Plan kimliği | `0000` (ön kontrol) |
| HTTP | 403 |
| Alım zamanı (UTC) | `2026-11-08T23:46:39.765Z` |
| Sunucu `Date` | `Sun, 08 Nov 2026 23:46:39 GMT` |
| Sunucu | CloudFront, `X-Cache: Error from cloudfront` |
| Gövde SHA-256 | `7ef856c945703d5772f1b1f2a8c65913247c9b0769302b10facfe14fa1e2083c` |
| `blocker.json` SHA-256 | `bc94c70f96db02f0a34bbc4495a264dcc4f5d48c109ff646139354495b3dce82` |
| Gövde | CloudFront, dağıtımın ülkeden erişimi engellediğini söylüyor |

Gövde ülke engeli metnini içeriyor. Bu hem bölge engeli hem de belgedeki "access too frequent" 403 sınıfı için aynı duruştur: tekrar yok, host değişimi yok.

Plan 26 iş içeriyordu. Biri denendi, 25'i gönderilmedi: ETHUSDT, SOLUSDT ve XRPUSDT güncel kimlik; dört sembolün `status=Closed` sorgusu; altı adayın Aralık 2023 günlük cirosu; dört sembolün 4s last, mark ve funding serileri.

Bu hashed kayıttan önce aynı URL'ye iki tanı amaçlı GET de 403 döndü. Onlar pakete yazılmadı. Paketteki kanıt yukarıdaki tek kayıtlı istektir.

## Sembol ve dönem

İstenen aralıklar UTC ve yarı açıktır. Isınma ve seçim penceresi [2023-12-01, 2024-01-01). Keşif [2024-01-01, 2025-07-01). Doğrulama [2025-07-01, 2026-04-01). Holdout kapsaması [2026-04-01, 2026-10-01).

| Sembol | Rol | Last 4s | Mark 4s | Funding | Güncel kimlik | Tarihsel statü | Launch | Katı yeterlilik |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | sabit | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | UNKNOWN | NOT_OBSERVED | geçmedi |
| ETHUSDT | sabit | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | UNKNOWN | NOT_OBSERVED | geçmedi |
| SOLUSDT | koşullu | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | UNKNOWN | NOT_OBSERVED | geçmedi |
| XRPUSDT | koşullu | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | NOT_OBSERVED | UNKNOWN | NOT_OBSERVED | geçmedi |

Aralık 2023 günlük ciro da alınamadı. Yayınlanmış sıralama bu koşuda yeniden ölçülmedi ve değiştirilmedi. Eski taslaktaki launchTime değerleri bu koşunun API gözlemi değildir; kimlik kanıtı yapılmadı.

Üç işlem dönemi ve ısınma penceresi için de aynı hüküm geçerlidir: mum kapsamı, mark kapsamı, funding tamlığı ve dönem içi statü BİLİNMİYOR. Holdout ayrı tutulacaktı; o dosya da oluşmadı ve strateji hesabına açılmadı.

## Neden geçmedi

- Tarihsel sözleşme statüsü, launch sonrası süreklilik ve delist zamanı resmi bir dönem kaydından gelmedi.
- Mark mumu, funding anındaki mark baskısı değildir. Bu belirsizlik, veri gelseydi de birincil funding nakit akışını bloke ederdi.
- Funding zaman damgalarının dizilişi, tarihsel funding aralığını kanıtlamaz. Aralık takvimi bu koşuda yok.
- Ücret ve zone için gözlem veya geçerlilik zamanı yok. Güncel kamu oranları tarihsel tarife değildir.
- Sıfır doldurma, vekil seri ve sessiz kısaltma uygulanmadı. Uygulanmış olsaydı yeterlilik yine geçmezdi.

## Hayatta kalma yanlılığı

Dört ad, bugün görülebilen sözleşmelerden geriye bakılarak sabitlendi. SOLUSDT ve XRPUSDT, listelenmeye devam eden altı adayın içinde ciroya göre öne çıkan iki addır. Kapanmış sözleşmeler o seçime girmedi. İleride bir sonuç yetkisi olsa bile o sonuç yalnız bu dört adı anlatır; tüm tarihsel USDT linear evrenin tahmini olmaz. 822 Trading anlık görüntüsü ile 1147 statü birleşimi farklı kapsamlardır ve ikisi de tarihsel evren değildir.

## Doğrulama komutları

```bash
python3 -m bybit_research verify --bundle /tmp/bybit-public-bundle
python3 -m bybit_research sufficiency --bundle /tmp/bybit-public-bundle
```

İlki bu pakette 0 döndü. İkincisi 1 döndü: katı yeterlilik yok. `performance` 3 döndü ve piyasa sonucu yazmadı.
