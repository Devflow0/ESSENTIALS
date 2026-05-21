"""
AVEETS Management System — Stress Test Suite
=============================================
Tests:  1. HTTP response times & status codes (sequential)
        2. Concurrent connection load (thread pool)
        3. Rapid-fire burst requests
        4. Database read/write stress
        5. Large payload / form simulation
        6. Static asset / websocket endpoint probing
        7. Memory baseline via DB size growth
"""

import requests
import time
import statistics
import sqlite3
import concurrent.futures
import json
import os
import sys
from datetime import date, timedelta
import random
import string
import traceback

BASE_URL = "http://localhost:8501"
DB_NAME  = "alpr_data.db"

# ── Colours for terminal output ───────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

results_summary = []  # collect per-test verdicts


def header(title):
    print(f"\n{BOLD}{CYAN}{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}{RESET}\n")


def verdict(test_name, passed, detail=""):
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    results_summary.append((test_name, passed, detail))
    print(f"  {BOLD}[{status}{BOLD}]{RESET}  {test_name}  {YELLOW}{detail}{RESET}")


def fmt_ms(seconds):
    return f"{seconds*1000:.1f}ms"


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Sequential HTTP Response Times
# ═══════════════════════════════════════════════════════════════════════════════
def test_sequential_response_times(n=20):
    header("TEST 1 — Sequential HTTP Response Times")
    print(f"  Sending {n} sequential GET requests to {BASE_URL} …\n")
    times = []
    errors = 0
    status_codes = {}

    for i in range(n):
        try:
            t0 = time.perf_counter()
            r = requests.get(BASE_URL, timeout=15)
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            status_codes[r.status_code] = status_codes.get(r.status_code, 0) + 1
        except Exception as e:
            errors += 1
            print(f"    Request {i+1}: {RED}ERROR{RESET} — {e}")

    if times:
        avg   = statistics.mean(times)
        med   = statistics.median(times)
        p95   = sorted(times)[int(len(times)*0.95)]
        mn    = min(times)
        mx    = max(times)
        stdev = statistics.stdev(times) if len(times) > 1 else 0

        print(f"  {BOLD}Results:{RESET}")
        print(f"    Requests OK : {len(times)}/{n}")
        print(f"    Errors      : {errors}")
        print(f"    Status codes: {status_codes}")
        print(f"    Avg         : {fmt_ms(avg)}")
        print(f"    Median      : {fmt_ms(med)}")
        print(f"    P95         : {fmt_ms(p95)}")
        print(f"    Min / Max   : {fmt_ms(mn)} / {fmt_ms(mx)}")
        print(f"    Std Dev     : {fmt_ms(stdev)}")

        verdict("Sequential response (avg < 2s)", avg < 2.0, f"avg={fmt_ms(avg)}")
        verdict("Sequential response (P95 < 3s)", p95 < 3.0, f"P95={fmt_ms(p95)}")
        verdict("No HTTP errors", errors == 0, f"errors={errors}")
    else:
        verdict("Sequential requests", False, "All requests failed")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Concurrent Connection Load
