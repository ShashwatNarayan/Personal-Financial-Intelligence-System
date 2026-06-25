"""
perf_probe.py — standalone performance diagnostic for ArthaLens.

REPORT-ONLY. This script does NOT modify application code. It creates a
throwaway test user, runs the real ingestion pipeline against a sample bank
statement (timing each discrete stage), then exercises the 6 dashboard
endpoints via the Flask test client. A SQLAlchemy event listener counts the
SQL statements issued per stage so N+1 patterns surface as a number.

It mirrors app/api/routes.py:upload_excel() stage-for-stage. The route is a
single monolithic function bound to `current_user`, so it cannot be invoked
piece-by-piece; this probe calls the exact same underlying functions in the
same order to get per-stage timings. Any divergence from the route is a bug
in this probe, not a measurement of different code.

The throwaway user and all its data are deleted in a finally block.

Usage:
    python scripts/perf_probe.py [path-to-statement.xls]

Default statement: mockdata/1 March 2025 to 28 Feb 2026.xls
"""

import os
import sys
import time
import hashlib
from contextlib import contextmanager

import pandas as pd
from sqlalchemy import event, text

# Make the project root importable when run as `python scripts/perf_probe.py`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app, db
from app.models import (
    User, Transaction, EntityMemory, UploadLog, Correction,
)
from app.analytics.bank_detector import detect_bank, get_parser
from app.analytics.categorization import SmartCategorizer
from app.analytics.reimbursement_detector import ReimbursementDetector
from app.analytics.anomaly_detector import AnomalyDetector
from app.analytics.subscription_auditor import SubscriptionAuditor
from app.api.routes import compute_fingerprint

DEFAULT_STATEMENT = os.path.join(
    PROJECT_ROOT, 'mockdata', '1 March 2025 to 28 Feb 2026.xls'
)
TEST_EMAIL = '__perf_probe_throwaway__@local.test'

# ── Global SQL counter (driven by a SQLAlchemy event listener) ──────────────
_QUERY_COUNT = {'n': 0}


def _count_queries(conn, cursor, statement, parameters, context, executemany):
    _QUERY_COUNT['n'] += 1


@contextmanager
def stage(name, results, rows=None):
    """Time a block with perf_counter and capture the # of SQL statements it issued."""
    start_q = _QUERY_COUNT['n']
    t0 = time.perf_counter()
    payload = {}
    try:
        yield payload
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        q = _QUERY_COUNT['n'] - start_q
        per100 = (ms / rows * 100.0) if rows else None
        results.append({
            'stage': name,
            'ms': ms,
            'queries': q,
            'rows': rows,
            'ms_per_100': per100,
        })
        bar = f"{ms:8.1f} ms | {q:4d} q"
        if per100 is not None:
            bar += f" | {per100:7.2f} ms/100 rows"
        print(f"  [{name:<28}] {bar}")


def fmt_table(rows, total_ms):
    lines = []
    header = f"{'Stage':<30} {'ms':>10} {'% total':>9} {'queries':>9} {'ms/100':>9}"
    lines.append(header)
    lines.append('-' * len(header))
    for r in rows:
        pct = (r['ms'] / total_ms * 100.0) if total_ms else 0.0
        per100 = f"{r['ms_per_100']:.2f}" if r['ms_per_100'] is not None else '-'
        lines.append(
            f"{r['stage']:<30} {r['ms']:>10.1f} {pct:>8.1f}% "
            f"{r['queries']:>9} {per100:>9}"
        )
    return '\n'.join(lines)


