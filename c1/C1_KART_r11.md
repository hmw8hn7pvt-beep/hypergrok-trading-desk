# KART C-1 r11 — arşivleme ve mühür ayrımı

Durum: r9 metni, r10 (J1–J4) ve r11 (L1–L5) ile birleştirilmiştir. Çakışmada r10, r11 ve aşağıdaki kapılar geçerlidir. Bu belge işlemi başlatmaz.

Amaç: Araştırma dosyalarını kaynaklara yazmadan üç ayrı TAR'a almak. Araştırma verisi canlı veriden bu arşivlerle ayrılır.

## Kapılar

- Varsayılan mod DRY-RUN'dur. Kaynak, envanter ve çıktı kökü açılmaz.
- Gerçek mod yalnız `--gercek` ve `--onay "ONAY C-1"` birlikteyken açılır.
- Yapılandırma dosyası `/workspace` veya `/home/box` altında olamaz.
- Gerçek mod kart yollarını, sayıları ve manifest sabitini zorunlu kılar.
- Gerçek mod Python 3.13.5 ister. Başka sürümde koşul 1, dizin açılmadan biter.
- MK-1..MK-4 hash'leri kodda sabit değildir. Çalışma anında yapılandırmadan okunur. Eldeki kısaltmalar: MK-1 `1793653c…550b`, MK-2 `5763679542…342c`, MK-3 `eb161b65…adc9`, MK-4 `b29d0bbb…f202`.
- Manifest `SHA256SUMS.txt` sabittir: 547 bayt, SHA-256 `a98b9dc8c7742f9588da23e6a670d7f5f138407953d1a7a835b27a1cfaf5ca02`. 3a-0 bu sabitle karşılaştırır ve raporda bağımsız doğrulama olmadığı yazılır.

## Kapsam (değişmez)

- Envanter 2.908 kayıt. İşlem listesi 2.897: A 1.936, B1 910, B2 51.
- Normal dosya 2.896, symlink 1.
- A-ek 11 dosya kapsam dışıdır. Hiçbir adımda open, stat, lstat, yol yoklaması veya arşiv yoktur.
- MK-5 kapsam dışıdır. Yalnız manifest satırındaki metinsel yoldur. open, read, stat, lstat, hash, arşiv ve envantere ekleme yoktur. Kaynak kökünün, dokunulmaz klasörlerin, geçici klasörün ve nihai klasörün içinde olamaz. Çıktı üstünün başka bir yerinde durabilir. Gerçek ek `/home/box/agent-data/...` altındadır.
- B1 ve B2 analiz edilmez; yalnız arşivlenir ve KARANTİNA diye işaretlenir.
- Dokunulmaz önceki klasörler: `GECERSIZ_c1_arsiv_20261110` (R1) ve `GECERSIZ_c1_arsiv_20261110_R2`. Açılmaz, listelenmez, stat edilmez.
- Sıradaki geçici klasör yapılandırmadan gelir: `GECERSIZ_c1_arsiv_20261110_R3`. Nihai ad `c1_arsiv_20261110`.
- Gerçek kaynak kökü `/workspace`. Gerçek çıktı üstü `/home/box`.
- Gerçek envanter: `/workspace/hypergrok_v2_plan_20261109/C1_DOSYA_LISTESI.csv`.
- Gerçek R5 dizini: `/workspace/trading-desk-research-v1.7.1/research/intraday-r5-20261109/freeze`.
- Gerçek yapılandırma dosyası `/var/tmp/c1_r11_yapilandirma/c1_gercek.json` olabilir. Bu yol yasak köklerin dışındadır. Gerçek modda `kapsam_sabitleri` ve `manifest_sabitleri_zorunlu` anahtarları yazılmazsa açık kabul edilir.

İzole sınama bu sayıları ve bu yolları kullanmaz. Küçük sentetik ağaçta aynı kuralları, kendi köküne göre uygular.

## Türler

Yalnız normal dosya ve symlink. Başka tür durdurur. İçerik yalnız inode'u doğrulanmış normal dosyada açılır. Symlink hedefi izlenmez. Metin `readlink` ile okunmaz.

## YG (metin)

İşlem listesindeki her yol için, G1'den önce:

- Yol mutlaktır ve kaynak kökü artı `/` ile başlar. Gerçek modda kök `/workspace` olduğundan ark adları `workspace/` ile başlar.
- Boş bileşen, `.`, `..`, sondaki `/`, `//` ve NUL reddedilir.
- `os.path.normpath(yol) == yol` değilse durulur. Yol düzeltilmez.
- Yollar ve arcname değerleri benzersizdir. arcname, baştaki `/` atılarak elde edilir.
- İhlalde koşul 2. İhlal eden yola gidilmez.
- Symlink metni YG'ye girmez; yalnız linkname olarak saklanır.

## Güvenli açma

Önbellek yok. YG'den geçmiş yollar.

