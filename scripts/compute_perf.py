#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance-agent v2 — deterministik performans/alfa hesabı.

v1'e göre DÖRT DÜZELTME (gerekçeleri METHODOLOGY.md §4):
  1. PROGRAM SİCİLİ: manşet metrik artık açık + KAPANMIŞ tüm pozisyonları kapsar.
     v1 yalnızca açık pozisyonları topluyordu; kapanmış 9 pozisyon hiçbir yerde
     toplanmıyordu ve manşet alfa gerçek portföyü temsil etmiyordu.
  2. SURVIVORSHIP BIAS: günlük seri artık O GÜN FİİLEN AÇIK olan pozisyonlardan
     kurulur. v1 seriyi "bugün hâlâ açık olan" isimlerle geriye doğru kuruyordu;
     bu 2026-07-20'de portföyü tek isimle (GARAN) temsil edip −%11,34 / −8,43pp
     gibi hiç yaşanmamış bir dip üretiyordu (gerçek: −%0,21 / +2,61pp).
  3. KESİM MALİYETİ ÖLÇÜMÜ: her kapanmış pozisyon için "tutsaydık ne olurdu"
     hesaplanır. Bu, stop disiplinini ÇÜRÜTEBİLİR kanıt üretir — v1'de bu veri
     defterden siliniyordu (çıkan ismin fiyatı izlenmiyordu), dolayısıyla
     "stop disiplini çalışıyor" iddiası yapısal olarak yanlışlanamazdı.
  4. Açık pozisyon yokken çökmez; kapanmış ile izleme (watchlist) ayrı etiketlenir.

2026-09-21 düzeltmeleri (METHODOLOGY §4.2 / §4.3):
  5. İKİ BACAK AYNI TARİHTE DURUR: hisse bacağı hangi kapanışta duruyorsa XU100
     bacağı da o tarihte durur. Eskiden "tutsaydık" bacağında hisse son izlenen
     kapanışta, XU100 ise as-of'ta duruyordu; 60 seanslık izleme penceresi dolan
     isimlerde bu fark her gün büyüyen sahte bir alfa üretecekti.
  6. "ÖLÇÜLEMEDİ" AYRIMI: çıkışı as-of seansında olan kesim henüz ölçülemez
     (çıkış sonrası seans yok) — bu §6.2 ihlali DEĞİLDİR. İhlal, çıkıştan sonra
     seans geçtiği hâlde fiyatın izlenmemiş olmasıdır. Eski sürüm ikisini de
     "ihlal" diye raporluyordu.
  7. MODEL PORTFÖY (§E): weights.csv'de ilan edilen ağırlıklar (nakit dahil)
     birebir izlenseydi 1.000 TL ne olurdu. v1 kök neden analizinin elle yapılan
     ölçümü (1.000 → 910 TL) artık her gün deterministik üretilir.

Girdi:  data/prices.csv (yalnızca KESİNLEŞMİŞ kapanışlar) · data/positions.csv · data/weights.csv
Çıktı:  stdout'a markdown — raporun "Gerçekleşen Performans" bölümüne AYNEN yapıştırılır.

