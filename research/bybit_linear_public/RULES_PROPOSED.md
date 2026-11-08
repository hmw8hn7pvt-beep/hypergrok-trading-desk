# Önerilen kurallar

Durum: **öneri, dondurulmamış**. Piyasa geçmişi üzerinde strateji performansı çalıştırılmadı. p-değeri, PASS veya avantaj iddiası yoktur.

- HyperGrok sabiti: `82bc645899b9581a693463b59553aa1329e021c4` (v1.7.1)
- Konfigürasyon SHA-256: `267d6c14a6975757a11dedaf877b6b3f0864a7db07887f550e8511a1551ba815`
- Şema: `bybit-linear-udar4-proposed-1`
- Kaynak: `python3 -m bybit_research config-hash`
- Bu hash, kullanıcı açıkça dondurup ayrıca onay verene kadar piyasa performansı için yetki değildir.

Araç yalnız `https://api.bybit.com` üzerinde belgelenmiş kamu GET ister. Hesap, emir, pozisyon, kaldıraç, marjin ve fon uçları yoktur. 1 USDT yalnız normalize birimdir; emir büyüklüğü, bakiye veya sermaye değildir. Portföy, likidasyon ve gerçekleşebilir dolum iddiası yoktur.

## Evren

Sabit dört ad: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT. SOLUSDT ve XRPUSDT koşullu adaydır; bu koşu onları elemedi ve uygunluklarını kapatmadı. Seçim, bugün hayatta olan altı adayın içinden yapılmış retrospektif bir sıralamadır. Kapanmış veya listeden çıkmış sözleşmeler o aday kümede yoktur. Bu hayatta kalma yanlılığıdır. 822 ve 1147 kayıtlı anlık görüntüler tarihsel evren değildir ve kullanılmadı.

Dönemler UTC ve yarı açıktır:

| Parça | Aralık |
| --- | --- |
| Isınma ve Aralık 2023 seçim penceresi | [2023-12-01T00:00:00Z, 2024-01-01T00:00:00Z) |
| Keşif | [2024-01-01T00:00:00Z, 2025-07-01T00:00:00Z) |
| Doğrulama | [2025-07-01T00:00:00Z, 2026-04-01T00:00:00Z) |
| Holdout adayı | [2026-04-01T00:00:00Z, 2026-10-01T00:00:00Z) |

Holdout dosyası açılırsa yalnız kapsama sayılır. Strateji özelliği, getiri veya p üretilmez. Kör segment sertifikası yoktur; bu yüzden çıkarım yapılmaz. Keşif ve doğrulama da bu teslimde değerlendirilmedi.

## Veri

İzinli kamu GET yolları:

- `/v5/market/kline`
- `/v5/market/mark-price-kline`
- `/v5/market/funding/history`
- `/v5/market/instruments-info`

Başka host, proxy veya yönlendirme yok. HTTP 401, 403 ve 451 denemeden durur. Diğer geçici hatalarda en çok dört deneme vardır. Kline pencereleri 1000 mumla sınırlıdır ve ilerlemezse durur. Funding sayfası en çok 40 sayfadır. Eksik gözlem BİLİNMİYOR'dur; sıfırla doldurulmaz, sembol veya dönem sessizce atılmaz.

Last mum birimleri belgede olduğu gibi baz hacim ve quote cirodur. Mark mumu, funding uzlaşmasındaki mark fiyatı değildir. Funding zaman damgaları tarihsel aralık takvimini kanıtlamaz. Güncel `instruments-info` tarihsel statü değildir. Ücret senaryoları güncel kamu yardım sayfalarından alınmış koşullu oranlardır, tarihsel veya kişisel tarife değildir. Zone kanıtı olmadığı için birincil senaryo S-inn (taker 0.110%) olarak durur; S-std (0.055%) strestir. Kayma senaryoları 2, 5 ve 15 bps; birincil 5 bps. PostOnly modellenmez.

## Defter

Mum 4 saattir. `r_t(N) = ln(C_t / C_{t-N})`. `σ_t`, son 42 bir-bar log getirisinin örneklem standart sapmasıdır, ddof=1. Biri eksikse σ BİLİNMİYOR'dur ve bu "sinyal yok" değildir. σ=0 bilinen geçersiz durumdur; sinyal üretilmez ve sayılır. `z_t(N) = r_t(N) / (σ_t √N)`. σ ve `d = 2 σ √N` sinyal kapanışında dondurulur.

Giriş bir sonraki mumun açılışındadır. Alış referansın `(1+b)` katı, satış `(1-b)` katıdır. `q = 1 / P_entry`. Net, `s q (P_exit - P_entry) - f q (P_entry + P_exit) - F` şeklindedir. Ayrı kayma terimi yoktur. Long stop `P_entry (1-d)` altındadır; `d ≥ 1` ise long önceden sayılan fizibilite atlamasıdır. Short stop `P_entry (1+d)` üstündedir. Stop dolumu, stop ile açılışın olumsuz olanıdır, sonra kayma uygulanır. Aynı mumda stop ve hedef varsa stop geçerlidir.

