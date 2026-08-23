"""One-off backfill: re-resolve POS entity names for user 19.

Transactions ingested before the 2026-07-01 POS fix stored the *whole* card-swipe
prefix as the entity name — ref number, date, HH:MM:SS, city — instead of the
merchant. This re-runs the CURRENT EntityResolver over each stored description
and writes back the corrected entity_name / entity_type, then merges the
per-user entity_memory rows that were keyed on those dirty names.

Scope: user_id = 19 only. No app/ code is touched.

  STEP 1  transactions   — 12 rows, entity_name + entity_type only.
                           category / confidence_level / is_reimbursed untouched.
  STEP 2  entity_memory  — 12 dirty rows merge into 8 target names.
  STEP 3  corrections    — deliberately untouched. It is an immutable audit log
                           and correctly keeps pointing at the old names.

Everything after the backup runs in ONE transaction. Any failed assertion rolls
the whole thing back.

Usage:
    python scripts/backfill_pos_entity_names.py            # dry run — rolls back
    python scripts/backfill_pos_entity_names.py --commit   # commits
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.analytics.entity_resolver import EntityResolver  # noqa: E402

USER_ID = 19
TIMESTAMP_PATTERN = r'\d{1,2}:\d{2}:\d{2}'
EXPECTED_TXN_ROWS = 12
EXPECTED_MEM_ROWS = 12
EXPECTED_TARGET_NAMES = 8

# Row-delta on entity_memory for this user.
#
# NOT 12 -> 8 (a drop of 4). Three of the eight target names — Asian Instiute Of
# Gast, Bigbasket, Star Bazaar — already existed as their own rows before this
# backfill, so the merge consumes 12 dirty rows PLUS those 3 pre-existing rows:
# 15 contributors collapse to 8 survivors, which is 7 deletions.
# Per group: Asian -2, Bigbasket -3, Star Bazaar -1, Rsp*Blink -1.
EXPECTED_CONTRIBUTORS = 15
EXPECTED_DELETIONS = 7


class Abort(Exception):
    pass


def main():
    commit = '--commit' in sys.argv
    load_dotenv(os.path.join(ROOT, '.env'))

    url = os.environ.get('DATABASE_URL')
    if not url:
        print('ABORTED: DATABASE_URL is not set.')
        sys.exit(1)
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)

    engine = create_engine(url)
    resolver = EntityResolver()

    # ── Backup (read-only, before any mutation) ─────────────────────────────
    with engine.connect() as conn:
        txns = conn.execute(text(
            'SELECT id, user_id, entity_name, description, category, entity_type, '
            'confidence_level, is_reimbursed FROM transactions '
            'WHERE user_id = :u AND entity_name ~ :p ORDER BY id'
        ), {'u': USER_ID, 'p': TIMESTAMP_PATTERN}).mappings().all()

        mems = conn.execute(text(
            'SELECT id, user_id, entity_name, category, entity_type, confidence, '
            'correction_count, created_at, updated_at FROM entity_memory '
            'WHERE user_id = :u AND entity_name ~ :p ORDER BY id'
        ), {'u': USER_ID, 'p': TIMESTAMP_PATTERN}).mappings().all()

        total_mem_before = conn.execute(text(
            'SELECT count(*) FROM entity_memory WHERE user_id = :u'
        ), {'u': USER_ID}).scalar()

    print(f'transactions matching the timestamp pattern : {len(txns)}')
    print(f'entity_memory  matching the timestamp pattern: {len(mems)}')
    if len(txns) != EXPECTED_TXN_ROWS:
        print(f'ABORTED: expected {EXPECTED_TXN_ROWS} transactions, found {len(txns)}')
        sys.exit(1)
    if len(mems) != EXPECTED_MEM_ROWS:
        print(f'ABORTED: expected {EXPECTED_MEM_ROWS} entity_memory rows, found {len(mems)}')
        sys.exit(1)

    # Resolve every description up front so the plan can be printed and the
    # merge targets identified before anything is written.
    plan = []
    for t in txns:
        new_name, new_type = resolver.resolve(t['description'], None)
        if not new_name or new_name == 'Unknown' or new_type == 'unknown':
            print(f'ABORTED: id={t["id"]} resolved to {new_name!r}/{new_type!r} — needs manual handling')
            sys.exit(1)
        plan.append({
            'id': t['id'],
            'old_name': t['entity_name'],
            'new_name': new_name,
            'old_type': t['entity_type'],
            'new_type': new_type,
        })

    old_to_new = {p['old_name']: p['new_name'] for p in plan}
    target_names = sorted({p['new_name'] for p in plan})

    # Pre-existing rows the merge will absorb into — these get MODIFIED, so they
    # belong in the backup too (kept under a separate key so the 12/12 count
    # assertions above stay meaningful).
    with engine.connect() as conn:
        pre_targets = conn.execute(text(
            'SELECT id, user_id, entity_name, category, entity_type, confidence, '
            'correction_count, created_at, updated_at FROM entity_memory '
            'WHERE user_id = :u AND entity_name = ANY(:names) ORDER BY id'
        ), {'u': USER_ID, 'names': target_names}).mappings().all()

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(ROOT, 'scripts', f'backfill_pos_backup_{stamp}.json')
    with open(backup_path, 'w', encoding='utf-8') as fh:
        json.dump({
            'user_id': USER_ID,
            'created_at': stamp,
            'transactions': [dict(r) for r in txns],
            'entity_memory': [dict(r) for r in mems],
            'entity_memory_merge_targets': [dict(r) for r in pre_targets],
        }, fh, indent=2, default=str, ensure_ascii=False)

    if not os.path.exists(backup_path):
        print(f'ABORTED: backup file was not created at {backup_path}')
        sys.exit(1)
    with open(backup_path, encoding='utf-8') as fh:
        restored = json.load(fh)
    if len(restored['transactions']) != EXPECTED_TXN_ROWS or len(restored['entity_memory']) != EXPECTED_MEM_ROWS:
        print('ABORTED: backup row counts do not verify')
        sys.exit(1)

    print(f'\nBackup written and verified: {backup_path}')
    print(f'  transactions={len(restored["transactions"])} '
          f'entity_memory={len(restored["entity_memory"])} '
          f'merge_targets={len(restored["entity_memory_merge_targets"])} '
          f'({os.path.getsize(backup_path):,} bytes)')

    # ── One transaction for everything below ────────────────────────────────
    conn = engine.connect()
    trans = conn.begin()
    try:
        # ---- STEP 1: transactions -----------------------------------------
        print('\n' + '=' * 104)
        print('STEP 1 — transactions: entity_name + entity_type')
        print('=' * 104)
        updated = 0
        for p in plan:
            n = conn.execute(text(
                'UPDATE transactions SET entity_name = :n, entity_type = :t '
                'WHERE id = :i AND user_id = :u'
            ), {'n': p['new_name'], 't': p['new_type'], 'i': p['id'], 'u': USER_ID}).rowcount
            updated += n
            print(f"  id={p['id']:<7} {p['old_name'][:46]:<48} -> {p['new_name'][:24]:<26} "
                  f"{p['old_type']} -> {p['new_type']}")

        if updated != EXPECTED_TXN_ROWS:
            raise Abort(f'STEP 1 updated {updated} rows, expected {EXPECTED_TXN_ROWS}')
        print(f'\n  updated {updated} rows')

        remaining = conn.execute(text(
            'SELECT count(*) FROM transactions WHERE user_id = :u AND entity_name ~ :p'
        ), {'u': USER_ID, 'p': TIMESTAMP_PATTERN}).scalar()
        if remaining != 0:
            raise Abort(f'STEP 1: {remaining} transactions still match the timestamp pattern')
        print(f'  remaining rows matching timestamp pattern: {remaining}  OK')

        # ---- STEP 2: entity_memory merge ----------------------------------
        print('\n' + '=' * 104)
        print('STEP 2 — entity_memory merge (12 dirty rows -> 8 target names)')
        print('=' * 104)

        groups = defaultdict(list)
        for m in mems:
            groups[old_to_new[m['entity_name']]].append(dict(m))

        pre_by_name = {r['entity_name']: dict(r) for r in pre_targets}
        deleted_total = 0
        contributors_total = 0

        for new_name in sorted(groups):
            contributors = list(groups[new_name])
            target = pre_by_name.get(new_name)
            if target:
                contributors.append(target)
            contributors_total += len(contributors)

            cats = {c['category'] for c in contributors}
            if len(cats) > 1:
                print(f'\n  !!! CATEGORY DISAGREEMENT in group {new_name!r}: {sorted(cats)}')
                for c in contributors:
                    print(f'        id={c["id"]} {c["entity_name"]!r} cat={c["category"]!r} '
                          f'conf={c["confidence"]} n={c["correction_count"]}')
                raise Abort(f'group {new_name!r} has conflicting categories {sorted(cats)} — '
                            'refusing to pick silently')

            chosen = max(contributors, key=lambda r: (r['confidence'], r['correction_count']))
            category = chosen['category']
            corr_max = max(c['correction_count'] for c in contributors)
            user_confirmed = any(c['correction_count'] > 0 for c in contributors)
            confidence = 1.0 if user_confirmed else chosen['confidence']

            survivor = target or max(groups[new_name], key=lambda r: r['correction_count'])
            doomed = [c for c in contributors if c['id'] != survivor['id']]

            print(f"\n  {new_name!r}")
            print(f"    contributors : {len(contributors)}  category={category!r} (agreed)")
            for c in contributors:
                tag = 'SURVIVOR' if c['id'] == survivor['id'] else 'delete'
                print(f"        [{tag:>8}] id={c['id']:<6} conf={c['confidence']:<5} "
                      f"n={c['correction_count']:<3} {c['entity_name'][:52]!r}")
            print(f"    -> confidence={confidence}  correction_count={corr_max} (MAX)")

            for d in doomed:
                deleted_total += conn.execute(text(
                    'DELETE FROM entity_memory WHERE id = :i AND user_id = :u'
                ), {'i': d['id'], 'u': USER_ID}).rowcount

            conn.execute(text(
                'UPDATE entity_memory SET entity_name = :n, category = :c, '
                'confidence = :f, correction_count = :k, updated_at = :ts '
                'WHERE id = :i AND user_id = :u'
            ), {'n': new_name, 'c': category, 'f': confidence, 'k': corr_max,
                'ts': datetime.utcnow(), 'i': survivor['id'], 'u': USER_ID})

        total_mem_after = conn.execute(text(
            'SELECT count(*) FROM entity_memory WHERE user_id = :u'
        ), {'u': USER_ID}).scalar()
        delta = total_mem_before - total_mem_after

        print(f'\n  contributors consumed   : {contributors_total} (12 dirty + 3 pre-existing targets)')
        print(f'  rows deleted            : {deleted_total}')
        print(f'  entity_memory total     : {total_mem_before} -> {total_mem_after}  (delta -{delta})')

        if contributors_total != EXPECTED_CONTRIBUTORS:
            raise Abort(f'expected {EXPECTED_CONTRIBUTORS} contributor rows across all groups, '
                        f'found {contributors_total} — the merge shape has changed since the dry run')
        if deleted_total != EXPECTED_DELETIONS:
            raise Abort(f'expected exactly {EXPECTED_DELETIONS} deletions, performed {deleted_total}')
        if delta != EXPECTED_DELETIONS:
            raise Abort(f'entity_memory total dropped by {delta}, expected {EXPECTED_DELETIONS} '
                        f'({total_mem_before} -> {total_mem_after})')
        print(f'  deletions == {EXPECTED_DELETIONS} and delta == {EXPECTED_DELETIONS}  OK')

        surviving = conn.execute(text(
            'SELECT count(*) FROM entity_memory WHERE user_id = :u AND entity_name = ANY(:names)'
        ), {'u': USER_ID, 'names': target_names}).scalar()
        if surviving != EXPECTED_TARGET_NAMES:
            raise Abort(f'expected {EXPECTED_TARGET_NAMES} rows carrying the target names, found {surviving}')
        print(f'  rows carrying the 8 target names: {surviving}  OK')

        # ---- Post-checks ---------------------------------------------------
        print('\n' + '=' * 104)
        print('POST-CHECKS')
        print('=' * 104)

        print('\n  transactions (12):')
        for r in conn.execute(text(
            'SELECT id, entity_name, entity_type, category, confidence_level '
            'FROM transactions WHERE id = ANY(:ids) ORDER BY id'
        ), {'ids': [p['id'] for p in plan]}):
            print(f'    id={r[0]:<7} {r[1][:30]:<32} type={r[2]:<10} cat={r[3]:<16} conf={r[4]}')

        print('\n  surviving entity_memory (8):')
        for r in conn.execute(text(
            'SELECT entity_name, category, confidence, correction_count FROM entity_memory '
            'WHERE user_id = :u AND entity_name = ANY(:names) ORDER BY entity_name'
        ), {'u': USER_ID, 'names': target_names}):
            print(f'    {r[0][:30]:<32} {r[1]:<16} conf={r[2]:<5} n={r[3]}')

        bb = conn.execute(text(
            'SELECT confidence FROM entity_memory WHERE user_id = :u AND entity_name = :n'
        ), {'u': USER_ID, 'n': 'Bigbasket'}).scalar()
        if bb is None or float(bb) != 1.0:
            raise Abort(f'Bigbasket survivor confidence is {bb}, expected 1.0')
        print(f"\n  Bigbasket confidence = {bb}  OK (was 0.8, below the >= 0.9 Stage 2 gate)")

        dirty = conn.execute(text(
            'SELECT count(*) FROM entity_memory WHERE user_id = :u AND entity_name ~ :p'
        ), {'u': USER_ID, 'p': TIMESTAMP_PATTERN}).scalar()
        if dirty != 0:
            raise Abort(f'{dirty} entity_memory rows still match the timestamp pattern')
        print(f'  entity_memory rows still matching timestamp pattern: {dirty}  OK')

        corr = conn.execute(text(
            'SELECT count(*) FROM corrections WHERE user_id = :u AND entity_name ~ :p'
        ), {'u': USER_ID, 'p': TIMESTAMP_PATTERN}).scalar()
        print(f'  corrections rows still referencing old names: {corr}  (STEP 3: untouched by design)')

        if commit:
            trans.commit()
            print('\nCOMMITTED.')
        else:
            trans.rollback()
            print('\nDRY RUN — transaction rolled back. Nothing was changed.')
            print('Re-run with --commit to apply.')
        print(f'Backup: {backup_path}')

    except Abort as exc:
        trans.rollback()
        print(f'\nABORTED: {exc}')
        print('Transaction rolled back. No changes were committed.')
        sys.exit(1)
    except Exception:
        trans.rollback()
        print('\nABORTED: unexpected error. Transaction rolled back.')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
