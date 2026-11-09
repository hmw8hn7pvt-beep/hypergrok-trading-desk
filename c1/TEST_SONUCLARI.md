# C-1 sınama sonuçları

Komut: `python3 -m unittest discover -s c1/tests -t . -v`

Ortam: Python 3.12.3. Kartın gerçek mod sürümü 3.13.5'tir; izole sınamalar bu yüzden sürüm eşitliği aramaz. Koşu tarihi bu çalışma ortamındadır. 34 sınamanın 34'ü geçti. Başarısız sınama yoktur. Gerçek `/workspace` teslimi yine de yapılmış değildir; bakınız [GUVENLIK_KONTROL.md](GUVENLIK_KONTROL.md).

| No | Sınama | Sonuç |
| --- | --- | --- |
| 01 | Normal dosya arşivleme | GEÇTİ |
| 02 | Symlink arşivleme, dolaylı metin | GEÇTİ |
| 03 | Boş dosya | GEÇTİ |
| 04 | Büyük dosya (200000 bayt) | GEÇTİ |
| 05 | Unicode ad | GEÇTİ |
| 06 | Türkçe karakter | GEÇTİ |
| 07 | Uzun ad | GEÇTİ |
| 08 | Yinelenen arcname | GEÇTİ |
| 09 | Path traversal | GEÇTİ |
| 10 | Symlink üzerinden kaçış | GEÇTİ |
| 11 | İşlem sırasında kaynak değişmesi | GEÇTİ |
| 12 | Metadata değişikliği | GEÇTİ |
| 13 | Yanlış hash | GEÇTİ |
| 14 | Bozuk R5 manifesti | GEÇTİ |
| 15 | Eksik manifest satırı | GEÇTİ |
| 16 | Fazla manifest satırı | GEÇTİ |
| 17 | MK-5 ve A-ek kapsam dışı | GEÇTİ |
| 18 | SYNC_FD inode uyuşmazlığı | GEÇTİ |
| 19 | R2 önceden var | GEÇTİ |
| 20 | Nihai klasör önceden var | GEÇTİ |
| 21 | renameat2 başarısızlığı | GEÇTİ |
| 22 | fsync başarısızlığı (K2) | GEÇTİ |
| 23 | TarFile kapanış hatası | GEÇTİ |
| 24 | Arşivde eksik üye | GEÇTİ |
| 25 | Arşivde fazla üye | GEÇTİ |
| 26 | PAX metadata uyuşmazlığı | GEÇTİ |
| 27 | K5 raporlama hatası | GEÇTİ |
| 28 | R1 açılmaz | GEÇTİ |
| 29 | DRY-RUN kaynak açmaz | GEÇTİ |
| 30 | Onaysız gerçek mod | GEÇTİ |
| 31 | Sürüm kapısı gerçek kökü açmaz | GEÇTİ |
| 32 | K4 belirsiz teslim | GEÇTİ |
| 33 | Manifest sabit boyutu | GEÇTİ |
| 34 | Statik yasaklar | GEÇTİ |
