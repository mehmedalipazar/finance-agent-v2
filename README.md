# finance-agent v2 — Günlük BIST100 Analiz Ajanı

[![ledger](https://github.com/mehmedalipazar/finance-agent-v2/actions/workflows/ledger.yml/badge.svg)](https://github.com/mehmedalipazar/finance-agent-v2/actions/workflows/ledger.yml)

Hafta içi her sabah 10:30'da (TRT) çalışan otonom bir Claude Code rutini. BIST100'ü tarar,
günün 5 hisselik yatırım komitesi raporunu yazar ve önceki önerilerinin gerçekleşen
performansını **XU100'e göre (alfa)** ölçer. İnsan müdahalesi yoktur; rutin sonucu doğrudan
`main`'e push eder.

## Nasıl çalışır

1. **Veri** — borsa-mcp üzerinden kesinleşmiş kapanışlar, temel veriler ve teknik göstergeler çekilir.
2. **Defter** — fiyatlar, pozisyonlar, ağırlıklar ve izleme tetikleri `data/` altındaki dört CSV'de tutulur.
3. **Ölçüm** — getiri ve alfa, model tarafından değil `scripts/compute_perf.py` tarafından deterministik hesaplanır; çıktı rapora aynen girer.
4. **Denetim** — `scripts/validate_ledger.py` defter kurallarını commit'ten önce, GitHub Actions ise her push'ta denetler. Hata varsa commit edilmez.
5. **Rapor** — `reports/YYYY-MM-DD-bist100.md`.

## v2 neden var

v1 üç ay çalıştı (66 rapor) ve ölçüldü: raporlar birebir izlenseydi 1.000 TL **910 TL** olurdu;
ilk portföye hiç dokunulmasaydı **1.047 TL**. Manşet metrik bunu göstermiyordu, çünkü yalnızca
açık pozisyonları sayıyordu. Kök sebep: satılan hissenin fiyatı defterden düşüyor, dolayısıyla
"stop kuralı işe yarıyor" iddiası hiçbir zaman sınanamıyordu. Eksik fiyatlar geriye dönük
tamamlandığında 9 kesimin 8'inin alfa kaybettirdiği görüldü.
Ayrıntı: [`docs/ROOT-CAUSE-v1.md`](docs/ROOT-CAUSE-v1.md)

## İyileştirmeler

| Alan | v1 | v2 |
|---|---|---|
| Satılan hisse | Fiyatı izlenmiyordu | 60 seans izlenir; her kesimin maliyeti ölçülür |
| Manşet metrik | Yalnızca açık pozisyonlar | Açık + kapanmış tüm pozisyonlar |
| Paranın karşılığı | Elle, bir kez hesaplandı | 1.000 TL model portföyü her gün hesaplanır |
| Kanıt standardı | Ölçülemeyen vaka kuralın lehine sayılıyordu | Simetrik: ölçülemeyen vaka sayılmaz |
| Stop tetikleri | 6–24 aylık tez, tek seanslık tetik | Tetik ufku tez ufkuyla uyumlu; günde en fazla 3 yeni tetik |
| Kurallar | Yalnızca metin | Mekanik denetim + 27 test + CI |
| Günlük okuma yükü | ~390 KB CSV | ~25 KB özet (`ledger_brief.py`), %94 azalma |
| Veri kesintisi | Defter donuyordu | İkinci kanal (`fetch_closes.py`); defter bağımsız kaynakla 660/660 doğrulandı |

## Repo yapısı

```
reports/      Günlük raporlar
data/         Defter: prices · positions · weights · triggers (CSV)
scripts/      compute_perf · ledger_brief · validate_ledger · fetch_closes
tests/        Script testleri
docs/         v1 kök neden analizi
METHODOLOGY.md   Tek otoriter metodoloji
```

## Kullanım

Yalnızca Python 3 standart kütüphanesi gerekir.

```
python3 scripts/compute_perf.py              # performans: açık · realize · manşet · kesim maliyeti · model portföy
python3 scripts/ledger_brief.py              # günün defter özeti
python3 scripts/validate_ledger.py           # defter kuralları (HATA = 0 olmalı)
python3 scripts/fetch_closes.py --verify 10  # son 10 seansı bağımsız kaynakla karşılaştır
python3 -m unittest discover -s tests        # testler
```

Güncel performans rakamları her raporun "Gerçekleşen Performans" bölümündedir.
Yöntemin tamamı: [METHODOLOGY.md](METHODOLOGY.md)

---

**Yatırım tavsiyesi değildir.** Veriler kamuya açık kaynaklardan derlenmiştir ve hata
içerebilir; geçmiş performans geleceği garanti etmez. v1 ölçümü, sistemin ilk üç ayda
endeksin altında kaldığını göstermiştir.
