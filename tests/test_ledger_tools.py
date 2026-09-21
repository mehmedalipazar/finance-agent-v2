# -*- coding: utf-8 -*-
"""
finance-agent v2 — script testleri (yalnızca stdlib; `python3 -m unittest discover -s tests`).

Her test, 2026-09-21 incelemesinde bulunan somut bir hatayı ya da v1 kök sebebini kilitler:
sentetik bir defter kurulur, script `--root` ile o deftere karşı çalıştırılır.
"""
import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ledger as L  # noqa: E402

POS_COLS = ["ticker", "sector", "entry_date", "report_price", "entry_close", "initial_stop",
            "current_stop", "initial_target", "status", "exit_date", "exit_close", "exit_reason"]


def weekdays(start, n):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


D = weekdays("2026-01-05", 8)


class Ledger:
    """Geçici, geçerli bir örnek defter: AAA açık, BBB D[3]'te kapanmış ve izlenmeye devam ediyor."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="fa2-test-"))
        (self.root / "data").mkdir()
        (self.root / "reports").mkdir()
        self.prices = ([(d, "XU100", 100.0) for d in D]
                       + [(d, "AAA", 100.0 + i) for i, d in enumerate(D)]
                       + [(d, "BBB", [50, 49, 47, 45, 46, 48, 50, 52][i]) for i, d in enumerate(D)])
        self.positions = [
            dict(ticker="AAA", sector="X", entry_date=D[0], report_price=100, entry_close=100,
                 initial_stop=85, current_stop=85, initial_target=140, status="open"),
            dict(ticker="BBB", sector="Y", entry_date=D[0], report_price=50, entry_close=50,
                 initial_stop=46, current_stop=46, initial_target=70, status="closed",
                 exit_date=D[3], exit_close=45, exit_reason="stop"),
        ]
        self.weights = [(D[0], "AAA", 50, 50, "kurulus"), (D[0], "BBB", 30, 30, "kurulus"),
                        (D[0], "CASH", 20, 20, "kurulus"),
                        (D[4], "AAA", 50, 0, "tetik yok"), (D[4], "BBB", 0, -30, "stop kesimi"),
                        (D[4], "CASH", 50, 30, "kesimden bosalan")]
        self.triggers = [(D[0], "AAA", "3 ardisik settled <85", "tam kesim", "active", ""),
                         (D[0], "BBB", "settled <46", "tam kesim", "fired", "D3")]
        self.flush()

    def flush(self):
        def dump(name, header, rows):
            with open(self.root / "data" / name, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(header)
                w.writerows(rows)
        dump("prices.csv", ["date", "ticker", "close"], self.prices)
        dump("positions.csv", POS_COLS, [[p.get(c, "") for c in POS_COLS] for p in self.positions])
        dump("weights.csv", ["date", "ticker", "weight_pct", "delta_pp", "trigger"], self.weights)
        dump("triggers.csv", ["date_set", "scope", "condition", "action", "status", "notes"], self.triggers)

    def run(self, script, *args):
        p = subprocess.run([sys.executable, str(SCRIPTS / script), "--root", str(self.root), *args],
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.lg = Ledger()
        self.addCleanup(self.lg.close)

    def validate(self, *args):
        return self.lg.run("validate_ledger.py", "--no-git", *args)


class ComputePerf(Base):
    def test_headline_counts_closed_positions(self):
        """v1 hatası: manşet yalnızca açık pozisyonları sayıyordu."""
        rc, out = self.lg.run("compute_perf.py")
        self.assertEqual(rc, 0, out)
        self.assertIn("**Alınmış tüm pozisyonlar (2):**", out)

    def test_cut_on_as_of_is_pending_not_violation(self):
        """Çıkışı as-of seansında olan kesim §6.2 ihlali DEĞİLDİR (09-21 VAKBN sahte alarmı)."""
        self.lg.positions[1].update(exit_date=D[-1], exit_close=52)
        self.lg.flush()
        rc, out = self.lg.run("compute_perf.py")
        self.assertEqual(rc, 0, out)
        self.assertIn("henüz ölçülemez (BBB", out)
        self.assertNotIn("ihlali, VERİ EKSİĞİ", out)

    def test_untracked_cut_is_a_violation(self):
        """v1 kök sebebi: çıkan ismin fiyatı defterden düşerse kesim ölçülemez → ihlal."""
        self.lg.prices = [r for r in self.lg.prices if not (r[1] == "BBB" and r[0] > D[3])]
        self.lg.flush()
        rc, out = self.lg.run("compute_perf.py")
        self.assertEqual(rc, 0, out)
        self.assertIn("1 kesim ölçülemedi (BBB", out)
        self.assertIn("METHODOLOGY §6.2 ihlali", out)

    def test_hold_leg_benchmark_stops_with_the_stock(self):
        """İzleme D[5]'te kesilmişse XU100 bacağı da D[5]'te durur (as-of'a uzamaz)."""
        self.lg.prices = [r for r in self.lg.prices if not (r[1] == "BBB" and r[0] > D[5])]
        # izleme bittikten SONRA endeks ikiye katlanıyor: eski kod bunu "tutsaydık" alfasına yazardı
        self.lg.prices = [(d, t, 200.0 if t == "XU100" and d > D[5] else c) for d, t, c in self.lg.prices]
        self.lg.flush()
        rc, out = self.lg.run("compute_perf.py")
        self.assertEqual(rc, 0, out)
        row = next(l for l in out.splitlines() if l.startswith("| BBB") and "pp" in l)
        # giriş 50 → D[5] 48 = −%4,00; XU100 D[0]→D[5] = %0 → tutsaydık alfa −%4,00
        self.assertIn("−%4,00", row)
        self.assertIn(f"48,00 ({D[5]})", row)
        self.assertIn(f"izleme {D[5]}'de kesilmiş (2/60 seans)", out)

    def test_model_portfolio_trades_only_on_weight_change(self):
        """§E: Δ=0 gününde yeniden dengeleme YOK (günlük dengeleme 1.125 TL verirdi)."""
        self.lg.prices = ([(d, "XU100", 100.0) for d in D[:3]]
                          + [(D[0], "AAA", 100.0), (D[1], "AAA", 200.0), (D[2], "AAA", 100.0)])
        self.lg.positions = self.lg.positions[:1]
        self.lg.weights = [(d, t, w, dl, "x") for d, dl in ((D[0], 50), (D[1], 0), (D[2], 0))
                           for t, w in (("AAA", 50), ("CASH", 50))]
        self.lg.triggers = self.lg.triggers[:1]
        self.lg.flush()
        rc, out = self.lg.run("compute_perf.py")
        self.assertEqual(rc, 0, out)
        self.assertIn("**1.000 TL → 1.000 TL**", out)

    def test_runs_without_open_positions(self):
        self.lg.positions = self.lg.positions[1:]
        self.lg.flush()
        rc, out = self.lg.run("compute_perf.py")
        self.assertEqual(rc, 0, out)
        self.assertIn("*Açık pozisyon yok.*", out)


class Validator(Base):
    def assertError(self, needle, *args):
        rc, out = self.validate(*args)
        self.assertEqual(rc, 1, out)
        self.assertIn(needle, out)

    def test_clean_ledger_passes(self):
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        self.assertIn("LEDGER GEÇERLİ", out)

    def test_duplicate_price_row(self):
        self.lg.prices.append((D[2], "AAA", 102.0))
        self.lg.flush()
        self.assertError("yinelenen satır")

    def test_future_dated_close(self):
        self.lg.prices.append(((date.today() + timedelta(days=3)).isoformat(), "XU100", 100.0))
        self.lg.flush()
        rc, out = self.validate()
        self.assertEqual(rc, 1, out)
        self.assertTrue("gelecek tarih" in out or "hafta sonu" in out, out)

    def test_dropped_exited_name_is_the_v1_root_cause(self):
        """§6.2: kapanmış isim 60 seans izlenir; delik = HATA."""
        self.lg.prices = [r for r in self.lg.prices if not (r[1] == "BBB" and r[0] > D[4])]
        self.lg.flush()
        self.assertError("BBB izleme penceresinde")

    def test_partial_session_breaks_atomicity(self):
        self.lg.prices = [r for r in self.lg.prices if not (r[1] == "XU100" and r[0] == D[-1])]
        self.lg.flush()
        self.assertError("ATOMİK SEANS")

    def test_weights_must_sum_to_100(self):
        self.lg.weights[-1] = (D[4], "CASH", 45, 25, "x")
        self.lg.flush()
        self.assertError("≠ 100")

    def test_delta_must_match_weight_change(self):
        self.lg.weights[3] = (D[4], "AAA", 50, 5, "x")
        self.lg.flush()
        self.assertError("delta_pp=5.0 ama ağırlık farkı +0")

    def test_weight_on_closed_name(self):
        self.lg.weights[4] = (D[4], "BBB", 10, -20, "x")
        self.lg.weights[5] = (D[4], "CASH", 40, 20, "x")
        self.lg.flush()
        self.assertError("AÇIK değil")

    def test_stale_active_trigger_on_closed_name(self):
        """v1'de 20 bayat tetik 'active' kalmıştı."""
        self.lg.triggers.append((D[1], "BBB", "settled >55", "geri al", "active", ""))
        self.lg.flush()
        self.assertError("pozisyonu KAPALI ama tetik hâlâ 'active'")

    def test_trigger_budget(self):
        """KURAL 9(c): günde en fazla 3 yeni tetik (v1: Eylül'de 106)."""
        self.lg.triggers += [("2026-09-22", "AAA", f"kosul {i}", "aksiyon", "active", "") for i in range(4)]
        self.lg.flush()
        self.assertError("4 yeni tetik açılmış")

    def test_text_cap_keeps_the_ledger_small(self):
        self.lg.weights += [("2026-09-22", "AAA", 50, 0, "x" * 281), ("2026-09-22", "BBB", 0, 0, "x"),
                            ("2026-09-22", "CASH", 50, 0, "x")]
        self.lg.flush()
        self.assertError("281 karakter > tavan 280", "--no-report")

    def test_exit_close_must_match_the_settled_close(self):
        self.lg.positions[1]["exit_close"] = 47
        self.lg.flush()
        self.assertError("exit_close 47.0 ≠ prices.csv")

    DAY = "2026-09-22"

    def _todays_weights(self):
        day = self.DAY
        self.lg.weights += [(day, "AAA", 50, 0, "x"), (day, "BBB", 0, 0, "x"), (day, "CASH", 50, 0, "x")]
        self.lg.flush()

    def _write_report(self, body):
        (self.lg.root / "reports" / f"{self.DAY}-bist100.md").write_text(body, encoding="utf-8")

    def test_report_must_contain_compute_perf_output_verbatim(self):
        self._todays_weights()
        _, perf = self.lg.run("compute_perf.py")
        self._write_report("# Rapor\n\n" + perf)
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)

    def test_output_pasted_before_the_last_ledger_edit_is_caught(self):
        """Script ledger'ın SON hâlinden önce çalıştırıldıysa rapor bayattır."""
        _, perf = self.lg.run("compute_perf.py")
        self._todays_weights()  # çıktı alındıktan SONRA defter değişti
        self._write_report("# Rapor\n\n" + perf)
        self.assertError("raporda AYNEN yok")

    def test_hand_edited_headline_is_caught(self):
        self._todays_weights()
        _, perf = self.lg.run("compute_perf.py")
        line = next(l for l in perf.splitlines() if l.startswith("**Alınmış tüm pozisyonlar"))
        self._write_report("# Rapor\n\n" + perf.replace(line, line.replace("(2)", "(1)")))
        self.assertError("compute_perf §C satırı raporda AYNEN yok")

    def test_missing_model_portfolio_section_is_caught(self):
        self._todays_weights()
        _, perf = self.lg.run("compute_perf.py")
        self._write_report("# Rapor\n\n" + perf.split("#### E)")[0])
        self.assertError("compute_perf §E satırı raporda AYNEN yok")

    @unittest.skipUnless(shutil.which("git"), "git yok")
    def test_prompt_file_in_repo_is_blocked(self):
        """Yerel çalışma dosyaları (routine/) git'e girmemelidir."""
        root = self.lg.root
        (root / "routine").mkdir()
        (root / "routine" / "PROMPT.md").write_text("gizli", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        rc, out = self.lg.run("validate_ledger.py")
        self.assertEqual(rc, 1, out)
        self.assertIn("gizlilik", out)
        self.assertIn("routine/PROMPT.md", out)


class Tracking(unittest.TestCase):
    def test_exited_name_stays_on_the_backfill_list_for_60_sessions(self):
        days = weekdays("2026-01-05", 70)
        pos = [dict(ticker="AAA", status="open", exit_date=""),
               dict(ticker="BBB", status="closed", exit_date=days[20]),   # 49 seans önce → izlenir
               dict(ticker="CCC", status="closed", exit_date=days[5]),    # 64 seans önce → düşer
               dict(ticker="DDD", status="watchlist", exit_date=days[1])]
        trk = L.tracking(pos, days)
        self.assertEqual(L.backfill_list(trk), ["XU100", "AAA", "DDD", "BBB"])
        self.assertEqual(trk["closed"], [("BBB", days[20], 49)])
        self.assertEqual(trk["dropped"], [("CCC", days[5], 64)])

    def test_reopened_name_is_listed_once_as_open(self):
        days = weekdays("2026-01-05", 10)
        pos = [dict(ticker="AAA", status="closed", exit_date=days[2]),
               dict(ticker="AAA", status="open", exit_date="")]
        trk = L.tracking(pos, days)
        self.assertEqual((trk["open"], trk["closed"]), (["AAA"], []))

    def test_todays_close_is_not_settled_before_1815_trt(self):
        mon_morning = datetime(2026, 9, 21, 10, 30, tzinfo=L.TRT)
        mon_evening = datetime(2026, 9, 21, 18, 30, tzinfo=L.TRT)
        self.assertEqual(L.candidate_sessions("2026-09-17", mon_morning), ["2026-09-18"])
        self.assertEqual(L.candidate_sessions("2026-09-17", mon_evening), ["2026-09-18", "2026-09-21"])


class Brief(Base):
    def test_brief_lists_backfill_symbols_and_active_triggers(self):
        rc, out = self.lg.run("ledger_brief.py")
        self.assertEqual(rc, 0, out)
        self.assertIn("[XU100, AAA, BBB]", out)
        self.assertIn("BBB (çıkış " + D[3], out)
        self.assertIn("3 ardisik settled <85", out)
        self.assertNotIn("settled <46", out)  # fired tetik özette yer kaplamaz


if __name__ == "__main__":
    unittest.main()
