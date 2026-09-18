# Metodoloji — BIST100 Günlük Rapor Sistemi (v2)

> **v2 nedir:** v1 (16 Haz – 17 Eyl 2026, 66 rapor) ölçüldü ve üç aylık aktif yönetimin
> kuruluş portföyüne dokunmamaya göre **13,7 puan sermaye kaybettirdiği** bulundu
> (1.000 TL → 910 TL; dokunulmasaydı 1.047 TL). Kök sebep tek bir mekanizmaydı:
> **kesilen ismin fiyatı defterden düşüyordu**, dolayısıyla "stop disiplini çalışıyor"
> iddiasını çürütecek veri yapısal olarak üretilemiyordu. §4.2, §6.2 ve §7 bunu kapatır.
> Tam kök-neden analizi: `docs/ROOT-CAUSE-v1.md`.

Bu belge, günlük raporların ve performans defterinin (ledger) tek otoriter metodoloji kaynağıdır.
Günlük raporlar buradaki kurallara uyar; kurallar değişecekse ÖNCE bu dosya güncellenir.

## 1. Sistem özeti

Hafta içi her sabah ~10:30 TRT'de (seans içi) bir Claude Code cloud rutini çalışır:
borsa-mcp'den canlı veri çeker, ledger'ı günceller, `scripts/compute_perf.py` ile performansı
deterministik hesaplar, günün raporunu `reports/YYYY-MM-DD-bist100.md` olarak yazar ve
doğrudan `main`'e push eder.

## 2. Dosyalar

| Dosya | İçerik | Kim günceller |
|-------|--------|---------------|
| `data/prices.csv` | Yalnızca **kesinleşmiş** gün-sonu kapanışlar (`date,ticker,close`). Intraday değer GİRİLMEZ. | Rutin, her sabah **dünün** kapanışlarını ekler — **açık + izleme + KAPANMIŞ tüm tickerlar** (§6.2) |
| `data/positions.csv` | Pozisyon defteri: giriş tarihi/kapanışı, stop (initial + current), hedef, durum (open / watchlist / closed) | Rutin, yalnızca giriş/çıkış/stop-değişikliğinde |
| `data/weights.csv` | Günlük örnek portföy ağırlıkları + Δ + değişim tetiği | Rutin, her rapor günü 5 satır ekler |
| `data/triggers.csv` | Aktif izleme tetikleri (rotasyon, overweight, kesim koşulları) | Rutin, her gün durumları günceller (active/fired/expired) |
| `scripts/compute_perf.py` | Deterministik getiri/alfa/maks-düşüş hesabı; markdown üretir | Elle (metodoloji değişirse) |
| `reports/` | Günlük raporlar (insan-okur anlatı katmanı) | Rutin |

## 3. Fiyat çapası kuralları (KRİTİK)

1. **Skorlama = kesinleşmiş kapanış.** Tüm getiri/alfa hesapları `data/prices.csv`'deki
   settled kapanışlarla yapılır (giriş çıpası dahil: `positions.csv.entry_close`).
2. **Intraday yalnızca gösterimdir.** Rutin 10:30'da çalıştığı için o günün oturmuş kapanışı
   henüz yoktur; raporda "bugünün fiyatı" (~15 dk gecikmeli TradingView/borsapy + İş Yatırım
   çapraz teyitli) yalnızca güncel durum, giriş bölgesi ve stop/hedef demirlemesi için kullanılır.
   **Intraday değer alfa hesabına ve prices.csv'ye girmez.**
   Gerekçe: 30 Haz'da XU100 10:32 intraday 14.270 yazılmışken kesin kapanış 14.121 geldi;
   1 Tem'de 10:32 intraday 14.086 iken kesin kapanış 14.350 geldi — intraday çapa alfayı
   ±1-2 puan oynatabiliyor (endeks-print artefaktı).
3. **Her sabah backfill:** rutin, `get_historical_data` ile bir önceki işlem gününün
   kapanışlarını (tüm open + watchlist tickerlar + XU100) `prices.csv`'ye ekler.
