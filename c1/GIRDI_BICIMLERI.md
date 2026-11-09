# Gerçek girdiler

Kodun gerçek dünyadan okuduğu girdiler ve bu çalışmada kullanılan biçim. Bilinmeyen biçim tahmin edilmez.

## Envanter CSV

UTF-8, virgül, başlık satırı artı kayıtlar. Başlık birebir:

`grup,yol,tur,boyut_bayt,mtime_trt,izin,bayrak,not`

Grup eşlemesi: `A_arastirma` → A (1936), `B1_canli_muhur_riskli` → B1 (910), `B2_anlik_goruntu_muhur_riskli` → B2 (51), `A_ek_oneri` → kapsam dışı (11). Başka grup durdurur.

`tur`: `file` ya da `symlink-><hedef>`. Hedef, `symlink->` önekinden sonraki metindir. Tek symlink bir dizine işaret eder; izlenmez. S-A, bu metnin UTF-8 uzunluğunu güvenli zincirin `st_size` değeriyle karşılaştırır.

`boyut_bayt`: normal dosyada ölçülen boyutla eşleşmelidir. Symlink satırında 0'dır; bu, bağın kendi `st_size` değeri değildir.

`izin`: `0o644`, `0o444` veya `0o777`. K444, `0o444` olan 216 normal dosyadır.

`mtime_trt`: saniye çözünürlüklü TRT metni. Bilgi amaçlı taşınır. Karşılaştırma, koşu içindeki nanosaniye kayıtlarıyla yapılır.

`bayrak` ve `not` analiz edilmez; işlem listesine taşınır.

Envanterde sha256 sütunu yoktur. Hash koşu sırasında kaynaktan hesaplanır.

## R5 manifesti

`SHA256SUMS.txt`, 547 bayt, LF ile biter. Satır biçimi sha256sum metin kipidir: `<64 onaltılık>␠␠<yol>`.

Gerçek satır sırası: `R5_FROZEN_RULES.md`, `DOWNLOAD_SPEC_R5.md`, `RUN_SPEC_R5.md`, MK-5'in mutlak yolu, `FREEZE_RECORD.txt`. İlk üç ve son satır freeze dizinine göre görelidir. MK-5 dördüncü satırdadır ve yalnız metindir. Doğrulama sıraya değil, çözülmüş yol kümesine bakar. Hash karşılaştırması yalnız MK-1..MK-4 içindir.

## Yapılandırma

JSON. Gerçek dosya `/var/tmp/c1_r11_yapilandirma/c1_gercek.json` olabilir. Geçici ad `gecici_adi` alanındadır; sıradaki değer `GECERSIZ_c1_arsiv_20261110_R3`. `dokunulmaz_klasorler` R1 ve eski R2 adlarını taşır. Nihai ad `c1_arsiv_20261110`.

## BİLİNMİYOR

- `R5_FROZEN_RULES.md`, `DOWNLOAD_SPEC_R5.md`, `RUN_SPEC_R5.md` ve `FREEZE_RECORD.txt` dosyalarının iç biçimi. Yalnız bayt olarak hash'lenirler.
- MK-1..MK-4 hash'lerinin tam 64 karakteri. Yapılandırmadan okunur; elde yalnız ön ekler vardır.
- `bayrak` değerlerinin sözlüğü. Sütun analiz edilmez.
- `not` sütununun şeması. Serbest metin olarak taşınır.
- `mtime_trt` metninin saat dilimi eki. Örnekler `YYYY-MM-DD HH:MM:SS` biçimindedir ve ayrıştırılmaz.
