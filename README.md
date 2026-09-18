# finance-agent v2 — Günlük BIST100 Rapor Sistemi

Hafta içi her sabah ~10:30 TRT'de çalışan bir Claude Code cloud rutini, borsa-mcp üzerinden
canlı BIST verisi çekip günün yatırım komitesi raporunu üretir ve doğrudan `main`'e push eder.
Her rapor, önceki önerilerin gerçekleşen performansını **XU100'e göre rölatif (alfa)** olarak
deterministik biçimde ölçer.

## v2 neden var

v1 (16 Haz – 17 Eyl 2026, 66 rapor) ölçüldü. 1.000 TL ile raporlar birebir izlenseydi
sonuç **910 TL** olurdu; kuruluş portföyüne hiç dokunulmasaydı **1.047 TL**. Yani üç aylık
aktif yönetim sermayenin **%13,7'sini yok etti** ve manşet metrik bunu göstermiyordu
(rapor +%4,01 alfa yazarken gerçek portföy −%9,01'di).

**Kök sebep:** kesilen ismin fiyatı defterden düşüyordu. Bu yüzden "stop disiplini çalışıyor"
iddiasını çürütecek veri yapısal olarak üretilemiyordu — 9 kesimin 6'sı ölçülemez durumdaydı.
Sistem kök sebebi 1 Eylül'de kendisi teşhis etti, kendi kanıt standardı gereği
"n=3 → HİPOTEZ" diye rafa kaldırdı ve n asla 4 olamadı.

Geriye dönük backfill sonrası 9 kesimin 9'u ölçüldü: **net −74,70 puan, doğru kesim 1/9.**

Tam analiz: [`docs/ROOT-CAUSE-v1.md`](docs/ROOT-CAUSE-v1.md)

## v2'de değişen sekiz şey

| # | Düzeltme | Nerede |
|---|---|---|
| 1 | Çıkan ismin fiyatı **60 seans** izlenmeye devam eder | METHODOLOGY §6.2 |
| 2 | Her kesim için **kesim maliyeti** hesaplanır ve rapora yazılır | §4.2 · `compute_perf.py` §D |
| 3 | Manşet metrik **açık + realize** tüm pozisyonları kapsar | §4 |
| 4 | Günlük seri **survivorship-free** | §4 |
| 5 | **Simetrik kanıt standardı** — ölçülemeyen vaka kural lehine sayılmaz | §7.1 · KURAL 10 |
| 6 | **Tetik ufku ile tez ufku uyumu** — tek seans kesim tetiği olamaz | §7.2 · KURAL 9(b) |
| 7 | **Tetik bütçesi** — rutin başına en fazla 3 yeni tetik | KURAL 9(c) |
| 8 | KURAL 1–10 artık **repoda** (v1'de yalnızca rutin prompt'undaydı) | `routine/PROMPT.md` |

## Yapı

```
reports/                 Günlük raporlar (YYYY-MM-DD-bist100.md) — anlatı katmanı
data/prices.csv          Kesinleşmiş gün-sonu kapanışlar (açık + izleme + KAPANMIŞ isimler)
data/positions.csv       Pozisyon defteri (giriş/stop/hedef/durum)
data/weights.csv         Günlük örnek portföy ağırlıkları + değişim tetikleri
data/triggers.csv        Aktif izleme tetikleri
scripts/compute_perf.py  Deterministik getiri/alfa/kesim-maliyeti hesabı
routine/PROMPT.md        Cloud rutinin otoriter prompt kopyası (KURAL 1–10)
METHODOLOGY.md           Tek otoriter metodoloji
docs/ROOT-CAUSE-v1.md    v1 kök neden analizi
```

## Performans hesabı

```
python3 scripts/compute_perf.py
```

Dört bölüm üretir: **A)** açık pozisyonlar · **B)** realize · **C)** program sicili (manşet)
· **D)** kesim maliyeti. Raporda dördü de AYNEN yer alır.

Alfa hesabının iki bacağı da (hisse + XU100) **kesinleşmiş kapanış** kullanır; seans içi
değerler yalnızca raporun "bugünkü fiyat" gösteriminde yer alır. Ayrıntı: [METHODOLOGY.md](METHODOLOGY.md).

## Veri kaynakları

borsa-mcp (yfinance + borsapy/TradingView + İş Yatırım), KAP/Mynet haber akışı,
TCMB makro verileri. Kaynak-tazelik haritası ve yapısal limitler METHODOLOGY §5'te.

> **Bu repo ve içerdiği raporlar yatırım tavsiyesi değildir.** Veriler kamuya açık
> kaynaklardan derlenmiştir ve hata içerebilir. Geçmiş performans gelecekteki getiriyi
> garanti etmez. v1 ölçümü, bu sistemin üç ayda endeksin altında kaldığını göstermektedir.
