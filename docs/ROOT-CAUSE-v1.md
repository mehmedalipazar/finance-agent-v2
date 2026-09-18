# v1 Kök Neden Analizi — neden 3 ayda sermaye kaybettik

**Kapsam:** 2026-06-16 → 2026-09-17, 66 rapor, 62 ağırlık günü, 14 pozisyon, 211 tetik.
**Yöntem:** `data/*.csv` üzerinden bağımsız backtest + 66 raporun tam okunması.
Tüm sayılar `data/prices.csv`'den yeniden üretilebilir.

---

## 1. Ölçüm: müdahale sermayeyi yok etti

1.000 TL ile ilk rapordan itibaren yalnızca raporların ilan ettiği ağırlıklar izlenseydi
(infaz = rapor gününün kesinleşmiş kapanışı, METHODOLOGY §4 konvansiyonu):

| Senaryo | 2026-09-16 | Getiri | Alfa |
|---|---:|---:|---:|
| **16 Haziran portföyü — hiç dokunulmasa** | **1.047 TL** | +%4,74 | **+14,20 pp** |
| Bir isim girdiyse bir daha çıkarılmasa | 990 TL | −%0,93 | +8,53 pp |
| **Gerçekte yapılan (70 işlem)** | **910 TL** | **−%9,01** | +0,45 pp |
| XU100 al-tut | 905 TL | −%9,46 | 0,00 |
| Nakitte dursa (%40 y.) | 1.089 TL | +%8,85 | +18,31 pp |

Kuruluş portföyünün FROTO/TCELL bacakları v1'de çıkıştan sonra izlenmediği için üç
varsayımla test edildi: dondurulmuş **1.047 TL**, XU100 gibi hareket etmiş **1.030 TL**,
XU100'den 5 puan kötü **1.012 TL**. Sonuç her varsayımda aynı yönde.

**Her karşı-senaryo aynı sırada: müdahale ne kadar azsa sonuç o kadar iyi.**

Manşet metrik bunu göstermiyordu. 17 Eylül raporu **+%4,01 kümülatif alfa** yazıyordu;
o rakam yalnızca **o gün açık olan 4 ismi** kendi giriş tarihlerinden ölçüyordu.
Gerçek portföy aynı anda −%9,01'di.

---

## 2. Katman 1 — tek kazanan satıldı, sekiz kaybeden taşındı

Kapanan 9 pozisyonun **1'i kârda** (TUPRS +%27,77, 31 seans), **8'i zararda**
(ortalama −%9,56, ortalama 20 seans).

TUPRS tek başına kuruluş portföyünün +%4,74'ünün **+15,65 puanını** üretiyordu.
30 Temmuz'da 288,00'den trailing stop ile kesildi. **Sonraki 15 seansta hisse bir kez
bile 288'in altını görmedi** — dip 380,75, tepe 416,75. 27 Ağustos'ta 380,75'ten geri
alındı; aradaki fark **22,56 puan** kaçırılmış rölatif getiri.

Trailing stop o pozisyonda sekiz kez yükseltilmişti:
`195 → 200 → 220 → 235 → 240 → 268 → 285 → 287 → 291`. Her yükseltme yükselen hissenin
etrafındaki bandı daralttı; sonunda normal bir geri çekilme bandı deldi.

---

## 3. Katman 2 — kural seti tek yönlü bir cırcır

Satış kuralları sayısal, tarihli, ön-kayıtlı ve koşulsuz. Alım kuralları "üç bacak da
taze veriyle geçsin" diyor ve pratikte açılmıyor.

- **211 tetik açıldı, 63'ü ateşledi.** 2026-09-04'e kadar ateşleyenlerin **hepsi kesimdi**;
  o günün raporu bunu kendisi yazıyor: *"Programın tarihinde ilk kez sayısal ve tarihli
  bir GİRİŞ eşiği ateşledi… bugüne kadar ateşleyen her ön-kayıt bir KESİMdi."*
- Tetik üretimi: Haziran 3 → Temmuz 10 → **Ağustos 92 → Eylül 106**.
- Nakit %0 → %45; raporun kendi ifadesiyle *"bir piyasa görüşü değil, iki mekanik
  kesimin sonucu."*
- Nakit **yanlış zamanda** yüksekti: Haz–Tem ortalaması %0–2 (piyasa düşerken),
  Eylül %35–45 (hasardan sonra).

---

## 4. Katman 3 — 6–24 aylık tez, 1–2 seanslık tetikle yönetildi

Her tezin altında "Zaman ufku: Orta (6–24 ay)" yazıyor. Gerçekleşen **medyan tutma
süresi 20 seans**. Tetiklerin tamamı kısa vadeli: MACD histogram işareti, RSI eşiği,
settled vs ema20, "iki ardışık kapanış". 62 rapor gününde **377 puanlık ağırlık
oynatıldı — portföyün 3,8 katı.**

Haziran'da 13 günde 35 ağırlık değişikliği. TCELL dört günde %22 → %18 → %20 → %16:
06-18 *"2 seans gerçekleşmediği için kırpıldı"*, 06-19 *"bugünkü +%3,48 toparlanmayla
geri alındı"* (sabah 10:04 fiyatıyla), 06-20 *"Cuma kapanışı erken-seans toparlanmayı
geri verdi → en düşük ağırlığa kırpıldı"*.

