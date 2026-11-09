# Bilinen sınırlamalar

1. Bu ortam Python 3.12.3 çalıştırır. Kart gerçek mod için 3.13.5 ister. Sürüm farklıysa program koşul 1 ile durur ve kart yollarını açmaz. Sentetik sınamalar bu nedenle izole modda, sürüm eşitliği aranmadan koştu.
2. MK-1..MK-4 dış hash'lerinin tam değerleri kodda yoktur. Gerçek koşu, 64 onaltılık değeri yapılandırma dosyasından almadan hash adımına geçemez. Manifestin 547 baytı ve SHA-256 `a98b9dc8c7742f9588da23e6a670d7f5f138407953d1a7a835b27a1cfaf5ca02` sabittir; gerçek 547 baytlık dosya bu ortamda olmadığı için pozitif sabit eşleşmesi koşturulmadı. Negatif boyut reddi sınandı.
3. Kaynak kökünün üstündeki ata dizinlerde (örneğin `/` ve `/tmp`) karşılaştırma aygıt, inode, tür ve izin ile sınırlıdır. Zaman damgası karşılaştırması kaynak kökü ve altındaki dizinlerde tamdır. Paylaşılan sistem dizinlerinin zaman damgası, kaynak değişmeden de oynayabilir.
4. `tarfile.TarFile` göreli arşiv adına içeride `os.path.abspath` uygular. Uygulama bu mutlak adı açmaz, yazmaz ve doğrulamaz. Veri, R2 tanıtıcısından açılan `fileobj` üzerinden gider.
5. Aynı inode üzerinde boyut ve `mtime_ns` korunarak yapılan eşzamanlı içerik değişikliği, okuma penceresine düşmezse yalnız hash farkıyla yakalanır. Kartın risk (b) ve (j) maddeleri geçerlidir: bütün yarışlar garanti edilmez.
6. Symlink metni envanterden gelir. Uzunluk, güvenli zincirin `st_size` değeriyle karşılaştırılır. Metin kaynaktan bayt olarak okunmaz; raporda dolaylı doğrulama yazar.
7. A-ek ve MK-5 için open, read, stat, lstat, hash, arşiv ve envantere ekleme yoktur. Bu yolların diskte var olup olmadığı da yoklanmaz; yoklamak yasağı delerdi.
8. Dizin listesi yapılmaz. İşlem listesinde olmayan fazla dosya aranmaz. Raporda bu cümle durur.
9. `O_NOATIME` dosya sahibi veya `CAP_FOWNER` ister. İzin yoksa koşul 5 ile durulur; başka açılış yöntemi denenmez.
10. `renameat2` ve `RENAME_NOREPLACE` Linux'a özgüdür. Çağrı yoksa veya başarısızsa koşul 1 ya da 12 ile durulur. `os.rename` kullanılmaz.
11. K1–K4 başarılı olduktan sonra K5 hatası teslim durumunu değiştirmez. Geri alma yoktur.
12. K4 başarısızsa durum `COMMIT_DURABILITY_UNCERTAIN` olur. Program, geçici adın durduğunu veya nihai adın görünmediğini iddia etmez.
13. Arşiv doğrulaması arşivi belleğe alır. Gerçek A grubu yaklaşık 358 MiB olduğundan tepe bellek bu boyuttadır.
14. Envanter ve manifest okuması 32 MiB üstünde durur. Karttaki envanter ve 547 baytlık manifest bu sınırın altındadır.
15. İzole sınama, 2.908 / 2.897 / 216 sabitlerini zorlamaz. Bu sabitler yalnız gerçek modda kapıdır.
16. Platform denemesindeki tek silme, çıktı üstünde az önce oluşturulan `C1_PLATFORM_DENEME_*` adlarıdır. R2, hata halinde silinmez ve nihai ada taşınmaz.
17. Boş grup için de geçerli, üyesiz bir TAR yazılır. Üye kümesi boş listeyle eşittir.
18. Gerçek teslim bu ortamda yapılmamıştır. Sentetik sınamaların geçmesi, `/workspace` üzerindeki C-1 işinin tamamlandığı anlamına gelmez.