# ═══════════════════════════════════════════════════════════════════════════════
def test_concurrent_load(workers=15, requests_per_worker=5):
    header("TEST 2 — Concurrent Connection Load")
    total = workers * requests_per_worker
    print(f"  {workers} threads × {requests_per_worker} requests = {total} total …\n")

    times = []
    errors = []

    def worker_fn(worker_id):
        local_times = []
        for i in range(requests_per_worker):
            try:
                t0 = time.perf_counter()
                r = requests.get(BASE_URL, timeout=20)
                elapsed = time.perf_counter() - t0
                local_times.append(elapsed)
            except Exception as e:
                errors.append((worker_id, i, str(e)))
        return local_times

    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_fn, w) for w in range(workers)]
        for f in concurrent.futures.as_completed(futures):
            times.extend(f.result())
    wall_time = time.perf_counter() - t_start

    if times:
        avg = statistics.mean(times)
        p95 = sorted(times)[int(len(times)*0.95)]
        rps = len(times) / wall_time

        print(f"  {BOLD}Results:{RESET}")
        print(f"    Successful   : {len(times)}/{total}")
        print(f"    Failed       : {len(errors)}")
        print(f"    Wall time    : {wall_time:.2f}s")
        print(f"    Throughput   : {rps:.1f} req/s")
        print(f"    Avg latency  : {fmt_ms(avg)}")
        print(f"    P95 latency  : {fmt_ms(p95)}")

        verdict("Concurrent load (avg < 3s)", avg < 3.0, f"avg={fmt_ms(avg)}")
        verdict("Concurrent load (>1 req/s)", rps > 1.0, f"throughput={rps:.1f} req/s")
        verdict("Concurrent error rate < 10%", len(errors)/total < 0.10, f"{len(errors)}/{total} failed")
    else:
        verdict("Concurrent load", False, "All requests failed")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Burst Requests (rapid fire)
# ═══════════════════════════════════════════════════════════════════════════════
def test_burst(count=50):
    header("TEST 3 — Burst Requests (rapid-fire)")
    print(f"  Firing {count} requests as fast as possible …\n")

    session = requests.Session()
    times = []
    errors = 0

    t_start = time.perf_counter()
    for _ in range(count):
        try:
            t0 = time.perf_counter()
            r = session.get(BASE_URL, timeout=20)
            times.append(time.perf_counter() - t0)
        except:
            errors += 1
    wall_time = time.perf_counter() - t_start

    if times:
        rps = len(times) / wall_time
        avg = statistics.mean(times)
        mx  = max(times)

        print(f"  {BOLD}Results:{RESET}")
        print(f"    OK / Errors  : {len(times)} / {errors}")
        print(f"    Wall time    : {wall_time:.2f}s")
        print(f"    Throughput   : {rps:.1f} req/s")
        print(f"    Avg latency  : {fmt_ms(avg)}")
        print(f"    Max latency  : {fmt_ms(mx)}")

        verdict("Burst throughput (>2 req/s)", rps > 2.0, f"{rps:.1f} req/s")
        verdict("Burst max latency < 10s", mx < 10.0, f"max={fmt_ms(mx)}")
    else:
        verdict("Burst requests", False, "All failed")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Database Read/Write Stress
