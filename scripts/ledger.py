#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance-agent v2 — ledger ortak yardımcıları (ledger_brief / validate_ledger / fetch_closes).

compute_perf.py bilerek BAĞIMSIZDIR (otoriter hesap tek dosyada, bağımlılıksız kalır);
buradaki mantık yalnızca defterin OKUNMASI ve DENETLENMESİ içindir.
"""
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = "XU100"
CASH = "CASH"
TRACK_SESSIONS = 60          # METHODOLOGY §6.2: çıkan isim en az 60 seans izlenir
TRT = timezone(timedelta(hours=3))   # Türkiye yıl boyu UTC+3 (yaz saati yok)
CLOSE_SETTLED_AFTER = (18, 15)       # bu saatten önce "bugünün kapanışı" kesinleşmiş olamaz

# Metin sütunu tavanları (METHODOLOGY §6.3). Uzun gerekçe RAPORA yazılır; ledger'a özeti.
TEXT_CAPS_FROM = "2026-09-21"
TEXT_CAPS = {
    ("weights.csv", "trigger"): 280,
    ("triggers.csv", "condition"): 300,
    ("triggers.csv", "action"): 200,
    ("triggers.csv", "notes"): 300,
    ("positions.csv", "exit_reason"): 400,
}
TRIGGER_BUDGET_FROM = "2026-09-18"   # KURAL 9(c) v2 ile başladı
TRIGGER_BUDGET = 3


def now_trt():
    return datetime.now(TRT)


def today_trt():
    return now_trt().date().isoformat()


def load_rows(root, name):
    path = Path(root) / "data" / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_prices(root):
    prices = {}
    for r in load_rows(root, "prices.csv"):
        try:
            prices.setdefault(r["ticker"].strip(), {})[r["date"].strip()] = float(r["close"])
        except (KeyError, ValueError, AttributeError):
            continue  # biçim hataları validate_ledger'da raporlanır
    return prices


def sessions_after(bench_dates, d, upto):
    """d'den SONRA, upto dahil kaç seans geçti."""
    return sum(1 for x in bench_dates if d < x <= upto)


def tracking(positions, bench_dates):
    """Backfill listesi (METHODOLOGY §6.2) — deterministik.

    Dönen: {"open": [...], "watch": [...],
            "closed": [(ticker, exit_date, geçen_seans)],   # hâlâ izlenen (<60 seans)
            "dropped": [(ticker, exit_date, geçen_seans)]}  # penceresi dolan
    Aynı ticker hem açık hem kapanmış kayıt taşıyorsa açık olan kazanır; birden çok
    kapanmış kaydı varsa EN SON çıkış esas alınır.
    """
    as_of = bench_dates[-1] if bench_dates else ""
    open_t, watch_t, last_exit = [], [], {}
    for p in positions:
        t, st = p["ticker"].strip(), p["status"].strip()
        if st == "open":
            if t not in open_t:
                open_t.append(t)
        elif st == "closed":
            xd = (p.get("exit_date") or "").strip()
            if xd and xd > last_exit.get(t, ""):
                last_exit[t] = xd
        elif t not in watch_t:
            watch_t.append(t)
    closed, dropped = [], []
    for t, xd in sorted(last_exit.items(), key=lambda kv: kv[1], reverse=True):
        if t in open_t or t in watch_t:
            continue
        k = sessions_after(bench_dates, xd, as_of)
        (closed if k < TRACK_SESSIONS else dropped).append((t, xd, k))
    return {"open": open_t, "watch": watch_t, "closed": closed, "dropped": dropped}


def backfill_list(trk):
    """XU100 başta olmak üzere çekilecek tüm semboller."""
    out = [BENCH]
    for t in trk["open"] + trk["watch"] + [c[0] for c in trk["closed"]]:
        if t not in out:
            out.append(t)
    return out


def candidate_sessions(as_of, now=None):
    """as_of'tan sonraki, kapanışı KESİNLEŞMİŞ olabilecek hafta içi günler.

    Bugün yalnızca 18:15 TRT sonrası dahil edilir (seans içi değer kapanış değildir).
    Resmî tatiller bilinmez: o gün için XU100 verisi dönmüyorsa seans yoktur.
    """
    now = now or now_trt()
    last = now.date()
    if (now.hour, now.minute) < CLOSE_SETTLED_AFTER:
        last -= timedelta(days=1)
    d = date.fromisoformat(as_of) + timedelta(days=1)
    out = []
    while d <= last:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def chunks(seq, n=3):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"