20 Haziran raporu hatayı adıyla koyuyor: *"EN ÖNEMLİ HATA KALIBI — tek-fiyat-noktası
üzerine güven kademesi oynatmak gürültü kovalamaktır."* Sonra üç ay boyunca aynı şey
daha sofistike bir kelime dağarcığıyla tekrarlandı.

---

## 5. KÖK SEBEP — öğrenme döngüsü kendini mühürlüyordu

METHODOLOGY §7 bir kanıt standardı koyuyor: **n≥4 ve tutarlı işaret = KANIT**, altı HİPOTEZ.

**Doğrulayan kanıt otomatik birikiyordu.** Her stop ateşlediğinde bir vaka eklenir:
17 Eylül raporu *"ÖN-KAYITLI STOP DİSİPLİNİ ÇALIŞIYOR. [KANIT, n=8]"* diyor.

**Çürüten kanıt birikemiyordu**, çünkü v1 §6.1 backfill'i "open + watchlist" ile
sınırlıydı; **çıkan ismin fiyatı defterden düşüyordu.** 9 kesimin 6'sı
(FROTO, TCELL, AEFES, CCOLA, ANSGR, ENJSA) kalıcı olarak **ölçülemez**di.

Sistem kök sebebi **kendisi buldu**. 28 Ağustos, 31 Ağustos ve 1 Eylül raporlarının
üçünde de aynı satır var:

> *"Stop disiplininin ayırt edici değişkeni FİYAT değil TEMEL YÖN — TUPRS kesimi
> 22,03pp alfa maliyeti; FROTO kesimi 4,16pp alfa korudu. **n=3 → HÂLÂ HİPOTEZ.
> Üç vaka örüntü değildir.**"*

Ve 1 Eylül teşhisi tamamlıyor:

> *"Portföy alfa yörüngesi TUPRS'un kesimini birebir izliyor: zirve +%2,65 (07-20) →
> TUPRS 07-30'da trailing stop ile kesildi → +%0,31 → −%3,24 → −%6,85 → −%4,35.
> **Kesimden sonra portföy alfası bir daha pozitif olmadı.**"*

**Kök sebep:** aşırı-uydurmayı önleyen kural (n≥4), yalnızca kendini doğrulayan veriyi
saklayan bir defterle birleşti. Sistem **yalnızca stop ekleyen kuralları öğrenebiliyor,
stop kaldıran kuralları asla öğrenemiyordu.** Teşhis raporda duruyordu, "HİPOTEZ"
etiketiyle, ve n asla 4 olamayacaktı çünkü veriyi defterin kendisi siliyordu.

### Düzeltme sonrası ölçüm

v2 backfill'i (196 satır, mevcut 464 satırla **sıfır çatışma**) 9 kesimin 9'unu
ölçülebilir yaptı:

| | v1 (ölçülebilen) | v2 (tamamı) |
|---|---|---|
| Ölçülebilir kesim | 3 / 9 | **9 / 9** |
| Net kesim etkisi | — | **−74,70 pp** |
| Doğru kesim | — | **1 / 9** |

v1'in "KANIT n=8" ilan ettiği kural, ölçülebilir hâle gelir gelmez **tersine** çıktı.

---

## 6. İkincil katkılar

- **Değer bacağı düşen hisseyi ödüllendiriyor.** "F/K < emsal medyanı" testi hisse
  düştükçe daha kolay geçilir. Bu yüzden her kesim raporunda aynı cümle var:
  *"kesim tez yanlışlanması DEĞİL fiyat/stop disiplinidir"* (CCOLA, ANSGR, ISCTR).
  Temel bacaklar ile teknik bacaklar yapı gereği zıt yöne bakıyor ve sayısal tetiği
  olan tek bacak teknik olduğu için **her zaman teknik kazanıyor.**
- **Yoğunlaşma sorgulanmadı.** GARAN 62 günün 62'sinde portföyde, ortalama %23,2
  ağırlık, dönem boyunca negatif katkı. Stop 118'e hiç değmediği için hiçbir tetik
  onu sorgulamadı.
- **KURAL 1–9 repoda hiç tanımlı değildi** — yalnızca cloud rutin prompt'unda.
  Repo kendi kurallarına karşı denetlenemiyordu. v2'de `routine/PROMPT.md` repoda.
- **Giriş çapası önemsiz:** 14 girişin 3'ü aleyhte, ortalama sapma +%0,11.

---

## 7. v2'de ne değişti

| # | Düzeltme | Nerede |
|---|---|---|
| 1 | Çıkan ismin fiyatı **60 seans** izlenmeye devam eder | METHODOLOGY §6.2 |
| 2 | Her kesim için **kesim maliyeti** hesaplanır ve rapora yazılır | §4.2 + `compute_perf.py` §D |
| 3 | Manşet metrik **açık + realize** tüm pozisyonları kapsar | §4 |
| 4 | Günlük seri **survivorship-free** (o gün fiilen açık pozisyonlar) | §4 |
| 5 | **Simetrik kanıt standardı** — ölçülemeyen vaka kural lehine sayılmaz | §7.1 |
| 6 | **Tetik ufku ile tez ufku uyumu** — tek seans kesim tetiği olamaz | §7.2 |
| 7 | KURAL 1–9 repoda | `routine/PROMPT.md` |
| 8 | Geriye dönük backfill: 196 satır, 0 çatışma, 0 delik | `data/prices.csv` |
