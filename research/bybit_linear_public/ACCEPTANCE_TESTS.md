# Kabul testleri

Sentetik testler ve kamu toplama doğrulaması çalıştı. Piyasa geçmişi üzerinde strateji performansı, p-değeri ve PASS çalışmadı.

Komutlar `research/bybit_linear_public` içinden:

```bash
python3 -m unittest test_acceptance.py
python3 -m bybit_research config-hash
python3 -m bybit_research collect --output /tmp/bybit-public-bundle
python3 -m bybit_research verify --bundle /tmp/bybit-public-bundle
python3 -m bybit_research sufficiency --bundle /tmp/bybit-public-bundle
python3 -m bybit_research performance
```

## Sonuçlar

| Komut | Sonuç |
| --- | --- |
| `python3 -m unittest test_acceptance.py` | 15 test, OK |
| `config-hash` | `267d6c14a6975757a11dedaf877b6b3f0864a7db07887f550e8511a1551ba815` |
| `collect` | çıkış 4, `result=blocked`, 1 istek, 25 istek gönderilmedi |
| `verify` | çıkış 0, `verification=consistent` |
| `sufficiency` | çıkış 1, katı yeterlilik yok |
| `performance` | çıkış 3, piyasa performansı reddedildi |

Toplama zamanı `2026-11-08T23:46:39.765Z`. Manifest SHA-256 `3e3f4c7d1a731255b4aaf2336c7c35d6d987ba370ccd9567806051aba355e8cc`. 403 gövdesi SHA-256 `7ef856c945703d5772f1b1f2a8c65913247c9b0769302b10facfe14fa1e2083c`. Ayrıntı [DATA_SUFFICIENCY.md](DATA_SUFFICIENCY.md) içindedir.

## Sentetik kapsam

Testler ağ kullanmaz. Sahte taşıyıcı 403, 500 ve şema yanıtları verir.

- Allowlist: POST, emir yolu, kimlik bilgisi parametresi ve `api.bybit.com` dışı URL reddedilir. İstek başlığında yalnız `User-Agent` ve `Accept` vardır.
- 403 tek istekle durur, ülke engelini yazar, kalan planı göndermez, hash doğrulamasından geçer ve resume ile aynı engeli yeniden denemez.
- 500 en çok dört denemedir. Kurtarılan yanıt kabul edilir, tükenen deneme başarısız olur.
- Ters kline sırası ayrıştırılır. Aynı kayıt bir kez tutulur. Çelişen kapanış seri yi kullanılamaz yapar. Bozuk OHLC ve yanlış mark genişliği reddedilir. Sayfa ilerlemezse funding sayfalama durur. Sayfa bütçesi tam kapsama sayılmaz.
- Eksik mum BİLİNMİYOR'dur, `zero_sigma` atlaması değildir. Düz ve bilinen σ=0 atlaması sayılır ve unknown değildir.
- Sinyal, gelecekteki kapanışı kullanmaz. Giriş bir sonraki bardadır. `q = 1/P_entry`.
- Stop, açılış stopun ötesine gap yapınca açılıştan ve kaymadan dolar. Stop ve hedef aynı mumda ise stop kazanır. Lehte gap hedeften daha iyi dolmaz. Açılış hedefi geçtiyse maliyet yazılmaz.
- Funding işareti: pozitif oran long için ödemedir, short için alıştırmadır. Giriş damgasındaki funding belirsizdir ve birincil nakde girmez. Ücret iki bacağa bir kez yazılır; ayrı kayma terimi yoktur.
- Mark-to-market, varsayımsal çıkış maliyetini ana seriden ayrı tutar. Mark yoksa BİLİNMİYOR'dur, sıfır değildir.
- Soğuma 6 bardır. Bölüm bitişindeki bar deftere girmez. `d ≥ 1` long ve `|z| ≥ 3` H2 retleri sayılır.
- H2 kontrolü aynı tohumda aynı hedefi üretir. Hedef `C_t + s |C_t - C_{t-N}|` dir. Giriş kararı, girişten sonraki bir bar değiştirilince değişmez. Kaldıraç, qtyStep ve minNotional parametreleri yoktur.
- Sıfır işlemli sembol havuzu tanımsızdır. Jackknife ve Monte Carlo p aritmetiği sabittir. Ortak SE bootstrap'i deterministiktir. İç SE sıfır olan yineleme p vermez. Holm ailesi 12 testtir ve hesaplanmayan H2 E2 reddetmez.
- İskelet 24 hücredir. Hepsi `not_executed`. `run_market_performance` ve CLI `performance` yetki hatası verir.
- Toplayıcı motoru import etmez. Holdout satırı keşif CSV'sine yazılmaz. CSV başlığında sinyal, z veya net yoktur.

## Bilerek çalıştırılmayanlar

Piyasa mumları üzerinde H1, H2, kontrol, bootstrap, Holm veya holdout değerlendirmesi yok. Koleksiyon komutu motoru çağırmaz. `scripts/check.sh` bu araştırmayı kendiliğinden toplamaz ve performans çalıştırmaz.
