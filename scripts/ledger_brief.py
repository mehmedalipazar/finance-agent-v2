#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance-agent v2 — günlük LEDGER ÖZETİ (METHODOLOGY §6.3).

Neden var: weights.csv + triggers.csv 2026-09-21'de ~390 KB'a ulaştı (tetik gerekçesi
metni Haziran'da ort. 25 karakterken Eylül'de 717) ve rutin her gün tamamını okuyordu.
Bu, her koşuda ~130 bin token ve sınırsız büyüyen bir maliyetti. Bu script kararın
ihtiyaç duyduğu her şeyi birkaç KB'ta verir; CSV'lerin TAMAMI okunmaz — gerekirse
burada verilen satır numarasıyla (L…) ilgili satıra bakılır.

Ayrıca backfill listesini (METHODOLOGY §6.2) DETERMİNİSTİK üretir: hangi ticker'ın
hâlâ izlendiği modelin hafızasına değil deftere bağlıdır.

Kullanım: python3 scripts/ledger_brief.py [--root DİZİN]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def fnum(x, nd=2):
    try:
        return f"{float(x):,.{nd}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    except (TypeError, ValueError):
        return "—"


def main():
    ap = argparse.ArgumentParser(description="finance-agent v2 günlük ledger özeti")
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else L.ROOT

    prices = L.load_prices(root)
    positions = L.load_rows(root, "positions.csv")
    weights = L.load_rows(root, "weights.csv")
    triggers = L.load_rows(root, "triggers.csv")
    if L.BENCH not in prices:
        print(f"HATA: prices.csv içinde {L.BENCH} yok.")
        sys.exit(1)
    bench_dates = sorted(prices[L.BENCH])
    as_of = bench_dates[-1]
    today = L.today_trt()
    trk = L.tracking(positions, bench_dates)
    syms = L.backfill_list(trk)

    print(f"# LEDGER ÖZETİ — as-of {as_of} · bugün {today} (TRT)")
    print()
    print("*Kaynak: `scripts/ledger_brief.py` — `data/*.csv`'den deterministik. CSV'lerin tamamını okuma; "
          "ayrıntı gerekiyorsa aşağıdaki satır numarasıyla (L…) yalnızca o satıra bak.*")
    print()

    # 1) backfill
    print("## 1. Backfill görevi (METHODOLOGY §6 / §6.2)")
    print()
    cand = L.candidate_sessions(as_of)
    print(f"- Son kesinleşmiş seans: **{as_of}**")
    if cand:
        print(f"- Çekilecek seans(lar): **{', '.join(cand)}** (resmî tatilse XU100 veri döndürmez → o gün atlanır)")
    else:
        print("- Çekilecek seans yok (defter güncel; bugünün kapanışı 18:15 TRT'den önce kesinleşmiş DEĞİLDİR)")
    print(f"- Çekilecek semboller ({len(syms)}): " + " · ".join(f"[{', '.join(c)}]" for c in L.chunks(syms, 3))
          + "  ← ≤3'lü gruplar")
    if trk["closed"]:
        print("- Kapanmış ama HÂLÂ izlenen (listeden DÜŞÜRME): "
              + ", ".join(f"{t} (çıkış {xd}, {k}/{L.TRACK_SESSIONS} seans)" for t, xd, k in trk["closed"]))
    if trk["dropped"]:
        print("- İzleme penceresi dolan (artık çekilmez): "
              + ", ".join(f"{t} (çıkış {xd}, {k} seans)" for t, xd, k in trk["dropped"]))
    print("- ATOMİK SEANS KURALI: bir seans ya listedeki TÜM semboller için yazılır ya hiç yazılmaz.")
    print()

    # 2) açık pozisyonlar
    print("## 2. Açık pozisyonlar")
    print()
    open_pos = [p for p in positions if p["status"].strip() == "open"]
    if open_pos:
        print("| Hisse | Sektör | Giriş | Giriş kapanışı | Stop (ilk → güncel) | Hedef | Son kapanış | Stop tamponu |")
        print("|---|---|---|---:|---|---:|---:|---:|")
        for p in open_pos:
            t = p["ticker"].strip()
            ds = [d for d in prices.get(t, {}) if d <= as_of]
            last = prices[t][max(ds)] if ds else None
            try:
                buf = f"%{fnum((last / float(p['current_stop']) - 1) * 100, 1)}"
            except (TypeError, ValueError, ZeroDivisionError):
                buf = "—"
            print(f"| {t} | {p['sector']} | {p['entry_date']} | {fnum(p['entry_close'])} | "
                  f"{p['initial_stop']} → {p['current_stop']} | {fnum(p['initial_target'])} | "
                  f"{fnum(last)} | {buf} |")
    else:
        print("*Açık pozisyon yok.*")
    print()

    # 3) son ağırlıklar
    print("## 3. Son ilan edilen ağırlıklar")
    print()
    if weights:
        wd = max(r["date"] for r in weights)
        rows = [r for r in weights if r["date"] == wd]
        print(f"**{wd}:** " + " · ".join(f"{r['ticker']} %{r['weight_pct']}" for r in rows)
              + f"  (toplam %{fnum(sum(float(r['weight_pct']) for r in rows), 0)})")
        print()
        for r in rows:
            print(f"- {r['ticker']} (Δ {r['delta_pp']}): {L.clip(r['trigger'], 200)}")
    print()

    # 4) aktif tetikler
    active = [(i + 2, r) for i, r in enumerate(triggers) if r["status"].strip() == "active"]
    held = set(trk["open"]) | set(trk["watch"])
    market = [(n, r) for n, r in active if r["scope"].strip() in held]
    other = [(n, r) for n, r in active if r["scope"].strip() not in held]
    print(f"## 4. Aktif tetikler ({len(active)}) — L = triggers.csv satır numarası")
    print()
    for title, grp, clen in (("### 4a. Portföydeki isimlere bağlı (HER GÜN ölçülür)", market, 300),
                             ("### 4b. Diğer (aday isim / portföy / altyapı / metodoloji)", other, 160)):
        print(title)
        print()
        if not grp:
            print("*Yok.*")
            print()
            continue
        print("| L | Açılış | Kapsam | Koşul | Aksiyon |")
        print("|---:|---|---|---|---|")
        for n, r in grp:
            print(f"| {n} | {r['date_set']} | {r['scope']} | {L.clip(r['condition'], clen).replace('|', '/')} "
                  f"| {L.clip(r['action'], clen).replace('|', '/')} |")
        print()
    new_today = sum(1 for r in triggers if r["date_set"].strip() == today)
    print(f"**Tetik bütçesi (KURAL 9c):** bugün açılan {new_today}/{L.TRIGGER_BUDGET}. "
          f"Aktif tetik {len(active)} — 40'ın üstü enflasyondur; ölçülemeyen/bayat olanı expire et.")
    print()

    # 5) kapanmış pozisyonlar
    closed_pos = [p for p in positions if p["status"].strip() == "closed"]
    print(f"## 5. Kapanmış pozisyonlar ({len(closed_pos)}) — geri alım METHODOLOGY §5.2'ye tabidir")
    print()
    if closed_pos:
        print("| Hisse | Giriş → Çıkış | Çıkış kapanışı | Neden (kısaltılmış) |")
        print("|---|---|---:|---|")
        for p in sorted(closed_pos, key=lambda p: p["exit_date"], reverse=True):
            print(f"| {p['ticker']} | {p['entry_date']} → {p['exit_date']} | {fnum(p['exit_close'])} "
                  f"| {L.clip(p['exit_reason'], 140).replace('|', '/')} |")
    print()
    print("## 6. Sıradaki adımlar")
    print()
    print("1. Backfill (§1) → 2. `python3 scripts/compute_perf.py` (karar girdisi) → 3. analiz + ledger güncelle "
          "→ 4. `compute_perf.py`'yi ledger'ın SON hâliyle YENİDEN çalıştır, rapora AYNEN yapıştır "
          "→ 5. `python3 scripts/validate_ledger.py` HATA=0 → 6. commit + push.")


if __name__ == "__main__":
    main()
