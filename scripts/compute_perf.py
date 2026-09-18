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

Girdi:  data/prices.csv (yalnızca KESİNLEŞMİŞ kapanışlar) · data/positions.csv · data/weights.csv
Çıktı:  stdout'a markdown — raporun "Gerçekleşen Performans" bölümüne AYNEN yapıştırılır.

Kullanım: python3 scripts/compute_perf.py
"""
import csv
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = "XU100"
STALE_DAYS = 5

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


def load_prices():
    prices = {}
    with open(ROOT / "data" / "prices.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            prices.setdefault(row["ticker"].strip(), {})[row["date"].strip()] = float(row["close"])
    return prices


def load_positions():
    with open(ROOT / "data" / "positions.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_last_weights():
    path = ROOT / "data" / "weights.csv"
    if not path.exists():
        return None, []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None, []
    last = max(r["date"] for r in rows)
    return last, [r for r in rows if r["date"] == last]


def main():
    warnings = []
    prices = load_prices()
    positions = load_positions()

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

        avail = [d for d in prices[t] if d <= cutoff]
        if not avail:
            warnings.append(f"{t}: {cutoff} ve öncesi için kapanış yok — atlandı.")
            continue
        last_d = max(avail)
        if last_d != cutoff and not closed:
            warnings.append(f"{t}: {cutoff} kapanışı yok — {last_d} kullanıldı.")
        last = prices[t][last_d]

        bd = max(d for d in bench if d <= cutoff)
        ret = (last / entry - 1) * 100
        xu = (bench[bd] / bench[ed] - 1) * 100

        r = {"ticker": t, "entry_date": ed, "entry": entry, "last": last, "last_date": last_d,
             "ret": ret, "xu": xu, "alpha": ret - xu, "status": status, "exit_date": exit_date}

        # --- KESİM MALİYETİ: bugüne kadar tutsaydık? (METHODOLOGY §4.2) ---
        if closed:
            nowav = [d for d in prices[t] if d <= as_of]
            if nowav and max(nowav) > last_d:
                nd = max(nowav)
                hold_ret = (prices[t][nd] / entry - 1) * 100
                hold_xu = (bench[as_of] / bench[ed] - 1) * 100
                r["hold_alpha"] = hold_ret - hold_xu
                r["hold_px"] = prices[t][nd]
                r["cut_gain"] = r["alpha"] - r["hold_alpha"]  # + ise kesim DOĞRUYDU
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
    if meas:
        print("| Hisse | Çıkış | Çıkış fiyatı | Bugünkü fiyat | Realize alfa | Tutsaydık alfa | **Kesimin faydası** |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for r in sorted(meas, key=lambda r: r["cut_gain"]):
            print(f"| {r['ticker']} | {r['exit_date']} | {tr_num(r['last'])} | {tr_num(r['hold_px'])} "
                  f"| {tr_pct(r['alpha'])} | {tr_pct(r['hold_alpha'])} | **{tr_pp(r['cut_gain'])}** |")
        net = sum(r["cut_gain"] for r in meas)
        good = sum(1 for r in meas if r["cut_gain"] > 0)
        print()
        print(f"**Net kesim etkisi ({len(meas)} ölçülebilir kesim):** {tr_pp(net)} · "
              f"ortalama {tr_pp(net / len(meas))} · **doğru kesim {good}/{len(meas)}**")
        unmeasured = len(closed_rows) - len(meas)
        if unmeasured:
            print(f"- ⚠ {unmeasured} kesim ölçülemedi (çıkış sonrası fiyat yok) — "
                  f"METHODOLOGY §6.2 ihlali, VERİ EKSİĞİ olarak raporlanır.")
    else:
        print("*Ölçülebilir kesim yok.*")
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

    # E) seri
    print("<details><summary>Günlük kümülatif seri (survivorship-free — o gün fiilen açık pozisyonlar)</summary>")
    print()
    print("| Tarih | Portföy | XU100 | ALFA (pp) |")
    print("|---|---:|---:|---:|")
    for d, pr, xr, al in series:
        print(f"| {d} | {tr_pct(pr)} | {tr_pct(xr)} | {tr_pp(al)} |")
    print()
    print("</details>")

    wd, wrows = load_last_weights()
    if wrows:
        act = [w for w in wrows if float(w["weight_pct"]) > 0]
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