4. **XU100 kaynağı `get_historical_data`'dır.** (`get_index_data` XU100 için yalnızca
   metadata döndürüyor — bilinen yapısal limit, her gün yeniden raporlanmaz.)
5. `get_quick_info` BIST'te güvenilmez → kullanılmaz.

## 4. Performans ölçümü

- **Alfa = hisse getirisi − aynı dönem XU100 getirisi** (iki bacak da settled close).
  Mutlak getiri tek başına asla sunulmaz (KURAL 6).
- **MANŞET METRİK = PROGRAM SİCİLİ (v2'de değişti):** açık **ve kapanmış** tüm
  pozisyonların eşit-ağırlık ortalaması. XU100 bacağı isim bazında kendi giriş tarihinden
  bileşiklenir. (`weights.csv`'deki örnek ağırlıklar anlatı katmanıdır.)
  **Gerekçe:** v1'de manşet yalnızca AÇIK pozisyonları kapsıyordu. 17 Eylül'de bu
  **+%4,01** gösterirken 9 kapanmış pozisyonun ortalaması **−2,80 puan**dı ve hiçbir yerde
  toplanmıyordu; gerçek portföy ise −%9 idi. Kapanmış pozisyonu manşetten dışlamak,
  sicili hayatta kalanlarla ölçmektir.
- **İKİNCİ MANŞET — zaman-ağırlıklı seri:** günlük eşit-ağırlık getiri zinciri, her gün
  **o gün fiilen açık olan** pozisyonlarla kurulur. v1 seriyi "bugün hâlâ açık olan"
  isimlerle geriye doğru kuruyordu; 2026-07-20'de bu, portföyü tek isimle (GARAN) temsil
  edip **−%11,34 / −8,43pp** yazıyordu — o gün 5 isim vardı ve gerçek okuma
  **−%0,21 / +2,61pp** idi. Maks. rölatif düşüş de bu seriden gelir.
- **Kapanmış pozisyonlarda İKİ bacak da `exit_date`'te dondurulur** (2026-08-27'de
  düzeltildi; 08-24 METODOLOJİ tetiği). Hisse bacağı `exit_close`'ta durur, XU100 bacağı da
  aynı tarihteki kapanışta durur — böylece realize alfa aynı dönemi ölçer. Eski davranış
  (XU100 bacağının bugüne uzaması) TUPRS'ta 8,4 puanlık sahte sapma üretiyordu.
  `exit_date` prices.csv'de yoksa o tarihten önceki son kapanış kullanılır.
- **Watchlist** isimleri (ör. THYAO) portföye dahil edilmez; karşılaştırma için ayrı satırda izlenir.
- Rapordaki geçmiş performans bölümü `compute_perf.py` çıktısından AYNEN alınır;
  model elle getiri/alfa hesaplamaz.
- Tarihsel not: 16-17 Haz girişleri rapor anında intraday fiyatla yazılmıştı
  (`positions.csv.report_price`); resmi seri giriş gününün kesinleşmiş kapanışını
  (`entry_close`) kullanır. Eski raporlardaki alfalarla ±0,5 puan fark bundandır.

### 4.2 KESİM MALİYETİ ÖLÇÜMÜ (v2 — ZORUNLU, çürütücü kanıt üretir)

Kapanan **her** pozisyon için `compute_perf.py` şunu hesaplar ve rapora yazar:

```
realize alfa      = (çıkış/giriş − 1) − (XU100(çıkış)/XU100(giriş) − 1)
tutsaydık alfa    = (bugün/giriş − 1) − (XU100(bugün)/XU100(giriş) − 1)
kesimin faydası   = realize alfa − tutsaydık alfa      (+ ise kesim DOĞRUYDU)
```

**Bu bölümün varlık sebebi:** v1'de stop disiplini **yanlışlanamaz** bir iddiaydı.
Doğrulayan kanıt her kesimde otomatik birikiyordu (n=8 → "KANIT"), çürüten kanıt ise
hiç birikemiyordu çünkü çıkan ismin fiyatı `prices.csv`'den düşüyordu — 9 kesimin
**6'sı ölçülemez** durumdaydı. Kural, kendisini çürütecek veriyi silen bir defterle
birlikte çalışıyordu.

v2 backfill'i sonrası 9 kesimin 9'u ölçüldü: **net −74,70 puan, doğru kesim 1/9**
(TUPRS tek başına −53,52 puan). Yani v1'in "KANIT n=8" ilan ettiği kural, ölçülebilir
hâle gelir gelmez **tersine** çıktı.

**Bağlayıcı sonuç:** bir kesim kuralı, kesim maliyeti bölümünde **net pozitif** olmadan
"çalışıyor" ilan EDİLEMEZ. Tetiğin ateşlemiş olması kuralın doğruluğu değildir.

## 5. Yapısal veri limitleri (bir kez burada; günlük DÜRÜSTLÜK bölümünde TEKRARLANMAZ)

| Limit | Kabul edilen ikame |
|-------|--------------------|
| Analist hedefi tek besleme (yfinance konsensüsü; ikinci bağımsız feed yok) | Konsensüs dağılımı (düşük/ort/medyan/yüksek + analist sayısı) + hedefin ima ettiği F/K kıyası |
| Çeyreklik YoY kâr büyümesi % temiz çekilemiyor (İş Yatırım bankalarda sınırlı) | **KAP-teyitli EPS beat** yeterli kanıttır (ör. GARAN 28,07 vs 8,55) |
| Net borç/FAVÖK tekil çekilemiyor | **EV/FAVÖK** ikamesi (get_financial_ratios) |
| `get_economic_calendar` sık boş | `get_macro_data` + `get_bond_yields` + son PPK kararı [kaynaklı] |
| `get_news` (KAP/mynet akışı) sistematik olarak **boş** dönüyor — araç hata vermiyor, `successful_count: 1` ile sıfır kalem döndürüyor (2026-09-09'da n=4 eşiğine ulaşıldı: 08-27, 09-04, 09-08, 09-09) | Katalizör bacağının **resmî** kanıtı `get_earnings`'in **KAP bilanço tarihi + EPS beat**'idir. **Sınırı:** bilanço-dışı katalizörler (ihale, kapasite, sözleşme, ortaklık yapısı) bu araç setiyle **tespit edilemez** — bu, açıklanamayan fiyat hareketlerinin kalıcı bir kör noktasıdır ve bir hareketi "tez teyidi" saymamak için gerekçedir |
| `get_evds_data` API anahtarı istiyor (hosted MCP'de yok) | Katalog dışı EVDS verisine güvenilmez |
| **RSI-14 iki araçta AYRIŞIYOR:** `get_technical_analysis` (Wilder) ile `scan_stocks` sistematik olarak farklı okuma döndürüyor; fark isme göre 0,1–17,1 puan (2026-09-11'de n=4 eşiğine ulaşıldı: 09-08, 09-09, 09-10, 09-11 — TUPRS'ta 14,0 / 14,0 / 17,1 / 14,0 puan). Hangisinin doğru olduğu bu araç setiyle çözülemiyor | **Kararda MUHAFAZAKÂR okuma bağlayıcıdır** (bir eşiği geçmemek lehimize ise yüksek okuma, geçmek lehimize ise düşük okuma); raporda **iki değer de** gösterilir. RSI zaten tek başına karar üretmez — §5.2 gereği yalnızca pozisyon boyutlandırmasında uyarı sinyalidir |

Günlük DÜRÜSTLÜK bölümü yalnızca **o güne özgü** gerçek veri boşluklarını yazar.

### 5.1 Değer bacağı: sektör medyanı HEDEF HARİÇ hesaplanır (2026-08-27)

`get_sector_comparison`'un döndürdüğü `sector_median_pe` **hedef hisseyi de içerir**. Hedef,
emsal kümesinin ortanca ismiyse "F/K < sektör medyanı" testi matematiksel olarak dejenere olur
ve hisse ne kadar ucuz olursa olsun testi **asla geçemez**. Bu üç kez gerçekleşti:
BIMAS 16,75 vs 16,75 (08-25), ENJSA 19,09 vs 19,09 (08-25), BIMAS 17,00 vs 17,00 (08-27).

**Kural:** değer bacağı **`F/K < hedef HARİÇ emsal medyanı`** ile ölçülür. Ex-target medyan,
emsal listesinden hedef satırı çıkarılıp kalan F/K'ların ortancası alınarak hesaplanır ve
rapora **açıkça yazılır** (hem dahil hem hariç medyan gösterilir).

### 5.2 Kesim sonrası GERİ ALIM kapısı (2026-08-27)

08-24'te ölçüldü: TUPRS'ta geri alım kapısı "yeni katalizör + **RSI<60 pullback** + settled >291"
diye yazılmıştı; `settled >291` 07-31'de sağlandı ama **RSI<60 bir kez bile gelmedi** çünkü hisse
kesintisiz yükseldi. Kapı fiilen ulaşılamazdı ve 44 puan alfa maliyeti üretti. Güçlü trendde
"RSI düşsün de girelim" kapısı yapısal olarak açılmaz.

**Kural — kesilen bir isme geri giriş yalnızca şu ÜÇ şart birlikte sağlanırsa yapılır:**
1. **SEÇİM KRİTERİ'nin üç bacağı da TAZE veriyle geçer** (reel kâr büyümesi, ex-target medyan
   altı F/K veya EV/FAVÖK, son 3 ayda KAP-teyitli katalizör);
2. **Son kesinleşmiş kapanış ema20'nin ÜSTÜNDE** (trend onarımı — RSI eşiği DEĞİL);
3. **Çıkış tarihinden SONRA gelen, tarihli ve KAP-teyitli YENİ bir katalizör** vardır.

RSI artık geri alım kapısında **eşik değil**; yalnızca pozisyon boyutlandırmasında uyarı
sinyali olarak raporlanır (RSI yüksekse giriş **starter** boyutta yapılır).
Bu kural her isme simetrik uygulanır: 08-27 itibarıyla CCOLA'yı (settled 79,00 < ema20 81,44)
**açmaz**, AEFES'i (büyüme bacağı başarısız) **açmaz**.

## 6. Günlük rutinin ledger görevleri (sırayla, rapor yazılmadan ÖNCE)

1. `get_historical_data` ile dünün kesinleşmiş kapanışlarını çek → `data/prices.csv`'ye ekle:
   **open + watchlist + KAPANMIŞ (§6.2) tüm tickerlar + XU100**; hafta sonu/tatil ertesi
   son işlem günü. Çağrılar **≤3 sembol** halinde bölünür (MCP batch limiti).
2. `python3 scripts/compute_perf.py` çalıştır → çıktıyı raporun "Gerçekleşen Performans"
   bölümüne AYNEN yapıştır. UYARI satırı çıkarsa raporda belirt ve düzelt.
3. Bugünün ağırlıklarını (Δ + tetik gerekçesi) `data/weights.csv`'ye ekle (KURAL 9 anti-whipsaw).
4. `data/triggers.csv` durumlarını güncelle: tetiklenen → fired (+raporda aksiyon),
   geçersizleşen → expired, yeni tetik → yeni satır.
5. Pozisyon değişikliği varsa (giriş/çıkış/stop güncellemesi) `data/positions.csv`'yi güncelle.

### 6.2 ÇIKAN İSİM İZLENMEYE DEVAM EDER (v2 — KÖK SEBEP DÜZELTMESİ)

Bir pozisyon kapandığında ticker `prices.csv` backfill listesinden **ÇIKARILMAZ**.
Kesim tarihinden itibaren **en az 60 işlem günü** boyunca günlük kapanışı çekilmeye
devam eder; ancak bu süre dolduktan sonra listeden düşürülebilir.

**Gerekçe (ölçülmüş):** v1 §6.1 backfill'i "open + watchlist" ile sınırlıydı. Bu tek
satır, 9 kesimin 6'sını kalıcı olarak ölçülemez yaptı (FROTO, TCELL, AEFES, CCOLA,
ANSGR, ENJSA) ve §4.2'deki çürütücü kanıtın **n≥4 eşiğine hiçbir zaman ulaşamamasına**
sebep oldu. Sistem 2026-09-01'de kök sebebi kendisi teşhis etti
(*"Portföy alfa yörüngesi TUPRS'un kesimini birebir izliyor"*), ama kendi kanıt
standardı gereği **"n=3 → HİPOTEZ, üç vaka örüntü değildir"** diye rafa kaldırdı ve
davranış değişmedi. n asla 4 olamazdı, çünkü veriyi defterin kendisi siliyordu.

**İhlal testi:** `compute_perf.py` §D'de "ölçülemedi" satırı varsa bu kural ihlal
edilmiştir ve rapor bunu DÜRÜSTLÜK bölümünde açıkça yazar.

## 6.1 VERİ KESİNTİSİ PROTOKOLÜ (2026-08-28'de resmileşti)

08-21, 08-26 ve 08-28'de rutin **hiçbir** piyasa verisine ulaşamadı. Bu üç günde davranış
yalnızca **presedanla** taşındı; aşağıdaki kural o presedanı bağlayıcı hâle getirir ve
Bölüm 6'nın "ZORUNLU KURAL"ıyla (prices.csv güncellenmeden rapor olusturulamaz) arasındaki
lafzî çelişkiyi kapatır.

**Kesinti tanımı (iki kanal birden kapalı):**
1. `borsamcp-new` araçları oturuma yüklenmedi (araç kaydı = 0) **veya** sunucu bağlanamadı; **ve**
2. doğrudan HTTP yedeği egress politikasınca reddedildi (proxy `connect_rejected` / 403).

**Kesinti günü davranışı — sırayla:**
1. **5 hisse listesi ÜRETİLMEZ.** KURAL 2 (fiyatı doğrulanamayan hisse listeye alınmaz)
   portföy ölçeğinde uygulanır: 100 ismin 100'ünün fiyatı doğrulanamıyorsa hiçbir isim giremez.
   Dünkü listeyi "bugünün önerisi" diye yeniden yazmak KURAL 3 ihlalidir.
2. **LEDGER DONDURULUR.** `prices.csv`'ye satır **eklenmez** (intraday yazmak §3.2 yasağıdır;
   web aramasından fiyat yazmak §6.1.1 yasağıdır). `positions.csv` değişmez.
   `weights.csv`'ye o günün satırları **ölçülemedi** tetiğiyle yazılır — KURAL 9 gereği
   tetik ölçülemiyorsa ağırlık oynatılmaz.