# ───────────────────────────── PHASE 1 ─────────────────────────────
def phase1_baseline_latency():
    print("\n=== PHASE 1: BASELINE NEON LATENCY (SELECT 1 x10) ===")
    samples = []
    for _ in range(10):
        t0 = time.perf_counter()
        db.session.execute(text('SELECT 1'))
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    stats = {
        'min': samples[0],
        'median': samples[len(samples) // 2],
        'max': samples[-1],
        'all': samples,
    }
    print(f"  SELECT 1  min={stats['min']:.1f}ms  "
          f"median={stats['median']:.1f}ms  max={stats['max']:.1f}ms")
    return stats


# ───────────────────────────── PHASE 2 ─────────────────────────────
def phase2_processing(user, statement_path):
    print("\n=== PHASE 2: STATEMENT PROCESSING (per stage) ===")
    results = []

    # S-1: parse -------------------------------------------------------------
    with stage('parse', results) as p:
        bank = detect_bank(statement_path)
        parser, validator = get_parser(bank)
        df = parser.parse(statement_path)
        p['bank'] = bank
        p['rows'] = len(df)
    row_count = len(df)
    print(f"     bank detected = {p['bank']!r}, parsed rows = {row_count}")

    df_expenses = df[df['transaction_type'] == 'debit'].copy()
    n_debit = len(df_expenses)
    print(f"     debit rows (workload for categorization) = {n_debit}")

    # S-3a: categorization (entity resolve + memory lookups + global N+1) -----
    with stage('categorize_dataframe', results, rows=n_debit):
        categorizer = SmartCategorizer(user_id=user.id)
        df_expenses = categorizer.categorize_dataframe(df_expenses)

    # S-3b: reimbursement detection -----------------------------------------
    with stage('reimbursement_detect', results, rows=n_debit):
        credits_for_detection = df[df['transaction_type'] == 'credit']
        df_for_detection = pd.concat([df_expenses, credits_for_detection])
        detector = ReimbursementDetector(df_for_detection, window_days=60)
        detector.generate_full_report()
        reimbursed_df = detector.df
        debit_flags = reimbursed_df[reimbursed_df['transaction_type'] == 'debit'][
            ['is_reimbursed', 'reimbursed_amount', 'net_amount']
        ].copy()
        df_expenses['is_reimbursed'] = debit_flags['is_reimbursed'].reindex(
            df_expenses.index, fill_value=False)
        df_expenses['reimbursed_amount'] = debit_flags['reimbursed_amount'].reindex(
            df_expenses.index, fill_value=0.0)
        df_expenses['net_amount'] = debit_flags['net_amount'].reindex(
            df_expenses.index, fill_value=None)
        df_expenses['net_amount'] = df_expenses['net_amount'].fillna(df_expenses['amount'])

    # S-3c: anomaly detection -----------------------------------------------
    with stage('anomaly_detect', results, rows=n_debit):
        if 'net_amount' not in df_expenses.columns:
            df_expenses['net_amount'] = df_expenses['amount']
        AnomalyDetector(df_expenses, threshold=2.5, min_months=3).generate_report()

    # S-3d: subscription audit ----------------------------------------------
    with stage('subscription_audit', results, rows=n_debit):
        SubscriptionAuditor(df_expenses, min_occurrences=3).generate_report()

    # S-4a: dedup / fingerprint (the per-row fingerprint loop) ---------------
    with stage('dedup_fingerprint', results, rows=n_debit) as p:
        existing_fps = set(
            fp for (fp,) in db.session.query(Transaction.fingerprint)
            .filter(Transaction.user_id == user.id)
            .filter(Transaction.fingerprint.isnot(None)).all()
        )
        upload = UploadLog(
            user_id=user.id, filename='perf_probe.xls', bank_detected=p.get('bank', 'unknown'),
            row_count=0, file_hash=hashlib.sha256(os.urandom(16)).hexdigest(),
        )
        db.session.add(upload)
        db.session.flush()
        to_insert = []
        skipped = 0
        for _, row in df_expenses.iterrows():
            fp = compute_fingerprint(user.id, row['date'], row.get('description', ''), row.get('amount', 0))
            if fp in existing_fps:
                skipped += 1
                continue
            existing_fps.add(fp)
            to_insert.append({
                'user_id': user.id, 'upload_id': upload.id, 'fingerprint': fp,
                'txn_date': row['date'],
                'description': str(row.get('description', ''))[:200],
                'entity_name': str(row.get('entity_name', row.get('merchant', 'Unknown'))),
                'amount': float(row.get('amount', 0)),
                'transaction_type': str(row.get('transaction_type', 'debit')),
                'category': str(row.get('category', 'Other')),
                'entity_type': str(row.get('entity_type', '')),
                'confidence_level': str(row.get('confidence_level', 'medium')),
                'is_reimbursed': bool(row.get('is_reimbursed', False)),
            })
        p['new'] = len(to_insert)
        p['skipped'] = skipped

    # S-4b: DB insert (single bulk insert) ----------------------------------
    with stage('db_bulk_insert', results, rows=p['new'] or None):
        if to_insert:
            db.session.bulk_insert_mappings(Transaction, to_insert)
        upload.row_count = len(to_insert)
        db.session.commit()

    # S-4c: entity-memory upsert --------------------------------------------
    with stage('entity_memory_seed', results, rows=n_debit):
        entity_updates = {}
        for _, row in df_expenses.iterrows():
            en = str(row.get('entity_name', row.get('merchant', 'Unknown')))
            entity_updates.setdefault(en, {
                'user_id': user.id, 'entity_name': en,
                'category': str(row.get('category', 'Other')),
                'entity_type': str(row.get('entity_type', 'unknown')),
                'confidence': 0.8, 'correction_count': 0,
            })
        if entity_updates:
            existing = EntityMemory.query.filter_by(user_id=user.id).filter(
                EntityMemory.entity_name.in_(entity_updates.keys())).all()
            existing_names = {e.entity_name for e in existing}
            new_mems = [v for k, v in entity_updates.items() if k not in existing_names]
            if new_mems:
                db.session.bulk_insert_mappings(EntityMemory, new_mems)
                db.session.commit()

    total_ms = sum(r['ms'] for r in results)
    print("\n  --- Phase 2 breakdown ---")
    print(fmt_table(results, total_ms))
    print(f"  TOTAL processing: {total_ms:.1f} ms  "
          f"(statement rows={row_count}, debit rows={n_debit})")
    return results, total_ms, row_count, n_debit


# ───────────────────────────── PHASE 3 ─────────────────────────────
DASHBOARD_ENDPOINTS = [
    '/api/transactions/classified',
    '/api/transactions/needs-review',
    '/api/subscriptions/audit',
    '/api/reimbursements/report',
    '/api/anomalies/report',
    '/api/insights/temporal',
]


def phase3_dashboard(app, user):
    print("\n=== PHASE 3: DASHBOARD LOAD (6 endpoints) ===")
    results = []
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True

    for ep in DASHBOARD_ENDPOINTS:
        start_q = _QUERY_COUNT['n']
        t0 = time.perf_counter()
        resp = client.get(ep)
        ms = (time.perf_counter() - t0) * 1000.0
        q = _QUERY_COUNT['n'] - start_q
        results.append({'endpoint': ep, 'ms': ms, 'queries': q, 'status': resp.status_code})
        print(f"  [{ep:<34}] {ms:8.1f} ms | {q:3d} q | HTTP {resp.status_code}")

    # Each endpoint calls get_user_transactions_df() exactly once → 1 SELECT on
    # transactions per endpoint. The classified endpoint additionally runs a
    # SubscriptionAuditor (pure pandas, 0 queries). So "DataFrame rebuilds per
    # page load" == number of endpoints firing == 6.
    total_ms = sum(r['ms'] for r in results)
    total_q = sum(r['queries'] for r in results)
    print(f"\n  TOTAL dashboard (serial): {total_ms:.1f} ms across {total_q} queries, "
          f"6 independent DataFrame rebuilds")
    return results, total_ms


def phase3_explain(user):
    """EXPLAIN ANALYZE the heaviest queries + report index coverage."""
    print("\n=== PHASE 3b: EXPLAIN ANALYZE + index check ===")
    out = []

    queries = {
        'transactions_by_user (the DataFrame fetch, every endpoint)':
            "SELECT * FROM transactions WHERE user_id = :uid",
        'transactions_by_user_excl_internal (5 of 6 endpoints)':
            "SELECT * FROM transactions WHERE user_id = :uid AND entity_type <> 'internal'",
        'fingerprint_preload (upload dedup)':
            "SELECT fingerprint FROM transactions WHERE user_id = :uid AND fingerprint IS NOT NULL",
    }
    for label, q in queries.items():
        try:
            plan = db.session.execute(
                text("EXPLAIN (ANALYZE, BUFFERS) " + q), {'uid': user.id}
            ).fetchall()
            plan_txt = '\n'.join(r[0] for r in plan)
        except Exception as e:
            plan_txt = f"(EXPLAIN failed: {e})"
        out.append((label, q, plan_txt))
        print(f"\n  -- {label}")
        for line in plan_txt.splitlines():
            print(f"     {line}")

    # Index inventory on transactions
    idx = db.session.execute(text("""
        SELECT indexname, indexdef FROM pg_indexes
        WHERE tablename = 'transactions' ORDER BY indexname
    """)).fetchall()
    print("\n  -- Indexes on 'transactions':")
    for name, ddl in idx:
        print(f"     {name}: {ddl}")
    return out, [(n, d) for n, d in idx]


# ───────────────────────────── driver ─────────────────────────────
def cleanup_user(user_id):
    Correction.query.filter_by(user_id=user_id).delete()
    Transaction.query.filter_by(user_id=user_id).delete()
    EntityMemory.query.filter_by(user_id=user_id).delete()
    UploadLog.query.filter_by(user_id=user_id).delete()
    User.query.filter_by(id=user_id).delete()
    db.session.commit()


def main():
    statement_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STATEMENT
    if not os.path.exists(statement_path):
        print(f"FATAL: statement not found: {statement_path}")
        sys.exit(1)

    app = create_app()
    with app.app_context():
        # Listener on the live engine — counts every SQL statement.
        event.listen(db.engine, 'before_cursor_execute', _count_queries)

        baseline = phase1_baseline_latency()

        # Fresh throwaway user
        User.query.filter_by(email=TEST_EMAIL).delete()
        db.session.commit()
        user = User(email=TEST_EMAIL)
        user.set_password('throwaway-not-used')
        db.session.add(user)
        db.session.commit()
        print(f"\n  throwaway user id = {user.id}")

        try:
            p2, p2_total, row_count, n_debit = phase2_processing(user, statement_path)
            p3, p3_total = phase3_dashboard(app, user)
            explains, indexes = phase3_explain(user)

            # ── Bottleneck ranking (printed to terminal per spec) ──
            print("\n" + "=" * 64)
            print("BOTTLENECK RANKING (slowest first)")
            print("=" * 64)
            combined = (
                [{'where': 'upload', **r} for r in p2]
                + [{'where': 'dashboard', 'stage': r['endpoint'], 'ms': r['ms'],
                    'queries': r['queries'], 'rows': None, 'ms_per_100': None}
                   for r in p3]
            )
            combined.sort(key=lambda r: r['ms'], reverse=True)
            for i, r in enumerate(combined, 1):
                print(f"  {i:2d}. [{r['where']:<9}] {r['stage']:<30} "
                      f"{r['ms']:8.1f} ms | {r['queries']:3d} q")
            print(f"\n  Neon SELECT 1 floor: median {baseline['median']:.1f} ms/query "
                  f"(min {baseline['min']:.1f}, max {baseline['max']:.1f})")
        finally:
            cleanup_user(user.id)
            print(f"\n  cleaned up throwaway user {user.id}")


if __name__ == '__main__':
    main()
