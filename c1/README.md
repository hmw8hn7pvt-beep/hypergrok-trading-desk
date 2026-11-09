# C-1 arşivleme ve mühür ayrımı

Araştırma dosyalarını kaynaklara yazmadan üç TAR arşivine alır ve arşivleri ayrı bir teslim adımıyla mühürler. Bu dizin bir borsa yazıcısı değildir; emir, imza veya cüzdan işlemi yapmaz.

Bu çalışma [HyperGrok Trading Desk](https://github.com/galleonlabs/hypergrok-trading-desk) deposunun içindedir ve [MIT lisansı](../LICENSE) altındadır.

Kurallar: [C1_KART_r11.md](C1_KART_r11.md). Güvenlik listesi: [GUVENLIK_KONTROL.md](GUVENLIK_KONTROL.md). Sınırlar: [BILINEN_SINIRLAMALAR.md](BILINEN_SINIRLAMALAR.md). Son koşu: [TEST_SONUCLARI.md](TEST_SONUCLARI.md).

## Modlar

Varsayılan **DRY-RUN** dir. Yapılandırma okunabilir; kaynak ağacı, envanter ve çıktı kökü açılmaz.

**İzole** mod yalnız geçici bir sınama kökünde, sentetik dosyalarla çalışır. `/workspace` ve `/home/box` bu modda reddedilir.

**Gerçek** mod iki kapı ister: `--gercek` ve `--onay "ONAY C-1"`. Biri eksikse hiçbir kaynak açılmaz. Kart yolları, 2.908 / 2.897 sayıları, manifestin 547 baytı ve sabit SHA-256 değeri bu modda zorunludur. Python `3.13.5` değilse gerçek mod, dizin açmadan koşul 1 ile durur. MK-1..MK-4 hash'leri kodda yoktur; yapılandırma dosyasından okunur. MK-5 kaynağın içinde olamaz. Çıktı üstünün altında, R1, R2 ve nihai klasörün dışında durabilir; bu yol yine açılmaz. Gerçek ek `/home/box/agent-data/...` altındadır.

Yapılandırma dosyası yasak köklerin içinde olamaz. Örnek iskelet: `ornek_yapilandirma.json`. Örnekteki hash alanları yer tutucudur.

## Modüller

| Modül | Görevi |
| --- | --- |
| `main.py` | Komut satırı, kapılar ve 0a–K5 akışı |
| `config.py` | Mod, kart sabitleri, JSON yükleme; dosya açmadan önce onay kapısı |
| `errors.py` | Kod, aşama, açıklama, beklenen ve gerçek değer |
| `validation.py` | YG metin kuralları ve disk üst sınırı |
| `secure_fs.py` | openat, O_NOFOLLOW, O_PATH, O_NOATIME, SYNC_FD, renameat2 |
| `inventory.py` | C1 CSV okuma, A-ek ayırma, işlem listesi |
| `metadata.py` | M1 kayıt, M2 karşılaştırma, S-A uzunluk kontrolü |
| `hashing.py` | SHA-256; symlink özeti dolaylıdır |
| `r5_validation.py` | Beş satırlık manifest, MK-1..MK-4 hash, MK-5 yalnız metin |
| `archive_writer.py` | Üç PAX arşivi, göreli ad, fileobj |
| `archive_validator.py` | Üye, tür, PAX ve içerik doğrulaması; diske çıkarmaz |
| `commit.py` | K1–K5. K4 başarısızlığı durumu belirsiz bırakır |
| `reporting.py` | RAPOR.txt ve TESLIM_BILDIRIMI.txt |

## Sınama

```bash
python3 -m unittest discover -s c1/tests -t . -v
```

Sınamalar `tempfile` ile kurulan dizinlerde sentetik dosya kullanır. Gerçek envanter okunmaz.

## Gerçek çalıştırma

Bu komut ancak kullanıcı ayrıca `ONAY C-1` verdiğinde ve yapılandırma gerçek hash'leri taşıdığında anlamlıdır. Bu teslimatta çalıştırılmamıştır.

```bash
python3 -m c1.main --yapilandirma /guvenli/c1_gercek.json --gercek --onay "ONAY C-1"
```

Bu ortamdaki Python 3.12.3 olduğu için aynı komut, kart sürümü 3.13.5 olmadığı gerekçesiyle koşul 1'de durur. Durma, `/workspace` ve `/home/box` açılmadan olur. Ayrıntı [GUVENLIK_KONTROL.md](GUVENLIK_KONTROL.md) içindedir.

Kuru bakış:

```bash
python3 -m c1.main --yapilandirma c1/ornek_yapilandirma.json
```