3. **`compute_perf.py` YİNE DE ÇALIŞTIRILIR** ve çıktısı rapora aynen girer. Çıktı mevcut
   en taze settled veriye kadar (as-of) geçerlidir; bu bir tekrar değil **devralmadır** ve
   raporda böyle etiketlenir.
4. **BACKFILL BORCU TETİK OLARAK KAYDEDİLİR** (`triggers.csv`, scope=ALTYAPI): kaç seansın
   kapanışı eksik ve hangi tickerlar. Araçlar döndüğü ilk gün bu borç, o rutinin
   **öncelikli** iş kalemidir.
5. **KESİNTİ RAPORU YAZILIR** (`reports/YYYY-MM-DD-bist100.md`, başlıkta rapor tipi
   ⛔ VERİ KESİNTİSİ olarak). Rapor kesintinin kanıtını (blokolanan hostlar + proxy
   damgası/saati), donmuş ledger'ın durumunu ve çözülemeyen tetikleri listeler.

**Bölüm 6 ZORUNLU KURAL'ının kapsamı:** o kural **öneri üreten** raporu bağlar. Kesinti
raporu öneri üretmediği için kuralın kapsamı dışındadır. Yani kesinti günü rapor yazmak
artık kuralın ihlali değil, **§6.1'in uygulanmasıdır.**