G1: `/` tanıtıcısından başlanır. Her ata `O_PATH|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC` ile açılır. İki ölçüm (fstat ve fstatat, sembolik bağ izlenmeden) aynı olmalıdır. Tür dizin olmalıdır.

G2: `O_PATH|O_NOFOLLOW` ve fstat. Tür normal dosya veya symlink olabilir.

G3a: `/proc/self/fd/<G2>` üzerinden `O_RDONLY|O_NOATIME|O_CLOEXEC`. Bu adımda `O_NOFOLLOW` yoktur. fstat, G2 ve kayıtla aynıdır. Okuma bu tanıtıcıdandır. Okuma bitince, son fstat'tan önce gözlem noktası çalışır; boyut veya `mtime_ns` değiştiyse koşul 11.

G3b kapalıdır. `readlink` ve `readlinkat` çağrılmaz.

S-A: Symlink metni envanterdedir. `len(metin.encode("utf-8", "surrogateescape"))` güvenli zincirin `st_size` değerine eşittir. 0e ile 6a arasında inode, `mtime_ns` ve `ctime_ns` aynı kalır. Raporda `symlink metni: DOLAYLI DOĞRULANDI` yazar.

M1, referans yokken iki yöntemi kaydeder. M2, sonraki her erişimde kayda bakar. Uyuşmazlık durdurur.

Kaynak kökünün altındaki dizinlerde zaman damgaları da karşılaştırılır. Kökün üstündeki ata dizinlerde aygıt, inode, tür ve izin karşılaştırılır. Ayrıntı [BILINEN_SINIRLAMALAR.md](BILINEN_SINIRLAMALAR.md) maddesindedir.

## Çıktı (L1–L5)

Mutlak yoldan çıktı açılmaz.

- PFD: çıktı üstü, `/` zinciriyle `O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`. Kimlik P0 `(st_dev, st_ino)` saklanır.
- Nihai ad veya R2 adı varsa koşul 1. Üzerine yazılmaz. R1 sorgulanmaz.
- Platform denemesi: en çok bir dizin ve üç dosya, sonra yalnız `C1_PLATFORM_DENEME_*` adları silinir. `renameat2` ve `RENAME_NOREPLACE` yoksa durulur.
- R2: umask 077 altında `mkdirat(PFD, R2, 0700)`. RFD = `openat` `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`. R0: izin 0700, sahip euid, nlink 2, `st_dev` çıktı üstüyle aynı.
- Her çıktı: yazma tanıtıcısı `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` ve 0600. Hemen ardından SYNC_FD `O_WRONLY|O_NOFOLLOW|O_CLOEXEC`. `fstat(yazma)`, `fstat(SYNC_FD)` ve `fstatat(..., AT_SYMLINK_NOFOLLOW)` aynı `st_dev` ve `st_ino` olmalıdır. Tür normal dosya, nlink 1. Fark varsa koşul 12. SYNC_FD'ye bayt yazılmaz.
- PFD ve RFD, K5 bitene kadar açık kalır. Hata K3'ten önceyse R2 `GECERSIZ_` adıyla kalır; silinmez ve taşınmaz.

## TAR

Üç arşiv: `A_arastirma.tar`, `B1_karantina.tar`, `B2_karantina.tar`.

`AYAR = (PAX_FORMAT, "utf-8", "surrogateescape")`.

```text
TarFile(name=<göreli ad>, mode="x", fileobj=os.fdopen(yazma_fd, "wb"),
        format=AYAR[0], encoding=AYAR[1], errors=AYAR[2], pax_headers={})
```

Açılışta format, kodlama ve hata kipi AYAR ile aynı olmalıdır.

Her üye için yeni `TarInfo`. Alanlar: arcname, REGTYPE veya SYMTYPE, izin, uid, gid, uname ve gname boş, symlink için boyut 0, `mtime = floor(mtime_ns/10^9)`, linkname envanter metni, devmajor ve devminor 0.

PAX alanları, tam yedi adet:

- `HYPERGROK.orig_mtime_ns`
- `HYPERGROK.orig_atime_ns`
- `HYPERGROK.orig_ctime_ns`
- `HYPERGROK.orig_inode`
- `HYPERGROK.orig_dev`
- `HYPERGROK.grup`
- `HYPERGROK.sha256`

0c2, hash yerine 64 adet `0` ile `tobuf` uzunluğunu H_i diye saklar. Yazımda gerçek hash aynı uzunluktadır; `len(b) != H_i` veya ofset farkı koşul 12.

Yazım sırası: `tf.close()`, kapanışın doğrulanması, `fobj.close()`, sonlandırma blokları, RECORDSIZE yuvarlaması. Boyut `ceil((V_g+1024)/10240)*10240`. Sıfır bölge en az 1024 bayttır.

Sonra arşiv RFD üzerinden salt okunur açılır, inode SYNC kaydıyla aynı olmalıdır. Bellekte: üye sayısı, adlar, türler, YG, PAX, başlık baytları ve içerik hash'i. Doğrulama bitmeden teslim yoktur. Doğrulama sonrası yalnız arşivler SYNC_FD üzerinden 0444 yapılır.

