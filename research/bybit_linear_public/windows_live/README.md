# Windows üzerinde sonlu kamu fiyat kontrolü

Bu klasör kasıtlı olarak küçüktür. Depo gerekmez. Kurulum, arka plan hizmeti veya otomatik başlangıç yoktur. Emir, hesap, strateji veya performans yoktur.

Python bu paketi kurmaz. Önce siz Python 3.11 veya daha yenisini kurun. Bu geliştirme CPython 3.12.3 ile sınandı. Üçüncü taraf paket yoktur. `pip install` çalıştırmayın.

Ağ önkoşulu: `wss://stream.bybit.com/v5/public/linear` adresine giden kamu WebSocket. Windows REST kamu okumasının HTTP 200 döndüğü gözlendi. WebSocket canlı erişim bu pakette kanıtlanmadı. Başka host, testnet, proxy veya tünel kullanmayın. Bağlantı kapanırsa durun.

## Başlatma

Zip'i açın. Bu dosyanın bulunduğu klasörde:

```text
py -3 --version
py -3 live_check.py --confirm-public-network --seconds 90 --receive-stale-ms 5000 --exchange-stale-ms 15000 --exchange-future-skew-ms 2000 --event-log live-health.jsonl
```

`--seconds` 60, 90 veya 120 olabilir. Aralık dışındaki değer ve bayraksız çağrı soket açmaz. Süreç 90 saniye sonra kendiliğinden durur.

## Durdurma

Pencere açıkken Ctrl+C. Süreç fiyatları gizler ve çıkar. Görev zamanlayıcıya eklemeyin. Arka planda bırakmayın.

## Tablo

Bir sembolde cross sequence geri giderse eski kare uygulanmaz ve son kabul edilen kitap durur. Aynı yönde üç kare gelirse yalnız o sembol için kamu unsubscribe ve subscribe gönderilir. Üç denemeden sonra soket, mevcut yeniden bağlanma sınırı içinde bir kez yenilenir. Diğer sembollerin kitapları karıştırılmaz. Alım yaşı, sürecin monoton saatine göredir. Borsa yaşı, bilgisayarın Unix duvar saati eksi Bybit `ts` değeridir. Bu iki saat birbirine çıkarılmaz. `--exchange-stale-ms` (varsayılan 15000) aşılmış veya borsa damgası duvar saatinden `--exchange-future-skew-ms` (varsayılan 2000) fazla ilerideyse fiyat `UNAVAILABLE` kalır. Program Windows saatini değiştirmez. `AWAITING_ACK` abonelik onayı değildir. `AWAITING_SNAPSHOT` onay vardır, fiyat yoktur. `IDLE` onaydan sonra veri gelmemiştir. `STALE`, `DISCONNECTED` ve `HEARTBEAT_TIMEOUT` eski fiyatı güncel diye göstermez. `PARTIAL` bazı semboller tazedir. SOLUSDT ve XRPUSDT satırında `conditional` yazar. Canlı görünmeleri tarihsel araştırma uygunluğu değildir.

`live-health.jsonl` yalnız bu klasörde, durum değişimlerini tutar. Dışarı mesaj göndermez.

Çıkış kodu 0, sürecin durduğunu söyler. Fiyatların kullanılabilir olduğunu söylemez. Bunu tablo söyler.