### 6.1.1 Web araması fiyat çapası DEĞİLDİR

08-21'de ölçüldü: "20 Ağustos 2026 XU100 kapanışı" araması **14.458,98** döndürdü; bu değer
08-20'nin değil, `prices.csv`'de zaten kayıtlı **08-19 kapanışının** kopyasıydı — haber akışı
bir günlük gecikmeyle yayınlanan seans özetini "bugün" diye sunuyor. Ledger'a yazılsaydı alfa
serisi sessizce bozulacaktı. **Web araması ne settled kapanış ne intraday çapa olarak kullanılır**;
kesinti günlerinde de kullanılmaz.

## 7. Geçmiş analiz derinliği

- **Her gün:** ledger (4 CSV) + **yalnızca dünkü rapor** okunur. Tarihsel Öğrenimler bölümü
  dünkü rapordan devralınır ve günün kanıtıyla güncellenir.
- **Ayın ilk iş günü:** tüm `reports/` arşivi baştan okunur (derin örüntü çıkarımı,
  öğrenimlerin sıfırdan doğrulanması). Diğer günler arşiv taraması yapılmaz (maliyet O(n²) büyüyordu).
- Örneklem küçükken (≲30 seans) örüntüler "kanıt" değil "HİPOTEZ" olarak işaretlenir.

