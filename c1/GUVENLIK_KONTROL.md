# C-1 güvenlik kontrolü

Kontrol, kod incelemesi ve `python3 -m unittest discover -s c1/tests -t .` koşusuna dayanır. Ortam Python 3.12.3. Gerçek kaynak ağacı açılmamıştır.

| Kontrol | Sonuç | Kanıt |
| --- | --- | --- |
| Varsayılan DRY-RUN; kaynak ve `/home/box` açılmaz | Geçti | test 29 |
| `--gercek` onaysızsa dosya açılmaz | Geçti | test 30 |
| Onaylı gerçek mod, 3.13.5 değilse dizin açmadan durur | Geçti | test 31 |
| `/workspace` ve `/home/box` yalnız `config.py` içinde sabit dizgidir | Geçti | test 34 |
| `os.readlink`, `readlinkat`, `pathlib`, `subprocess` yok | Geçti | test 34 |
| Dış R5 hash'i kodda sabit değil; 64 onaltılık tek sabit manifest özetidir | Geçti | test 33, test 34 |
| YG: `..`, tekrar, NUL ve kök dışı yol dosya açılmadan reddedilir | Geçti | test 08, test 09 |
| Dizin symlink'i O_NOFOLLOW ile izlenmez | Geçti | test 10 |
| A-ek ve MK-5 yoluna open/stat/lstat/readlink/listdir yok | Geçti | test 17, test 36 |
| Envanter başlığı `grup,yol,tur,boyut_bayt,mtime_trt,izin,bayrak,not` | Geçti | test 36 |
| Eski R2 dokunulmaz; sıradaki geçici ad R3 | Geçti | test 36 |
| Manifest göreli yolları küme olarak, sıra şartı olmadan | Geçti | test 36, test 37 |
| Gerçek yol düzeni geçici kökte uçtan uca, MK-5 ve R1'e syscall yok | Geçti | test 36 |
| R1 adı açılmaz, stat edilmez, içeriği değişmez | Geçti | test 28 |
| Kaynak `mtime_ns` başarılı arşivde değişmez | Geçti | test 01 |
| Symlink metni dolaylıdır; `os.readlink` çağrılmaz | Geçti | test 02 |
| Okuma sırasında boyut değişirse durulur | Geçti | test 11 |
| Adım 1 metadata farkında durulur | Geçti | test 12 |
| Hash uyuşmazlığında devam edilmez | Geçti | test 13, test 14 |
| Manifest satır kümesi beş değilse durulur | Geçti | test 15, test 16 |
| Manifest 547 bayt değilse ve sabit zorunluysa durulur | Geçti | test 33 |
| SYNC_FD inode farkında yazıya geçilmez | Geçti | test 18 |
| R2 veya nihai ad varsa durulur, üzerine yazılmaz | Geçti | test 19, test 20 |
| renameat2 hatasında R2 kalır, nihai ad oluşmaz | Geçti | test 21 |
| K2 fsync hatasında taşıma yapılmaz | Geçti | test 22 |
| TarFile kapanış hatasında teslim edilmez | Geçti | test 23 |
| Eksik, fazla üye ve PAX farkı teslimden önce durdurur | Geçti | test 24, test 25, test 26 |
| K5 hatası `TESLIM EDILDI` durumunu bozmaz | Geçti | test 27 |
| K4 fsync hatası `COMMIT_DURABILITY_UNCERTAIN` bırakır | Geçti | test 32 |
| Çıktı O_EXCL ve RFD üzerindendir; arşiv sonunda 0444 olur | Geçti | test 01 |
| Unicode, Türkçe, uzun, boş ve büyük dosya | Geçti | test 03–07 |

## Gerçek komutun durduğu yer

```bash
python3 -m c1.main --yapilandirma /guvenli/c1_gercek.json --gercek --onay "ONAY C-1"
```

Durma sırası:

1. Onay metni `ONAY C-1` değilse yapılandırma dosyası bile açılmaz.
2. Yapılandırma yolu `/workspace` veya `/home/box` altındaysa açılmaz.
3. MK-1..MK-4 değeri 64 onaltılık değilse yükleme, kaynak açılmadan koşul 6 ile biter. Örnek dosyadaki yer tutucular bu kapıdadır.
4. Yollar kartla aynı ve hash biçimi geçerliyse, bu ortamda `platform.python_version()` `3.12.3` olduğu için `calistir` koşul 1 üretir. `ac_cikti_ust` çağrılmaz. `/workspace` ve `/home/box` açılmaz.
5. Ancak Python 3.13.5, kart yolları, dolu hash'ler ve açık onay bir arada olursa program çıktı üstünü ve kaynak zincirini açar. Bu teslimat o adımı çalıştırmadı.

Üretime hazır ilanı, gerçek ağaç üzerinde ve kart sürümünde yapılmış bir koşuya bırakılmıştır. Sentetik sınamalar geçmiştir; gerçek C-1 teslimi yapılmış sayılmaz.
