#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance-agent v2 — kesinleşmiş kapanışlar için İKİNCİ KANAL (METHODOLOGY §6.1).

Neden var: 08-21, 08-26, 08-28, 09-16 ve 09-21'de borsa-mcp oturuma araç kaydetmedi ve
defter dondu (67 seansın 5'i). Kesinti günlerinde rutin "doğrudan HTTP yedeği"ni her
seferinde elle, 7 ayrı host'a curl atarak deniyordu. Bu script o denemeyi TEK komuta
indirir ve sonucu deterministik raporlar.

Kaynak: Yahoo Finance chart API — borsa-mcp `get_historical_data`'nın (yfinance) AYNI
birincil kaynağıdır; yalnızca taşıma farklıdır. Yani §3'teki "kesinleşmiş kapanışın tek
kaynağı" kuralını gevşetmez. Web araması / haber sitesi fiyatı HÂLÂ yasaktır (§6.1.1).

Güvenceler:
  - BUGÜNÜN barı 18:15 TRT'den önce ASLA alınmaz (seans içi değer kapanış değildir).
  - ATOMİK SEANS: bir seans, listedeki TÜM semboller kapanış döndürdüyse yazılır;
    eksik varsa o seans ve sonrası YAZILMAZ (defterde delik açılmaz).
  - Sembol listesi modelin hafızasından değil defterden gelir (ledger.tracking, §6.2).

Kullanım:
  python3 scripts/fetch_closes.py              # kuru çalıştırma: eklenecek satırları göster
  python3 scripts/fetch_closes.py --write      # data/prices.csv'ye ekle
  python3 scripts/fetch_closes.py --verify 10  # defterin son 10 seansını kaynakla karşılaştır

Çıkış kodu: 0 tamam · 2 ağ erişimi yok (egress engelli / kaynak kapalı) · 3 eksik veri
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
UA = "Mozilla/5.0 (finance-agent-v2 ledger backfill)"
TOLERANCE = 0.005  # %0,5 — entry_close/exit_close denetimiyle aynı eşik


class NetworkBlocked(Exception):
    pass


def yahoo_daily(symbol, start, end):
    """symbol için [start, end] aralığındaki günlük kapanışlar → {YYYY-MM-DD: close}."""
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()) - 86400
    p2 = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp()) + 2 * 86400
    q = urllib.parse.urlencode({"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"})
    last_err = None
    for host in HOSTS:
        url = f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol)}.IS?{q}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            last_err = f"{host}: HTTP {e.code}"
            if e.code == 404:
                return {}
            continue
        except Exception as e:  # URLError, timeout, proxy CONNECT reddi…
            last_err = f"{host}: {type(e).__name__}: {e}"
            continue
        res = (data.get("chart") or {}).get("result") or []
        if not res:
            return {}
        off = res[0].get("meta", {}).get("gmtoffset", 10800)
        ts = res[0].get("timestamp") or []
        cl = ((res[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        out = {}
        for t, c in zip(ts, cl):
            if c is None:
                continue
            d = (datetime.fromtimestamp(t, timezone.utc) + timedelta(seconds=off)).date().isoformat()
            if start <= d <= end:
                out[d] = round(float(c), 2)
        return out
    raise NetworkBlocked(last_err or "bilinmeyen ağ hatası")


def main():
    ap = argparse.ArgumentParser(description="kesinleşmiş kapanışlar için ikinci kanal (Yahoo chart API)")
    ap.add_argument("--root", default=None)
    ap.add_argument("--write", action="store_true", help="data/prices.csv'ye ekle (varsayılan: kuru çalıştırma)")
    ap.add_argument("--verify", type=int, metavar="N", help="defterin son N seansını kaynakla karşılaştır")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else L.ROOT

    prices = L.load_prices(root)
    positions = L.load_rows(root, "positions.csv")
    if L.BENCH not in prices:
        print(f"HATA: prices.csv içinde {L.BENCH} yok.")
        sys.exit(1)
    bench_dates = sorted(prices[L.BENCH])
    as_of = bench_dates[-1]
    syms = L.backfill_list(L.tracking(positions, bench_dates))

    if args.verify:
        window = bench_dates[-args.verify:]
        lo, hi = window[0], window[-1]
        bad = checked = 0
        try:
            for s in syms:
                src = yahoo_daily(s, lo, hi)
                for d in window:
                    mine = prices.get(s, {}).get(d)
                    if mine is None or d not in src:
                        continue
                    checked += 1
                    if abs(src[d] - mine) / mine > TOLERANCE:
                        bad += 1
                        print(f"UYUŞMAZLIK  {d} {s}: defter {mine} · kaynak {src[d]} "
                              f"({(src[d] / mine - 1) * 100:+.2f}%)")
                time.sleep(0.2)
        except NetworkBlocked as e:
            print(f"AĞ ERİŞİMİ YOK — ikinci kanal kapalı ({e}). Doğrulama yapılamadı.")
            sys.exit(2)
        print(f"DOĞRULAMA: {lo} → {hi} · {len(syms)} sembol · {checked} hücre karşılaştırıldı · "
              f"{bad} uyuşmazlık (eşik %{TOLERANCE * 100:g})")
        sys.exit(3 if bad else 0)

    cand = L.candidate_sessions(as_of)
    if not cand:
        print(f"Defter güncel (as-of {as_of}); çekilecek kesinleşmiş seans yok.")
        return
    lo, hi = cand[0], cand[-1]
    got = {}
    try:
        for s in syms:
            got[s] = yahoo_daily(s, lo, hi)
            time.sleep(0.2)
    except NetworkBlocked as e:
        print(f"AĞ ERİŞİMİ YOK — ikinci kanal kapalı ({e}).")
        print("Bu ortamın egress politikası query1/query2.finance.yahoo.com'a izin vermiyor olabilir. "
              "METHODOLOGY §6.1 kesinti protokolünü uygula; bu sonucu raporda kanıt olarak kullan.")
        sys.exit(2)

    sessions = sorted(d for d in got[L.BENCH] if d in cand)  # XU100 yoksa o gün seans yok (tatil)
    rows, incomplete = [], None
    for d in sessions:
        miss = [s for s in syms if d not in got[s]]
        if miss:
            incomplete = (d, miss)
            break
        rows += [(d, s, got[s][d]) for s in syms]

    print(f"Kaynak: Yahoo chart API · aday seanslar: {', '.join(cand)} · sembol: {len(syms)}")
    if not sessions:
        print("XU100 bu aralıkta kapanış döndürmedi → seans yok (tatil) veya veri henüz yayınlanmadı.")
    for d, s, c in rows:
        print(f"{d},{s},{c:.2f}")
    if incomplete:
        print(f"EKSİK: {incomplete[0]} seansında şu semboller kapanış döndürmedi: {', '.join(incomplete[1])} "
              f"→ ATOMİK SEANS kuralı gereği {incomplete[0]} ve sonrası YAZILMADI.")
    if args.write and rows:
        path = root / "data" / "prices.csv"
        tail = path.read_bytes()[-1:]
        with open(path, "a", encoding="utf-8", newline="") as f:
            if tail not in (b"\n", b""):
                f.write("\n")
            w = csv.writer(f, lineterminator="\n")
            for d, s, c in rows:
                w.writerow([d, s, f"{c:.2f}"])
        print(f"YAZILDI: {len(rows)} satır → data/prices.csv (seanslar: "
              f"{', '.join(sorted({r[0] for r in rows}))}). Raporda kaynağı 'ikinci kanal (Yahoo chart API)' diye belirt.")
    elif rows:
        print(f"(kuru çalıştırma — {len(rows)} satır yazılmadı; yazmak için --write)")
    sys.exit(3 if incomplete else 0)


if __name__ == "__main__":
    main()