### 7.1 SİMETRİK KANIT STANDARDI (v2 — kök sebep düzeltmesi)

v1'in n≥4 eşiği **tek yönlü** çalışıyordu: bir kuralı DOĞRULAYAN vakalar otomatik
birikiyor (her ateşleyen tetik bir vaka), ÇÜRÜTEN vakalar ise ölçülemediği için
n=2–3'te tavanlanıyordu. Sonuç: sistem yalnızca **stop EKLEYEN** kurallar öğrenebildi,
stop KALDIRAN hiçbir kural öğrenemedi. 211 tetiğin 63'ü ateşledi ve 09-04'e kadar
ateşleyen **her** ön-kayıt bir kesimdi.

**Bağlayıcı kurallar:**
1. Bir öğrenimin n'i sayılırken **ölçülemeyen vakalar da yazılır**: "n=3 ölçüldü,
   6 vaka ÖLÇÜLEMEDİ". Ölçülemeyen vaka kuralın lehine sayılmaz.
2. Bir kuralın doğrulayıcı n'i, aynı kuralın **çürütücü kanıt kanalı açık değilken**
   ilerletilemez. Kanal kapalıysa öğrenim "ÖLÇÜLEMİYOR" etiketiyle dondurulur.
3. Karşıt kanıt eşiği, destekleyen kanıt eşiğinden **yüksek olamaz**. Aynı n aynı ağırlık.
4. Bir öğrenim HİPOTEZ'den KANIT'a yalnızca §4.2 ölçümüyle **birlikte** terfi eder.

