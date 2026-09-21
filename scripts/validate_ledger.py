#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance-agent v2 — ledger DOĞRULAYICI (METHODOLOGY §6.4).

Neden var: v1'in kök sebebi, kuralların yalnızca METİN olarak var olmasıydı — defter
kendi kurallarına karşı hiçbir zaman MEKANİK olarak denetlenmedi. Bu script, sayıyla
ifade edilebilen her kuralı commit'ten ÖNCE denetler. HATA varsa çıkış kodu 1'dir ve
rutin commit ETMEZ; nedeni düzeltir.

Denetlenenler:
  prices.csv    biçim · yinelenen (tarih,ticker) · hafta sonu/gelecek tarih · bugünün
                kapanışı 18:15 TRT'den önce yazılmış mı (intraday sızıntısı) · ATOMİK
                seans (XU100'de olmayan tarihte hisse satırı) · §6.2 kapsama delikleri
                (açık/izleme/kapanmış<60 seans) · günlük ±%10 limit aşımı (uyarı)
  positions.csv durum değerleri · kapanmışta exit_date/exit_close · giriş/çıkış kapanışı
                prices.csv ile tutarlı mı · tarih sırası
  weights.csv   her gün toplam = 100 · Δ = ağırlık − dünkü ağırlık · son günde ağırlığı
                olan isim AÇIK pozisyon mu · açık pozisyon son günde var mı
  triggers.csv  durum değerleri · kapanmış isme ait AKTİF (bayat) tetik · KURAL 9(c)
                günlük 3 yeni tetik bütçesi · aktif tetik enflasyonu (uyarı)
  metin tavanı  §6.3: ledger hücreleri kısa kalır, uzun gerekçe rapora yazılır
  rapor         son raporun compute_perf.py özet satırlarını AYNEN içerip içermediği
                (elle "düzeltme" ve ledger'dan SONRA güncellenmemiş bayat çıktı yakalanır)
  gizlilik      yerel çalışma dosyaları git'te izlenmez

Kullanım: python3 scripts/validate_ledger.py [--root DİZİN] [--no-report] [--no-git]
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERBATIM_FROM = "2026-09-21"     # bu tarihten itibaren rapor ↔ compute_perf birebir denetlenir
SECTION_E_FROM = "2026-09-22"    # §E bu tarihten itibaren zorunlu (öncesinde varsa denetlenir)
FORBIDDEN_PATHS = re.compile(r"(^|/)routine/|prompt", re.IGNORECASE)
ACTIVE_TRIGGER_SOFT_CAP = 40


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def is_date(s):
    if not DATE_RE.match(s or ""):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def check_prices(root, rep):
    rows = L.load_rows(root, "prices.csv")
    if not rows:
        rep.err("prices.csv boş veya yok.")
        return {}, []
    if list(rows[0].keys()) != ["date", "ticker", "close"]:
        rep.err(f"prices.csv başlığı 'date,ticker,close' olmalı (bulunan: {','.join(rows[0].keys())}).")
    now = L.now_trt()
    today = now.date().isoformat()
    settled_today = (now.hour, now.minute) >= L.CLOSE_SETTLED_AFTER
    seen, prices = set(), {}
    for i, r in enumerate(rows, start=2):
        d, t, c = (r.get("date") or "").strip(), (r.get("ticker") or "").strip(), fnum(r.get("close"))
        if not is_date(d):
            rep.err(f"prices.csv L{i}: geçersiz tarih '{d}'.")
            continue
        if not t or c is None or c <= 0:
            rep.err(f"prices.csv L{i}: geçersiz ticker/kapanış ({t!r}, {r.get('close')!r}).")
            continue
        if (d, t) in seen:
            rep.err(f"prices.csv L{i}: yinelenen satır ({d}, {t}).")
        seen.add((d, t))
        if date.fromisoformat(d).weekday() >= 5:
            rep.err(f"prices.csv L{i}: {d} hafta sonu — seans yok.")
        if d > today:
            rep.err(f"prices.csv L{i}: gelecek tarih {d}.")
        elif d == today and not settled_today:
            rep.err(f"prices.csv L{i}: {d} BUGÜN ve saat {now:%H:%M} TRT < 18:15 — kapanış henüz "
                    f"kesinleşmedi; bu bir INTRADAY değerdir (METHODOLOGY §3.2). Satırı sil.")
        prices.setdefault(t, {})[d] = c

    if L.BENCH not in prices:
        rep.err(f"prices.csv içinde {L.BENCH} yok.")
        return prices, []
    bench_dates = sorted(prices[L.BENCH])
    pos = {d: i for i, d in enumerate(bench_dates)}
    for t, ser in prices.items():
        extra = sorted(d for d in ser if d not in pos)
        if extra:
            rep.err(f"prices.csv: {t} için {L.BENCH}'de OLMAYAN tarih(ler) var: {', '.join(extra[:5])} "
                    f"— ATOMİK SEANS kuralı (seans ya tüm semboller için yazılır ya hiç).")
        if t == L.BENCH:
            continue
        ds = sorted(d for d in ser if d in pos)
        for a, b in zip(ds, ds[1:]):
            # yalnızca ARDIŞIK seanslar: arada delik varsa çok günlük hareket limite takılmaz
            if pos[b] - pos[a] != 1:
                continue
            mv = (ser[b] / ser[a] - 1) * 100
            if abs(mv) > 10.5:
                rep.warn(f"prices.csv: {t} {a}→{b} %{mv:+.1f} — BIST günlük limiti ±%10; "
                         f"veri hatası veya bölünme/bedelsiz olabilir, kaynağı doğrula.")
    return prices, bench_dates


def check_positions(root, rep, prices, bench_dates):
    rows = L.load_rows(root, "positions.csv")
    if not rows:
        rep.err("positions.csv boş veya yok.")
        return rows
    as_of = bench_dates[-1] if bench_dates else ""
    open_seen = set()
    for i, p in enumerate(rows, start=2):
        t, st = (p.get("ticker") or "").strip(), (p.get("status") or "").strip()
        ed, xd = (p.get("entry_date") or "").strip(), (p.get("exit_date") or "").strip()
        tag = f"positions.csv L{i} ({t})"
        if st not in ("open", "closed", "watchlist"):
            rep.err(f"{tag}: geçersiz status '{st}' (open/closed/watchlist).")
        if not is_date(ed):
            rep.err(f"{tag}: geçersiz entry_date '{ed}'.")
            continue
        if st == "open":
            if t in open_seen:
                rep.err(f"{tag}: aynı isim için ikinci AÇIK kayıt.")
            open_seen.add(t)
            if xd:
                rep.err(f"{tag}: açık pozisyonda exit_date dolu ({xd}).")
            if fnum(p.get("current_stop")) is None:
                rep.err(f"{tag}: açık pozisyonda current_stop sayı değil.")
        if st == "closed":
            if not is_date(xd):
                rep.err(f"{tag}: kapanmış pozisyonda exit_date yok/geçersiz.")
                continue
            if xd < ed:
                rep.err(f"{tag}: exit_date {xd} < entry_date {ed}.")
            if xd > as_of:
                rep.err(f"{tag}: exit_date {xd} > son kesinleşmiş seans {as_of} — çıkış kesinleşmiş "
                        f"bir kapanışa demirlenir (METHODOLOGY §4).")
            xc = fnum(p.get("exit_close"))
            if xc is None:
                rep.err(f"{tag}: kapanmış pozisyonda exit_close yok.")
            else:
                px = prices.get(t, {}).get(xd)
                if px is None:
                    rep.err(f"{tag}: çıkış tarihi {xd} için prices.csv satırı yok.")
                elif abs(px - xc) / xc > 0.005:
                    rep.err(f"{tag}: exit_close {xc} ≠ prices.csv {xd} kapanışı {px} (>%0,5).")
        ec = fnum(p.get("entry_close"))
        px = prices.get(t, {}).get(ed)
        if px is None:
            if ed <= as_of:
                rep.err(f"{tag}: giriş tarihi {ed} için prices.csv satırı yok.")
            else:
                rep.warn(f"{tag}: giriş {ed} henüz kesinleşmedi — entry_close PROVİZYONEL, "
                         f"ilk backfill'de doğrulanmalı.")
        elif ec is not None and abs(px - ec) / ec > 0.005:
            rep.err(f"{tag}: entry_close {ec} ≠ prices.csv {ed} kapanışı {px} (>%0,5). Giriş günü artık "
                    f"kesinleşti: entry_close'u {px} yap (seans içi değer report_price'ta kalır — METHODOLOGY §4).")
    return rows


def check_coverage(rep, prices, positions, bench_dates):
    """METHODOLOGY §6.2 — v1'in kök sebebi: izlenen isimde delik OLAMAZ."""
    if not bench_dates:
        return
    as_of = bench_dates[-1]
    windows = {}
    for p in positions:
        t, st = p["ticker"].strip(), p["status"].strip()
        ed, xd = p["entry_date"].strip(), (p.get("exit_date") or "").strip()
        if not is_date(ed):
            continue
        if st == "closed" and is_date(xd):
            after = [d for d in bench_dates if d > xd][: L.TRACK_SESSIONS]
            end = after[-1] if after else xd
        else:
            end = as_of
        lo, hi = windows.get(t, (ed, end))
        windows[t] = (min(lo, ed), max(hi, end))
    for t, (lo, hi) in sorted(windows.items()):
        holes = [d for d in bench_dates if lo <= d <= hi and d not in prices.get(t, {})]
        if holes:
            rep.err(f"prices.csv: {t} izleme penceresinde ({lo} → {hi}) {len(holes)} eksik seans: "
                    f"{', '.join(holes[:6])}{' …' if len(holes) > 6 else ''} — METHODOLOGY §6.2 "
                    f"(çıkan isim {L.TRACK_SESSIONS} seans izlenir).")


def check_weights(root, rep, positions):
    rows = L.load_rows(root, "weights.csv")
    if not rows:
        rep.err("weights.csv boş veya yok.")
        return
    by_date = {}
    for i, r in enumerate(rows, start=2):
        d, t, w = (r.get("date") or "").strip(), (r.get("ticker") or "").strip(), fnum(r.get("weight_pct"))
        if not is_date(d) or not t or w is None or w < 0:
            rep.err(f"weights.csv L{i}: geçersiz satır ({d!r}, {t!r}, {r.get('weight_pct')!r}).")
            continue
        if t in by_date.setdefault(d, {}):
            rep.err(f"weights.csv L{i}: {d} için {t} iki kez yazılmış.")
        by_date[d][t] = (w, fnum(r.get("delta_pp")), i)
    dates = sorted(by_date)
    for k, d in enumerate(dates):
        tot = sum(v[0] for v in by_date[d].values())
        if abs(tot - 100) > 0.01:
            rep.err(f"weights.csv {d}: ağırlık toplamı %{tot:g} ≠ 100.")
        if k == 0:
            continue
        prev = by_date[dates[k - 1]]
        for t, (w, dl, i) in by_date[d].items():
            exp = w - prev.get(t, (0.0,))[0]
            if dl is None or abs(dl - exp) > 0.01:
                rep.err(f"weights.csv L{i}: {d} {t} delta_pp={dl} ama ağırlık farkı {exp:+g}.")
        for t, (w, _, _) in prev.items():
            if w > 0 and t not in by_date[d]:
                rep.err(f"weights.csv {d}: dün ağırlığı olan {t} bugün YOK — sıfırlanıyorsa "
                        f"'%0, Δ −{w:g}' satırı yazılmalı.")
    last = dates[-1]
    open_t = {p["ticker"].strip() for p in positions if p["status"].strip() == "open"}
    for t, (w, _, i) in by_date[last].items():
        if t != L.CASH and w > 0 and t not in open_t:
            rep.err(f"weights.csv L{i}: {last} {t} %{w:g} ağırlık taşıyor ama positions.csv'de AÇIK değil.")
    for t in sorted(open_t):
        if by_date[last].get(t, (0,))[0] <= 0:
            rep.err(f"weights.csv {last}: {t} positions.csv'de AÇIK ama ağırlığı yok/sıfır.")


def check_triggers(root, rep, positions):
    rows = L.load_rows(root, "triggers.csv")
    if not rows:
        rep.err("triggers.csv boş veya yok.")
        return
    held = {p["ticker"].strip() for p in positions if p["status"].strip() in ("open", "watchlist")}
    gone = {p["ticker"].strip() for p in positions if p["status"].strip() == "closed"} - held
    per_day, active = {}, 0
    for i, r in enumerate(rows, start=2):
        d, st, sc = (r.get("date_set") or "").strip(), (r.get("status") or "").strip(), (r.get("scope") or "").strip()
        if not is_date(d):
            rep.err(f"triggers.csv L{i}: geçersiz date_set '{d}'.")
            continue
        if st not in ("active", "fired", "expired"):
            rep.err(f"triggers.csv L{i}: geçersiz status '{st}' (active/fired/expired).")
        if not (r.get("condition") or "").strip() or not (r.get("action") or "").strip():
            rep.err(f"triggers.csv L{i}: koşul/aksiyon boş.")
        if st == "active":
            active += 1
            if sc in gone:
                rep.err(f"triggers.csv L{i}: {sc} pozisyonu KAPALI ama tetik hâlâ 'active' — aynı rutinde "
                        f"expire edilmeli (v1'de 20 bayat tetik birikmişti).")
        per_day[d] = per_day.get(d, 0) + 1
    for d, n in sorted(per_day.items()):
        if d >= L.TRIGGER_BUDGET_FROM and n > L.TRIGGER_BUDGET:
            rep.err(f"triggers.csv: {d} tarihinde {n} yeni tetik açılmış — KURAL 9(c) bütçesi "
                    f"{L.TRIGGER_BUDGET}. Fazlasını sil veya mevcut bir tetiği güncelle.")
    if active > ACTIVE_TRIGGER_SOFT_CAP:
        rep.warn(f"triggers.csv: {active} aktif tetik (> {ACTIVE_TRIGGER_SOFT_CAP}) — tetik enflasyonu; "
                 f"artık ölçülmeyen/bayat olanları expire et.")


def check_text_caps(root, rep):
    keycol = {"weights.csv": "date", "triggers.csv": "date_set", "positions.csv": "exit_date"}
    for (fname, col), cap in L.TEXT_CAPS.items():
        for i, r in enumerate(L.load_rows(root, fname), start=2):
            d = (r.get(keycol[fname]) or "").strip()
            n = len((r.get(col) or "").strip())
            if d >= L.TEXT_CAPS_FROM and n > cap:
                rep.err(f"{fname} L{i}: '{col}' {n} karakter > tavan {cap} (METHODOLOGY §6.3). "
                        f"Özetle; ayrıntıyı rapora yaz ve 'bkz. rapor {d}' diye atıf ver.")


def check_report(root, rep):
    reports = sorted((Path(root) / "reports").glob("????-??-??-bist100.md"))
    weights = L.load_rows(root, "weights.csv")
    if not reports or not weights:
        return
    latest = reports[-1]
    rdate = latest.name[:10]
    wdate = max(r["date"] for r in weights)
    if rdate < wdate:
        rep.warn(f"rapor: weights.csv {wdate} için satır içeriyor ama reports/{wdate}-bist100.md henüz yok "
                 f"(rapor yazılmadan önce çalıştırıldıysa normal).")
        return
    if rdate < VERBATIM_FROM:
        return
    try:
        out = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "compute_perf.py"),
                              "--root", str(root)], capture_output=True, text=True, timeout=120)
    except Exception as e:  # pragma: no cover
        rep.err(f"compute_perf.py çalıştırılamadı: {e}")
        return
    if out.returncode != 0:
        rep.err(f"compute_perf.py çıkış kodu {out.returncode}: {out.stdout.strip()[:200]}")
        return
    text = latest.read_text(encoding="utf-8")
    section, need = None, []
    for line in out.stdout.splitlines():
        if line.startswith("#### "):
            section = line[5:7]
        elif line.startswith("<details>"):
            section = None  # günlük seri ve sonrası özet satırı değildir
        elif line.startswith("**") and section in ("A)", "B)", "C)", "D)", "E)"):
            need.append((section, line.strip()))
    has_e = "#### E) MODEL PORTFÖY" in text
    for sec, line in need:
        if sec == "E)" and rdate < SECTION_E_FROM and not has_e:
            continue
        if line not in text:
            rep.err(f"rapor {latest.name}: compute_perf §{sec[0]} satırı raporda AYNEN yok → "
                    f"«{L.clip(line, 110)}». Script'i ledger'ın SON hâliyle yeniden çalıştırıp "
                    f"çıktıyı AYNEN yapıştır (elle düzeltme yasak).")