# ═══════════════════════════════════════════════════════════════════════════════
def test_database_stress(writes=200, reads=500):
    header("TEST 4 — Database Read/Write Stress")
    print(f"  {writes} INSERTs + {reads} SELECTs on scheduled_meetings …\n")

    # ── WRITES ────────────────────────────────────────────────────────────────
    write_times = []
    inserted_ids = []
    for i in range(writes):
        title = f"StressTest-{i}-{''.join(random.choices(string.ascii_letters, k=6))}"
        mdate = (date.today() + timedelta(days=random.randint(1, 90))).isoformat()
        room  = random.choice(["General Staff Briefing", "Security Coordination",
                                "Management Sync", "Private 1-on-1"])
        priority = random.choice(["Normal", "High", "Urgent"])

        try:
            t0 = time.perf_counter()
            with sqlite3.connect(DB_NAME) as conn:
                cur = conn.execute(
                    """INSERT INTO scheduled_meetings
                       (title, room, meeting_date, start_time, end_time, priority,
                        status, agenda, attendees, organizer, created_by)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (title, room, mdate, "09:00:00", "10:00:00", priority,
                     "Scheduled", f"Stress test agenda item {i}",
                     "User-A, User-B", "StressBot", "stress_test")
                )
                conn.commit()
                inserted_ids.append(cur.lastrowid)
            write_times.append(time.perf_counter() - t0)
        except Exception as e:
            print(f"    WRITE error: {e}")

    w_avg = statistics.mean(write_times) if write_times else 0
    w_max = max(write_times) if write_times else 0

    # ── READS ─────────────────────────────────────────────────────────────────
    read_times = []
    queries = [
        "SELECT * FROM scheduled_meetings ORDER BY meeting_date DESC",
        "SELECT * FROM scheduled_meetings WHERE status='Scheduled'",
        "SELECT * FROM scheduled_meetings WHERE priority='Urgent'",
        f"SELECT * FROM scheduled_meetings WHERE meeting_date >= '{date.today().isoformat()}'",
        "SELECT COUNT(*) FROM scheduled_meetings",
    ]
    for i in range(reads):
        q = queries[i % len(queries)]
        try:
            t0 = time.perf_counter()
            with sqlite3.connect(DB_NAME) as conn:
                rows = conn.execute(q).fetchall()
            read_times.append(time.perf_counter() - t0)
        except Exception as e:
            print(f"    READ error: {e}")

    r_avg = statistics.mean(read_times) if read_times else 0
    r_max = max(read_times) if read_times else 0

    # ── CLEANUP ───────────────────────────────────────────────────────────────
    cleanup_start = time.perf_counter()
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM scheduled_meetings WHERE created_by='stress_test'")
        conn.commit()
    cleanup_time = time.perf_counter() - cleanup_start

    print(f"  {BOLD}WRITE Results ({len(write_times)} ops):{RESET}")
    print(f"    Avg write    : {fmt_ms(w_avg)}")
    print(f"    Max write    : {fmt_ms(w_max)}")
    print(f"  {BOLD}READ Results ({len(read_times)} ops):{RESET}")
    print(f"    Avg read     : {fmt_ms(r_avg)}")
    print(f"    Max read     : {fmt_ms(r_max)}")
    print(f"  {BOLD}Cleanup:{RESET}  {len(inserted_ids)} rows deleted in {fmt_ms(cleanup_time)}")

    verdict("DB writes (avg < 50ms)", w_avg < 0.050, f"avg={fmt_ms(w_avg)}")
    verdict("DB reads  (avg < 50ms)", r_avg < 0.050, f"avg={fmt_ms(r_avg)}")
    verdict("DB write count matches", len(write_times) == writes, f"{len(write_times)}/{writes}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5 — Concurrent Database Access
# ═══════════════════════════════════════════════════════════════════════════════
def test_concurrent_db(threads=10, ops_per_thread=30):
    header("TEST 5 — Concurrent Database Access")
    total = threads * ops_per_thread
    print(f"  {threads} threads × {ops_per_thread} mixed r/w ops = {total} …\n")

    errors = []
    times  = []

    def db_worker(wid):
        local_t = []
        for i in range(ops_per_thread):
            try:
                t0 = time.perf_counter()
                with sqlite3.connect(DB_NAME, timeout=10) as conn:
                    if i % 3 == 0:  # write
                        conn.execute(
                            """INSERT INTO scheduled_meetings
                               (title, room, meeting_date, start_time, priority,
                                status, created_by)
                               VALUES (?,?,?,?,?,?,?)""",
                            (f"ConcTest-{wid}-{i}", "Management Sync",
                             date.today().isoformat(), "09:00:00", "Normal",
                             "Scheduled", "stress_test")
                        )
                        conn.commit()
                    else:  # read
                        conn.execute("SELECT * FROM scheduled_meetings").fetchall()
                local_t.append(time.perf_counter() - t0)
            except Exception as e:
                errors.append((wid, i, str(e)))
        return local_t

    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futs = [pool.submit(db_worker, w) for w in range(threads)]
        for f in concurrent.futures.as_completed(futs):
            times.extend(f.result())
    wall = time.perf_counter() - t_start

    # cleanup
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM scheduled_meetings WHERE created_by='stress_test'")
        conn.commit()

    if times:
        avg = statistics.mean(times)
        p95 = sorted(times)[int(len(times)*0.95)]
        print(f"  {BOLD}Results:{RESET}")
        print(f"    OK / Errors  : {len(times)} / {len(errors)}")
        print(f"    Wall time    : {wall:.2f}s")
        print(f"    Avg latency  : {fmt_ms(avg)}")
        print(f"    P95 latency  : {fmt_ms(p95)}")
        if errors:
            # show first few unique error messages
            unique = set(e[2] for e in errors[:5])
            for msg in unique:
                print(f"    {RED}Error sample:{RESET} {msg}")

        verdict("Concurrent DB (avg < 100ms)", avg < 0.100, f"avg={fmt_ms(avg)}")
        verdict("Concurrent DB error rate < 5%", len(errors)/total < 0.05,
                f"{len(errors)}/{total}")
    else:
        verdict("Concurrent DB", False, "All ops failed")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6 — Streamlit Internal Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
def test_streamlit_endpoints():
    header("TEST 6 — Streamlit Internal Endpoints")
    endpoints = [
        ("Main page",       "/"),
        ("Health check",    "/_stcore/health"),
        ("Host config",     "/_stcore/host-config"),
        ("Allowed message origins", "/_stcore/allowed-message-origins"),
    ]

    for name, path in endpoints:
        try:
            t0 = time.perf_counter()
            r = requests.get(f"{BASE_URL}{path}", timeout=10)
            elapsed = time.perf_counter() - t0
            ok = r.status_code == 200
            detail = f"status={r.status_code}, time={fmt_ms(elapsed)}"
            if ok:
                detail += f", size={len(r.content)} bytes"
            verdict(f"Endpoint: {name}", ok, detail)
        except Exception as e:
            verdict(f"Endpoint: {name}", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7 — Database Integrity & Size
# ═══════════════════════════════════════════════════════════════════════════════
def test_db_integrity():
    header("TEST 7 — Database Integrity & Size")

    db_path = os.path.join(os.getcwd(), DB_NAME)
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    print(f"  Database file  : {db_path}")
    print(f"  File size      : {db_size / 1024:.1f} KB\n")

    with sqlite3.connect(DB_NAME) as conn:
        # integrity check
        result = conn.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = result[0] == "ok"
        verdict("SQLite integrity check", integrity_ok, result[0])

        # table row counts
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
        ).fetchall()]

        print(f"\n  {BOLD}Table Row Counts:{RESET}")
        for tbl in sorted(tables):
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
                print(f"    {tbl:30s} : {count:>6} rows")
            except Exception as e:
                print(f"    {tbl:30s} : {RED}ERROR{RESET} — {e}")

        # WAL mode check
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        print(f"\n  Journal mode   : {journal}")
        verdict("DB size < 100 MB", db_size < 100 * 1024 * 1024, f"{db_size/1024:.1f} KB")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 8 — Sustained Load (30-second soak)
# ═══════════════════════════════════════════════════════════════════════════════
def test_sustained_load(duration_sec=15, workers=5):
    header("TEST 8 — Sustained Load (soak test)")
    print(f"  {workers} threads hitting the app for {duration_sec}s …\n")

    stop_flag = False
    all_times = []
    all_errors = []

    def soak_worker(wid):
        session = requests.Session()
        local_times = []
        local_errors = 0
        while not stop_flag:
            try:
                t0 = time.perf_counter()
                r = session.get(BASE_URL, timeout=15)
                local_times.append(time.perf_counter() - t0)
            except:
                local_errors += 1
            time.sleep(0.05)  # small pause to avoid pure CPU spin
        return local_times, local_errors

    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(soak_worker, w) for w in range(workers)]
        time.sleep(duration_sec)
        stop_flag = True
        for f in concurrent.futures.as_completed(futures):
            t, e = f.result()
            all_times.extend(t)
            all_errors.append(e)
    wall = time.perf_counter() - t_start
    total_errors = sum(all_errors)

    if all_times:
        avg  = statistics.mean(all_times)
        p95  = sorted(all_times)[int(len(all_times)*0.95)]
        mx   = max(all_times)
        rps  = len(all_times) / wall

        # check for degradation: compare first-quarter vs last-quarter avg
        q1 = all_times[:len(all_times)//4]
        q4 = all_times[-len(all_times)//4:]
        q1_avg = statistics.mean(q1) if q1 else 0
        q4_avg = statistics.mean(q4) if q4 else 0
        degradation = ((q4_avg - q1_avg) / q1_avg * 100) if q1_avg > 0 else 0

        print(f"  {BOLD}Results:{RESET}")
        print(f"    Total requests : {len(all_times)}")
        print(f"    Total errors   : {total_errors}")
        print(f"    Wall time      : {wall:.1f}s")
        print(f"    Throughput     : {rps:.1f} req/s")
        print(f"    Avg latency    : {fmt_ms(avg)}")
        print(f"    P95 latency    : {fmt_ms(p95)}")
        print(f"    Max latency    : {fmt_ms(mx)}")
        print(f"    Q1 avg → Q4 avg: {fmt_ms(q1_avg)} → {fmt_ms(q4_avg)}  ({degradation:+.1f}%)")

        verdict("Soak throughput (>2 req/s)", rps > 2.0, f"{rps:.1f} req/s")
        verdict("Soak P95 < 5s", p95 < 5.0, f"P95={fmt_ms(p95)}")
        verdict("Soak degradation < 50%", degradation < 50, f"{degradation:+.1f}%")
        verdict("Soak error rate < 5%", total_errors / (len(all_times)+total_errors) < 0.05,
                f"{total_errors} errors")
    else:
        verdict("Sustained load", False, "No successful requests")


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════════
def print_report():
    header("FINAL STRESS TEST REPORT")
    passed = sum(1 for _, p, _ in results_summary if p)
    failed = sum(1 for _, p, _ in results_summary if not p)
    total  = len(results_summary)

    print(f"  {BOLD}Total checks : {total}{RESET}")
    print(f"  {GREEN}Passed       : {passed}{RESET}")
    print(f"  {RED}Failed       : {failed}{RESET}")
    score = (passed / total * 100) if total else 0
    print(f"  {BOLD}Score        : {score:.0f}%{RESET}\n")

    if failed:
        print(f"  {RED}{BOLD}Failed checks:{RESET}")
        for name, p, detail in results_summary:
            if not p:
                print(f"    ✗ {name}  — {detail}")
    print()

    # Overall grade
    if score >= 95:
        grade, colour = "A+  — Excellent", GREEN
    elif score >= 85:
        grade, colour = "A   — Very Good", GREEN
    elif score >= 70:
        grade, colour = "B   — Good", YELLOW
    elif score >= 50:
        grade, colour = "C   — Fair", YELLOW
    else:
        grade, colour = "D   — Needs Improvement", RED

    print(f"  {BOLD}Overall Grade: {colour}{grade}{RESET}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════╗")
    print(f"║         AVEETS Management System — Stress Test Suite           ║")
    print(f"║         Target: {BASE_URL:44s} ║")
    print(f"╚══════════════════════════════════════════════════════════════════╝{RESET}\n")

    # Quick connectivity check
    try:
        r = requests.get(BASE_URL, timeout=5)
        print(f"  {GREEN}✓ Server is reachable (status {r.status_code}){RESET}\n")
    except Exception as e:
        print(f"  {RED}✗ Cannot reach {BASE_URL}: {e}{RESET}")
        print(f"  {RED}  Make sure the Streamlit app is running!{RESET}\n")
        sys.exit(1)

    test_sequential_response_times(n=20)
    test_concurrent_load(workers=15, requests_per_worker=5)
    test_burst(count=50)
    test_database_stress(writes=200, reads=500)
    test_concurrent_db(threads=10, ops_per_thread=30)
    test_streamlit_endpoints()
    test_db_integrity()
    test_sustained_load(duration_sec=15, workers=5)

    print_report()