Zaman sınırı 18 mumdur: giriş `E` ise çıkış açılışı `E+18` mumdur ve bu açılış bölüm bitişinden kesin önce olmalıdır. Çıkış mumu `x` ise yeni sinyalin açılışı en erken `x+6` mumdur. Bölüm dışına taşan çıkış yoktur. Açık pozisyon varken mum eksikse pozisyon BİLİNMİYOR kalır ve silinmez.

H1: `z ≥ 2` long, `z ≤ -2` short. Hedef yok. Sonraki kapanışta `s z < 0` ise çıkış bir sonraki açılışa kuyruklanır.

H2: işaret tersinedir. `|z| ≥ 3` ise sinyal reddedilir ve sayılır. Hedef `T = C_{t-N}` dir. Açılış hedefi geçmişse maliyet yazılmadan iptal edilir. Hedef dolumu T'ye kayma uygular; lehte gap T'den iyi dolmaz. Geçersizleşme, orijinal aşırılık yönünde `sign(z_t) z_k ≥ 3` olunca bir sonraki açılıştır.

Funding birincil nakde yalnız uzlaşma damgası girişten ve çıkıştan kesin içerideyse ve modellenmiş dolumdan en az 5000 ms uzaktaysa girer. Pozitif oran long için ödemedir. Sınırdakiler etiketlenir ve birincil nakde girmez. Mark bilinmiyorsa birincil net BİLİNMİYOR'dur. Mark-to-market, gerçekleşmiş net artı açık `s q (Mark - P_entry)` eksi işlemiş giriş ücreti ve funding'dir. Anında kapanışın ücret ve kayması ayrı seridir.

## H2 rastgele kontrol önerisi

Ad: `H2-BR-mirror-v1`. Henüz kabul edilmedi. Kabul edilene kadar H2'nin E2 testi hesaplanmaz; iskelette p=1 yalnız yer tutucudur.

Uygun kapanışta σ biliniyor ve sıfırdan büyükse, defter boşsa, soğuma ve bölüm kuralı sağlanıyorsa Bernoulli(1/18) çekilir. Başarıda yön adil yazı-turadır. Çekiliş, H işleminin sonucunu, tutma süresini veya sinyal yönünü kullanmaz. `|z|≥2` ve `|z|≥3` kontrol girişi için filtre değildir.

Hedef `T_s = C_t + s |C_t - C_{t-N}|`. Hareket sıfırsa sayılan atlamadır. Açılış bu hedefi geçmişse H2 ile aynı iptal uygulanır. Geçersizleşme `s z_k ≤ -3` tir. Stop, süre, ücret, funding ve soğuma H2 ile aynıdır.

Tohum, taslaktaki `20261109 + r` kökünü taşır ve varyant, N, sembol ve koşu için ayrı PCG akışıdır. Böylece defterler aynı çekilişi paylaşmaz. Bu, taslağın tek akış cümlesinin açıklaştırılmasıdır.

## İstatistik iskeleti

24 hücre (6 varyant × 4 sembol) tanımlayıcıdır. Eşit sembol havuzu `θ = (μ_BTC + μ_ETH + μ_SOL + μ_XRP) / 4` dür. Bir sembolde sıfır işlem μ'yi tanımsız kılar; sıfır yazılmaz. Holm ailesi 12 testtir, α=0.05. H2 E2 bloke olduğu sürece reddedilemez.

İki okuma da öneridir ve piyasa verisine uygulanmadı:

- STAT-1b: ortak zaman bloklarında θ bootstrap standart hatası tek SE olarak kullanılır. Gözlenen örneklem veya bir yineleme tanımsızsa ya da SE sıfırsa p üretilmez.
- STAT-1: her yinelemenin kendi jackknife SE değeri vardır. Biri sıfırsa test bloke olur. Yerine koymalı çekiliş bunu sık üretir; bu kasıtlı olarak p vermez.

Blok uzunluğu 42 mumdur. 21 ve 84 duyarlılıktır, ayrı aile değildir. B=9999 bu teslimde piyasa üzerinde çalıştırılmadı.

## Taslakların çözümü

READINESS içindeki TBD eşikler, plan taslağındaki sabit önerilerle değiştirildi. U-geniş kurulmadı. Endeks serisi toplanmıyor. Tarihsel statü, tarihsel funding aralığı ve uzlaşma markı bilinmiyorsa katı yeterlilik geçmez. Güncel symbolType, birincil ücreti S-std yapmaz.

Sapma kimlikleri D1–D25 konfigürasyon hash'inin içindedir. Özet: plan sabitleri, H2 ayna hedefi, ayrık tohum, kontrolde z filtresi olmaması, 5000 ms funding sınırı, dolum zamanının bar açılışı olması, bilinmeyenin olumlu sonucu bloke etmesi, S-inn birincil ücret, endeks yok, kaldıraç istatistiğe girmez, PostOnly yok, holdout yalnız kapsama, iki bootstrap okuması, B=9999 piyasa dışı, koşullu altcoinler durur, Closed sorgusu yalnız dört ad, 403 duruşu, Aralık 2023 ısınması, ilk bölüm girişinin önceki kapanıştan sinyal alabilmesi, açık pozisyonda boşluğun BİLİNMİYOR bırakması, sıfır işlemli kontrol koşusunun tanımsız olması, dejenere örneklemde p olmaması, mark mumu uzlaşma markı değildir, geçersizleşme giriş mumunun kapanışında da bakılabilir.