def check_privacy(root, rep):
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, timeout=30)
    except Exception:
        return
    if out.returncode != 0:
        return
    bad = [f for f in out.stdout.splitlines() if FORBIDDEN_PATHS.search(f)]
    if bad:
        rep.err("gizlilik: yerel çalışma dosyası git'te izleniyor — şu yol(lar) git'ten çıkarılmalı: "
                + ", ".join(bad[:5]))


def main():
    ap = argparse.ArgumentParser(description="finance-agent v2 ledger doğrulayıcı")
    ap.add_argument("--root", default=None)
    ap.add_argument("--no-report", action="store_true", help="rapor ↔ compute_perf denetimini atla")
    ap.add_argument("--no-git", action="store_true", help="gizlilik (git ls-files) denetimini atla")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else L.ROOT

    rep = Report()
    prices, bench_dates = check_prices(root, rep)
    positions = check_positions(root, rep, prices, bench_dates)
    if positions:
        check_coverage(rep, prices, positions, bench_dates)
        check_weights(root, rep, positions)
        check_triggers(root, rep, positions)
    check_text_caps(root, rep)
    if not args.no_report:
        check_report(root, rep)
    if not args.no_git:
        check_privacy(root, rep)

    for w in rep.warnings:
        print(f"UYARI  {w}")
    for e in rep.errors:
        print(f"HATA   {e}")
    as_of = bench_dates[-1] if bench_dates else "—"
    print(f"SONUÇ: {len(rep.errors)} HATA · {len(rep.warnings)} UYARI · as-of {as_of} · "
          f"{L.now_trt():%Y-%m-%d %H:%M} TRT — "
          + ("LEDGER GEÇERLİ ✅" if not rep.errors else "COMMIT ETME, önce hataları düzelt ❌"))
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