Kullanım: python3 scripts/compute_perf.py [--root DİZİN]
"""
import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = "XU100"
CASH = "CASH"
STALE_DAYS = 5
TRACK_SESSIONS = 60  # METHODOLOGY §6.2: çıkan isim en az 60 seans izlenir

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def tr_num(x, nd=2):
    s = f"{x:,.{nd}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def tr_pct(x, nd=2):
    return ("+%" if x >= 0 else "−%") + tr_num(abs(x), nd)


def tr_pp(x, nd=2):
    return ("+" if x >= 0 else "−") + tr_num(abs(x), nd) + "pp"


def load_prices(root):
    prices = {}
    with open(root / "data" / "prices.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            prices.setdefault(row["ticker"].strip(), {})[row["date"].strip()] = float(row["close"])
    return prices


def load_positions(root):
    with open(root / "data" / "positions.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_weights(root):
    path = root / "data" / "weights.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def on_or_before(series, d):
    """series içinde d ve öncesindeki son tarih (yoksa None)."""
    ds = [x for x in series if x <= d]
    return max(ds) if ds else None


def model_portfolio(prices, bench, all_dates, weight_rows, warnings):
    """weights.csv'de ilan edilen ağırlıklar birebir izlenseydi (METHODOLOGY §4.3).

    Konvansiyon (v1 kök neden analizindeki "Senaryo B" ile aynı):
      - İnfaz = rapor gününün kesinleşmiş kapanışı.
      - YALNIZCA ilan edilen ağırlık DEĞİŞTİĞİNDE işlem yapılır; Δ=0 yazan günde
        pozisyon sürüklenir (raporu izleyen kimse "değişmedi" gününde yeniden
        dengeleme yapmaz). İşlem tutarı = portföy değeri × Δağırlık.
      - Nakit getirisi %0, işlem maliyeti yok.
      - Seans olmayan günde (hafta sonu/tatil) ilan edilen ağırlık, izleyen ilk
        seansın kapanışında infaz edilir.
    """
    declared = {}
    for r in weight_rows:
        try:
            declared.setdefault(r["date"].strip(), {})[r["ticker"].strip()] = float(r["weight_pct"])
        except (KeyError, ValueError):
            continue
    eff = {}
    for d in sorted(declared):
        e = next((x for x in all_dates if x >= d), None)
        if e:
            eff[e] = declared[d]  # aynı seansa düşen birden çok ilan → sonuncusu
    if not eff:
        return None

    start = min(eff)
    cash, sh, last, prev_w = 1.0, {}, {}, {}
    sessions, cash_sum, missing = 0, 0.0, []
    nav = 1.0
    for d in all_dates:
        if d < start:
            continue
        for t in set(sh) | set(eff.get(d, {})):
            if t != CASH and t in prices and d in prices[t]:
                last[t] = prices[t][d]
        nav = cash + sum(n * last[t] for t, n in sh.items() if n)
        if d in eff:
            tgt = {t: w for t, w in eff[d].items() if t != CASH}
            for t in set(tgt) | set(prev_w):
                wn, wo = tgt.get(t, 0.0), prev_w.get(t, 0.0)
                held = sh.get(t, 0.0)
                if abs(wn - wo) < 1e-9 or (wn <= 0 and abs(held) < 1e-12):
                    continue
                if t not in last:
                    missing.append(f"{t}@{d}")
                    continue
                if wn <= 0:
                    want = 0.0
                elif wo <= 0:
                    want = nav * (wn / 100) / last[t]
                else:
                    want = held + nav * ((wn - wo) / 100) / last[t]
                cash -= (want - held) * last[t]
                sh[t] = want
            prev_w = tgt
        if d > start:
            sessions += 1
            cash_sum += cash / nav * 100 if nav else 0.0
    if missing:
        warnings.append("model portföy: ağırlığı değişen ismin kapanışı yok (işlem atlandı): "
                        + ", ".join(missing[:6]) + (" …" if len(missing) > 6 else ""))
    end = all_dates[-1]
    xu = bench[end] / bench[start]

    # ağırlık devri (KURAL 9 whipsaw ölçüsü): kuruluş günü hariç Σ|Δ|, nakit hariç
    ds = sorted(declared)
    churn = []
    for i in range(1, len(ds)):
        p, c = declared[ds[i - 1]], declared[ds[i]]
        churn.append(sum(abs(c.get(t, 0.0) - p.get(t, 0.0))
                         for t in set(p) | set(c) if t != CASH))
    return {"start": start, "end": end, "sessions": sessions, "nav": nav, "xu": xu,
            "avg_cash": cash_sum / sessions if sessions else 0.0,
            "churn_total": sum(churn), "churn_days": len(churn),
            "churn_last20": sum(churn[-20:]), "n_last20": len(churn[-20:])}


def main():
    ap = argparse.ArgumentParser(description="finance-agent v2 performans/alfa hesabı")
    ap.add_argument("--root", default=None, help="repo kökü (varsayılan: bu script'in bir üstü)")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else ROOT

    warnings = []
    prices = load_prices(root)
    positions = load_positions(root)

    if BENCH not in prices:
        print(f"HATA: prices.csv içinde {BENCH} yok.")
        sys.exit(1)

    bench = prices[BENCH]
    all_dates = sorted(bench)
    as_of = all_dates[-1]

    age = (date.today() - datetime.strptime(as_of, "%Y-%m-%d").date()).days
    if age > STALE_DAYS:
        warnings.append(f"prices.csv bayat: son satır {as_of} ({age} gün önce).")

    # ---------- pozisyon bacakları ----------
    rows = []
    for p in positions:
        t, ed = p["ticker"].strip(), p["entry_date"].strip()
        status = p["status"].strip()
        if t not in prices or ed not in prices[t]:
            warnings.append(f"{t}: giriş tarihi {ed} için prices.csv satırı yok — atlandı.")
            continue
        bed = on_or_before(bench, ed)
        if bed is None:
            warnings.append(f"{t}: giriş tarihi {ed} ve öncesi için {BENCH} kapanışı yok — atlandı.")
            continue
        if bed != ed:
            warnings.append(f"{t}: giriş tarihi {ed} için {BENCH} kapanışı yok — {bed} kullanıldı.")
        entry = prices[t][ed]
        declared = float(p["entry_close"]) if p.get("entry_close") else entry
        if declared and abs(entry - declared) / declared > 0.005:
            warnings.append(
                f"{t}: positions.csv entry_close={declared} ile prices.csv {ed} kapanışı "
                f"{entry} uyuşmuyor (>%0,5). prices.csv esas alındı."
            )

        exit_date = (p.get("exit_date") or "").strip()
        closed = status == "closed" and exit_date
        cutoff = min(exit_date, as_of) if closed else as_of

        last_d = on_or_before(prices[t], cutoff)
        if last_d is None or last_d < ed:
            warnings.append(f"{t}: {cutoff} ve öncesi için kapanış yok — atlandı.")
            continue
        if last_d != cutoff:
            if closed:
                warnings.append(f"{t}: çıkış tarihi {cutoff} kapanışı yok — {last_d} kullanıldı.")
            else:
                warnings.append(f"{t}: {cutoff} kapanışı yok — {last_d} kullanıldı.")
        last = prices[t][last_d]

        # iki bacak AYNI tarihte durur: XU100 bacağı hissenin durduğu kapanışa hizalanır
        bd = on_or_before(bench, last_d)
        ret = (last / entry - 1) * 100
        xu = (bench[bd] / bench[bed] - 1) * 100

        r = {"ticker": t, "entry_date": ed, "entry": entry, "last": last, "last_date": last_d,
             "ret": ret, "xu": xu, "alpha": ret - xu, "status": status, "exit_date": exit_date}

        # --- KESİM MALİYETİ: tutsaydık? (METHODOLOGY §4.2) ---
        if closed:
            nd = on_or_before(prices[t], as_of)
            if nd and nd > last_d:
                hbd = on_or_before(bench, nd)
                hold_ret = (prices[t][nd] / entry - 1) * 100
                hold_xu = (bench[hbd] / bench[bed] - 1) * 100
                r["hold_alpha"] = hold_ret - hold_xu
                r["hold_px"] = prices[t][nd]
                r["hold_date"] = nd
                r["tracked"] = sum(1 for d in all_dates if last_d < d <= nd)
                r["cut_gain"] = r["alpha"] - r["hold_alpha"]  # + ise kesim DOĞRUYDU
            else:
                # çıkıştan sonra henüz seans yoksa ölçüm BEKLİYOR; seans geçtiyse VERİ EKSİĞİ
                r["pending"] = last_d >= as_of
        rows.append(r)

    open_rows = sorted([r for r in rows if r["status"] == "open"], key=lambda r: -r["alpha"])
    closed_rows = sorted([r for r in rows if r["status"] == "closed"], key=lambda r: -r["alpha"])
    watch_rows = [r for r in rows if r["status"] not in ("open", "closed")]
    booked = open_rows + closed_rows  # program sicili = fiilen alınmış her pozisyon

    # ---------- survivorship-free günlük seri (zincirlenmiş eşit ağırlık) ----------
    def held_on(d):
        return [r for r in booked
                if r["entry_date"] <= d and (not r["exit_date"] or r["exit_date"] >= d)
                and d in prices[r["ticker"]]]

    series = []
    nav = xunav = 1.0
    peak_rel, max_dd, max_dd_d = 1.0, 0.0, None
    prev = None
    for d in all_dates:
        cur = held_on(d)
        if prev is not None:
            both = [r for r in cur if r["entry_date"] <= prev
                    and prev in prices[r["ticker"]] and d in prices[r["ticker"]]]
            if both:
                nav *= 1 + sum(prices[r["ticker"]][d] / prices[r["ticker"]][prev] - 1
                               for r in both) / len(both)
                xunav *= bench[d] / bench[prev]
                rel = nav / xunav
                peak_rel = max(peak_rel, rel)
                dd = (rel / peak_rel - 1) * 100
                if dd < max_dd:
                    max_dd, max_dd_d = dd, d
                series.append((d, (nav - 1) * 100, (xunav - 1) * 100, (nav - xunav) * 100))
        if cur:
            prev = d

    # ---------- çıktı ----------
    print(f"### Gerçekleşen Performans — kesinleşmiş kapanışlarla (as-of: {as_of})")
    print()
    print("*(Kaynak: `data/prices.csv` + `scripts/compute_perf.py` — deterministik hesap. "
          "Giriş ve skorlama = kesinleşmiş kapanış; bugünün intraday fiyatı bu tablolara girmez.)*")
    print()

    # A) açık
    print("#### A) AÇIK POZİSYONLAR")
    print()
    if open_rows:
        print("| Hisse | Giriş | Giriş kapanışı | Son kapanış | Getiri | XU100 | **ALFA** |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for r in open_rows:
            print(f"| {r['ticker']} | {r['entry_date']} | {tr_num(r['entry'])} | {tr_num(r['last'])} "
                  f"| {tr_pct(r['ret'])} | {tr_pct(r['xu'])} | **{tr_pct(r['alpha'])}** |")
        o_ret = sum(r["ret"] for r in open_rows) / len(open_rows)
        o_xu = sum(r["xu"] for r in open_rows) / len(open_rows)
        print()
        print(f"**Eşit-ağırlık açık ({len(open_rows)} isim):** getiri {tr_pct(o_ret)} · "
              f"XU100 {tr_pct(o_xu)} · **ALFA {tr_pct(o_ret - o_xu)}** · "
              f"isabet {sum(1 for r in open_rows if r['alpha'] > 0)}/{len(open_rows)}")
    else:
        print("*Açık pozisyon yok.*")
    print()

    # B) kapanmış
    print("#### B) KAPANMIŞ POZİSYONLAR (realize)")
    print()
    if closed_rows:
        print("| Hisse | Giriş | Çıkış | Giriş→Çıkış | XU100 | **REALİZE ALFA** |")
        print("|---|---|---|---:|---:|---:|")
        for r in closed_rows:
            print(f"| {r['ticker']} | {r['entry_date']} | {r['exit_date']} | {tr_pct(r['ret'])} "
                  f"| {tr_pct(r['xu'])} | **{tr_pct(r['alpha'])}** |")
        c_ret = sum(r["ret"] for r in closed_rows) / len(closed_rows)
        c_xu = sum(r["xu"] for r in closed_rows) / len(closed_rows)
        print()
        print(f"**Eşit-ağırlık realize ({len(closed_rows)} pozisyon):** getiri {tr_pct(c_ret)} · "
              f"XU100 {tr_pct(c_xu)} · **ALFA {tr_pct(c_ret - c_xu)}** · "
              f"isabet {sum(1 for r in closed_rows if r['alpha'] > 0)}/{len(closed_rows)}")
    else:
        print("*Kapanmış pozisyon yok.*")
    print()

    # C) PROGRAM SİCİLİ — manşet
    print("#### C) PROGRAM SİCİLİ (açık + realize) — **MANŞET METRİK**")
    print()
    if booked:
        b_ret = sum(r["ret"] for r in booked) / len(booked)
        b_xu = sum(r["xu"] for r in booked) / len(booked)
        hits = sum(1 for r in booked if r["alpha"] > 0)
        print(f"**Alınmış tüm pozisyonlar ({len(booked)}):** getiri {tr_pct(b_ret)} · "
              f"aynı dönem XU100 {tr_pct(b_xu)} · **KÜMÜLATİF ALFA {tr_pct(b_ret - b_xu)}**")
        print(f"**İsabet (pozitif alfa):** {hits}/{len(booked)} (%{hits / len(booked) * 100:.0f})")
    if series:
        d, pr, xr, al = series[-1]
        print(f"**Zaman-ağırlıklı portföy serisi (survivorship-free, {len(series)} seans):** "
              f"portföy {tr_pct(pr)} · XU100 {tr_pct(xr)} · **ALFA {tr_pp(al)}**")
        print(f"**Maks. rölatif düşüş (XU100'e karşı):** {tr_pct(max_dd)}"
              + (f" ({max_dd_d})" if max_dd_d else ""))
    print()

    # D) KESİM MALİYETİ — v2'nin yeni bölümü
    print("#### D) KESİM MALİYETİ ÖLÇÜMÜ (METHODOLOGY §4.2)")
    print()
    print("*Her kesim için: realize alfa vs bugüne kadar TUTSAYDIK alfa. "
          "Pozitif fayda = kesim doğruydu. Bu bölüm stop disiplinini **çürütebilir** "
          "kanıt üretir; ölçülemeyen kesim kuralın lehine yorumlanamaz.*")
    print()
    meas = [r for r in closed_rows if "cut_gain" in r]
    pending = [r for r in closed_rows if r.get("pending") is True]
    missing = [r for r in closed_rows if r.get("pending") is False]
    if meas:
        print("| Hisse | Çıkış | Çıkış fiyatı | Bugünkü fiyat | Realize alfa | Tutsaydık alfa | **Kesimin faydası** |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for r in sorted(meas, key=lambda r: r["cut_gain"]):
            frozen = f" ({r['hold_date']})" if r["hold_date"] != as_of else ""
            print(f"| {r['ticker']} | {r['exit_date']} | {tr_num(r['last'])} | {tr_num(r['hold_px'])}{frozen} "
                  f"| {tr_pct(r['alpha'])} | {tr_pct(r['hold_alpha'])} | **{tr_pp(r['cut_gain'])}** |")
        net = sum(r["cut_gain"] for r in meas)
        good = sum(1 for r in meas if r["cut_gain"] > 0)
        print()
        print(f"**Net kesim etkisi ({len(meas)} ölçülebilir kesim):** {tr_pp(net)} · "
              f"ortalama {tr_pp(net / len(meas))} · **doğru kesim {good}/{len(meas)}**")
    else:
        print("*Ölçülebilir kesim yok.*")
    for r in meas:
        if r["hold_date"] != as_of:
            if r["tracked"] < TRACK_SESSIONS:
                print(f"- ⚠ {r['ticker']} ({r['exit_date']}): izleme {r['hold_date']}'de kesilmiş "
                      f"({r['tracked']}/{TRACK_SESSIONS} seans) — METHODOLOGY §6.2 ihlali; "
                      f"ölçüm o tarihte dondu (iki bacak da).")
            else:
                print(f"- {r['ticker']} ({r['exit_date']}): {TRACK_SESSIONS} seanslık izleme penceresi doldu; "
                      f"ölçüm {r['hold_date']}'de donduruldu (iki bacak da).")
    if pending:
        print(f"- ⏳ {len(pending)} kesim henüz ölçülemez ("
              + ", ".join(f"{r['ticker']} {r['exit_date']}" for r in pending)
              + ") — çıkış as-of seansında, çıkış sonrası seans henüz yok. İhlal DEĞİL; "
                "ilk ölçüm bir sonraki backfill'de. KURAL 10: kuralın lehine sayılmaz.")
    if missing:
        print(f"- ⚠ {len(missing)} kesim ölçülemedi ("
              + ", ".join(f"{r['ticker']} {r['exit_date']}" for r in missing)
              + ") — çıkıştan sonra seans geçti ama fiyat yok: METHODOLOGY §6.2 ihlali, "
                "VERİ EKSİĞİ olarak raporlanır.")
    print()

    # E) MODEL PORTFÖY — ilan edilen ağırlıklar birebir izlenseydi
    mp = model_portfolio(prices, bench, all_dates, load_weights(root), warnings)
    print("#### E) MODEL PORTFÖY — 1.000 TL testi (METHODOLOGY §4.3)")
    print()
    if mp and mp["sessions"]:
        print("*Raporların `weights.csv`'de ilan ettiği ağırlıklar (nakit dahil) birebir izlenseydi. "
              "İnfaz = rapor gününün kesinleşmiş kapanışı; yalnızca ağırlık DEĞİŞİNCE işlem (arada sürüklenir); "
              "nakit getirisi %0; işlem maliyeti yok. §C eşit ağırlıkla İSİM SEÇİMİNİ ölçer; "
              "bu bölüm ağırlık + nakit + zamanlama dahil PARANIN kendisini ölçer.*")
        print()
        p_ret, x_ret = (mp["nav"] - 1) * 100, (mp["xu"] - 1) * 100
        print(f"**1.000 TL → {tr_num(mp['nav'] * 1000, 0)} TL** (getiri {tr_pct(p_ret)}) · "
              f"XU100 al-tut → {tr_num(mp['xu'] * 1000, 0)} TL ({tr_pct(x_ret)}) · "
              f"**ALFA {tr_pp(p_ret - x_ret)}** · {mp['start']} → {mp['end']} ({mp['sessions']} seans)")
        print(f"**Ortalama nakit payı:** %{tr_num(mp['avg_cash'], 1)} · "
              f"**ağırlık devri (nakit hariç Σ|Δ|):** {tr_num(mp['churn_total'], 0)} puan / "
              f"{mp['churn_days']} rapor günü · son {mp['n_last20']} rapor günü: "
              f"{tr_num(mp['churn_last20'], 0)} puan")
    else:
        print("*weights.csv yok veya henüz infaz edilmiş ağırlık yok.*")
    print()

    # izleme
    if watch_rows:
        print("#### İzleme (portföye hiç alınmadı — sicile dahil DEĞİL)")
        print()
        print("| Hisse | Tarih | Fiyat | Bugün | Getiri | XU100 | ALFA |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for r in watch_rows:
            print(f"| {r['ticker']} | {r['entry_date']} | {tr_num(r['entry'])} | {tr_num(r['last'])} "
                  f"| {tr_pct(r['ret'])} | {tr_pct(r['xu'])} | {tr_pct(r['alpha'])} |")
        print()

    # günlük seri
    print("<details><summary>Günlük kümülatif seri (survivorship-free — o gün fiilen açık pozisyonlar)</summary>")
    print()
    print("| Tarih | Portföy | XU100 | ALFA (pp) |")
    print("|---|---:|---:|---:|")
    for d, pr, xr, al in series:
        print(f"| {d} | {tr_pct(pr)} | {tr_pct(xr)} | {tr_pp(al)} |")
    print()
    print("</details>")

    wrows = load_weights(root)
    if wrows:
        wd = max(r["date"] for r in wrows)
        act = [w for w in wrows if w["date"] == wd and float(w["weight_pct"]) > 0]
        print()
        print(f"**Son kayıtlı ağırlıklar ({wd}):** "
              + " · ".join(f"{w['ticker']} %{w['weight_pct']}" for w in act))

    if warnings:
        print()
        print("**UYARILAR (ledger tutarlılığı):**")
        for w in warnings:
            print(f"- ⚠ {w}")


if __name__ == "__main__":
    main()