### 7.2 ZAMAN UFKU İLE TETİK UFKU UYUMU (v2)

v1'de her tezin ufku "orta (6–24 ay)" yazılırken gerçekleşen **medyan tutma süresi
20 seans**tı; tetiklerin tamamı 1–2 seanslık sinyallere (MACD işareti, RSI eşiği,
ema20, "iki ardışık kapanış") bağlıydı. 62 rapor gününde **377 puan** ağırlık oynatıldı
(portföyün 3,8 katı). 6–24 aylık bir tez 1–2 seanslık tetikle yönetilirse gürültüyle
sonlandırılır.

**Kural:** bir pozisyonun kesim/trim tetiği, tezin ufkuyla **aynı mertebeden** olmalıdır.
Orta-vadeli (6–24 ay) tezde tek-seans kapanışı bir kesim tetiği OLAMAZ; kesim en az
**üç ardışık kesinleşmiş kapanış** veya **tezin bir bacağının taze veriyle çökmesi**
gerektirir. Hard stop (sermaye koruma) bunun istisnasıdır ve yalnızca girişten
%−15 veya daha derin bir seviyede tanımlanabilir.

## 8. Tarihçe notları

- 2026-06-20 ve 2026-06-21 raporları eski günlük-cron döneminden kalmadır (Cmt/Paz, seans yok);
  `prices.csv`'de bu tarihler yoktur. 25 Haz'dan beri cron yalnızca hafta içi çalışır.
- 2026-06-16 → 07-01 raporlarındaki performans tabloları intraday çapalıydı; 2026-07-02
  itibarıyla resmi seri bu ledger'dır (Bölüm 4'teki tarihsel not geçerli).