## R5

Manifest beş satırdır. Yol kümesi tam olarak MK-1..MK-5 olmalıdır. 3-B (i) biçim, (ii) bu küme, (iii) hash yalnız MK-1..MK-4. 3-B (iv) bayt özgünlüğü doğrulanmaz, raporda yazılır, durdurmaz.

MK-1, MK-2 ve MK-3 hem manifest satırı hem dış referans hem dosya özeti ile eşleşir (3a-1). MK-4 dış referans, manifest satırı ve dosya özeti ile eşleşir (3a-2). SHA256SUMS.txt için dış referans yoktur; gerçek modda boyut ve kendi SHA-256 değeri R1 sabitidir.

Beş R5 dosyası Grup A, normal dosya ve 0444'tür: üç kural dosyası, `FREEZE_RECORD.txt` ve manifest. K444, işlem listesinde envanter izni 0444 olan normal dosyalardır. Gerçek modda tam 216'dır ve beş R5 dosyasını içerir. Symlink ve A-ek bu kümede değildir. İzin düzeltilmez.

`R5_FREEZE_IZIN.txt` en çok 9 satırdır.

## Adımlar

0a platform ve çıktı üstü. 0b envanterin güvenli okunması, işlem listesi, YG, sayılar. 0c1 envanter boyutlarıyla disk üst sınırı. 0d dizin M1. 0e dosya M1 ve S-A. 0c2 kesin H_i ve disk. 0f O_NOATIME açılıp kapanır; symlink'te yalnız G1+G2. 0g R5. Adım 1 metadata yeniden alınır. Adım 2 birinci tam hash. Adım 4 ikinci tam okuma ve arşiv. Adım 5 bellek doğrulaması. Adım 6 üçüncü hash ve metadata. Sonra `RAPOR.txt`: `Kapanış: henüz yapılmadı`.

K1 uygulama tamponları. K2 SYNC_FD kimliği, her dosyada fsync, alt dizinler en derinden, RFD fsync; SYNC_FD kapanır, PFD ve RFD açık kalır. K3 kimlikler, sonra `renameat2(PFD, R2, PFD, nihai, RENAME_NOREPLACE)`, sonra RFD hâlâ R0. K4 `fsync(PFD)` ve P0. K1–K4 tamamsa durum `TESLIM EDILDI`. K3 başarılı ve K4 başarısızsa `COMMIT_DURABILITY_UNCERTAIN`. K5, K4'ten sonra `TESLIM_BILDIRIMI.txt` dosyasını RFD üzerinden O_EXCL ile yazar, fsync eder, RFD'yi fsync eder, sonra PFD ve RFD kapanır. K5 hatası teslim durumunu değiştirmez.

## Disk

`T_g = ceil((V_g+1024)/10240)*10240`. `V_g` başlıklar artı 512'ye yuvarlanmış veridir. Symlink verisi 0'dır. `T_arsiv = T_A + T_B1 + T_B2`. Boş alan en az `T_arsiv + R + 2 GiB` olmalıdır. R, karttaki çıktı üst sınırıdır. `renameat2` ek alan istemez. Yetmezse koşul 3.

## On yedi durdurma

1. Platform, sürüm, renameat2, R2 veya nihai ad zaten var, onay ya da kart yolu uyuşmazlığı.
2. Envanter, sayı, A-ek sızıntısı, YG, K444.
3. Disk.
4. M1 yöntem farkı veya desteklenmeyen tür.
5. O_NOATIME.
6. R5, 3a, 3-B (i)(ii)(iii), 3b, 3c, K444 izin sapması.
7. Adım 1 farkı.
8. G1 zinciri.
9. G2 / G3a fstat farkı.
10. Symlink: readlink, S-A uzunluğu veya inode/zaman.
11. Okuma sırasında boyut veya mtime.
12. TAR, AYAR, H_i, ofset, günlük veya rapor sınırı, flush, fsync, kapatma, renameat2. K4 başarısızlığı durumu belirsiz yapar.
13. Eksik, fazla, yinelenen, A-ek, kötü tür veya YG'ye aykırı üye.
14. Hash.
15. PAX veya başlık baytı.
16. Kaynak dosya değişti.
17. Kaynak dizin değişti.

Otomatik düzeltme, yeniden deneme, yedek yol, eksik veri tamamlama, geri alma ve izin yazma yoktur. Her hatada kod, aşama, açıklama, beklenen ve gerçek değer vardır.

1–7, Adım 2'den önce yoklanır. Durdurmayan tek kayıt 3-B (iv)'tür.

## Kalıcı kurallar

- Kaynakta yazma, chmod, chown, utime ve atime yazma yoktur. SYNC_FD kaynakta açılmaz.
- B1 ve B2 araştırmaya girmez.
- Mühürden sonra adlar ve metadata girdi yapılmaz.
- `/workspace` altına bir şey yazılmaz.
- Fazla dosya kontrolü yapılmaz. Bu cümle raporda durur.
