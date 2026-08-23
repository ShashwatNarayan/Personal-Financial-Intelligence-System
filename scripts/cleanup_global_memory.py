"""One-off cleanup of global_entity_memory.

Removes the rows where a POS narration's ref number / date / timestamp / city
leaked into the shared cross-user entity store, and corrects the one row where
a grocery merchant was recorded as a P2P transfer.

Two operations only:
  1. DELETE rows whose entity_name embeds an HH:MM:SS timestamp (9 rows).
  2. UPDATE id 173 ('big basket') from 'Transfer / P2P' to 'Food & Dining'.

Deliberately NOT done here: no deletion by category. The Transfer / P2P rows
stay. Whether that shared store should hold person names at all is a policy
decision, not a data-hygiene fix, and is out of scope for this script.

The timestamp regex is the selector rather than length(entity_name) > 40 —
both match exactly the same 9 rows, but the timestamp is what actually defines
the leak. Do NOT select on entity_name ~ '[0-9]': that matches 27 rows and
would destroy 18 legitimate merchants (kims c17, grill 9, medkart 24, bits 01).

Everything runs in a single transaction. Any failed assertion rolls back.

Usage:  python scripts/cleanup_global_memory.py
"""

import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Selector for the leaked POS rows: an embedded HH:MM:SS clock time.
TIMESTAMP_PATTERN = r'\d{1,2}:\d{2}:\d{2}'

EXPECTED_TOTAL_BEFORE = 633
EXPECTED_DELETE_COUNT = 9
BIG_BASKET_ID = 173
BIG_BASKET_NEW_CATEGORY = 'Food & Dining'
EXPECTED_TOTAL_AFTER = EXPECTED_TOTAL_BEFORE - EXPECTED_DELETE_COUNT  # 624

# Legitimate rows containing digits — must survive.
SENTINELS = ['kims c17', 'grill 9', 'medkart 24', 'bits 01']

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fail(message):
    print(f'\nABORTED: {message}')
    print('No changes were committed.')
    sys.exit(1)


def main():
    load_dotenv(os.path.join(ROOT, '.env'))

    url = os.environ.get('DATABASE_URL')
    if not url:
        fail('DATABASE_URL is not set.')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)

    engine = create_engine(url)

    # ── Step 1: back up every row before touching anything ──────────────────
    with engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT id, entity_name, category, contributed_by_user_id, updated_at '
            'FROM global_entity_memory ORDER BY id'
        )).mappings().all()

    print(f'Read {len(rows)} rows from global_entity_memory.')
    if len(rows) != EXPECTED_TOTAL_BEFORE:
        fail(
            f'expected {EXPECTED_TOTAL_BEFORE} rows before cleanup, found {len(rows)}. '
            'The table changed since this script was written — re-verify before running.'
        )

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(ROOT, 'scripts', f'backup_global_memory_{stamp}.json')
    with open(backup_path, 'w', encoding='utf-8') as fh:
        json.dump([dict(r) for r in rows], fh, indent=2, default=str, ensure_ascii=False)

    # Verify the backup landed and is complete before deleting anything.
    if not os.path.exists(backup_path):
        fail(f'backup file was not created at {backup_path}')
    with open(backup_path, encoding='utf-8') as fh:
        restored = json.load(fh)
    if len(restored) != EXPECTED_TOTAL_BEFORE:
        fail(f'backup holds {len(restored)} rows, expected {EXPECTED_TOTAL_BEFORE}')

    print(f'Backup written and verified: {backup_path}')
    print(f'  {len(restored)} rows, {os.path.getsize(backup_path):,} bytes')

    # ── Step 2: mutate inside one transaction ───────────────────────────────
    with engine.begin() as conn:
        doomed = conn.execute(
            text('SELECT id, entity_name, category FROM global_entity_memory '
                 'WHERE entity_name ~ :pat ORDER BY id'),
            {'pat': TIMESTAMP_PATTERN},
        ).all()

        print(f'\nRows matching the timestamp pattern: {len(doomed)}')
        for r in doomed:
            print(f'  id={r[0]:<4} {r[1]!r} -> {r[2]}')

        if len(doomed) != EXPECTED_DELETE_COUNT:
            fail(
                f'expected exactly {EXPECTED_DELETE_COUNT} rows to delete, matched {len(doomed)}. '
                'Rolling back rather than guessing.'
            )

        deleted = conn.execute(
            text('DELETE FROM global_entity_memory WHERE entity_name ~ :pat'),
            {'pat': TIMESTAMP_PATTERN},
        ).rowcount
        if deleted != EXPECTED_DELETE_COUNT:
            fail(f'DELETE removed {deleted} rows, expected {EXPECTED_DELETE_COUNT}')
        print(f'Deleted {deleted} rows.')

        before = conn.execute(
            text('SELECT entity_name, category FROM global_entity_memory WHERE id = :i'),
            {'i': BIG_BASKET_ID},
        ).first()
        if before is None:
            fail(f'id {BIG_BASKET_ID} not found — refusing to recategorize a missing row')

        updated = conn.execute(
            text('UPDATE global_entity_memory SET category = :c WHERE id = :i'),
            {'c': BIG_BASKET_NEW_CATEGORY, 'i': BIG_BASKET_ID},
        ).rowcount
        if updated != 1:
            fail(f'UPDATE touched {updated} rows, expected 1')
        print(f'Updated id={BIG_BASKET_ID} {before[0]!r}: {before[1]!r} -> {BIG_BASKET_NEW_CATEGORY!r}')

        # ── Step 3: post-checks, still inside the transaction ───────────────
        print('\nPost-checks:')

        total = conn.execute(text('SELECT COUNT(*) FROM global_entity_memory')).scalar()
        if total != EXPECTED_TOTAL_AFTER:
            fail(f'expected {EXPECTED_TOTAL_AFTER} rows remaining, found {total}')
        print(f'  rows remaining ......................... {total} (expected {EXPECTED_TOTAL_AFTER})  OK')

        long_names = conn.execute(text(
            'SELECT COUNT(*) FROM global_entity_memory WHERE length(entity_name) > 40'
        )).scalar()
        if long_names != 0:
            fail(f'{long_names} rows still have length(entity_name) > 40')
        print(f'  rows with length(entity_name) > 40 ..... {long_names}  OK')

        missing = [
            name for name in SENTINELS
            if conn.execute(
                text('SELECT COUNT(*) FROM global_entity_memory WHERE entity_name = :n'),
                {'n': name},
            ).scalar() != 1
        ]
        if missing:
            fail(f'legitimate rows were destroyed: {missing}')
        print(f'  sentinels intact ....................... {", ".join(SENTINELS)}  OK')

        big_basket = conn.execute(
            text('SELECT entity_name, category FROM global_entity_memory WHERE id = :i'),
            {'i': BIG_BASKET_ID},
        ).first()
        if big_basket is None or big_basket[1] != BIG_BASKET_NEW_CATEGORY:
            fail(f'id {BIG_BASKET_ID} did not end up as {BIG_BASKET_NEW_CATEGORY!r}')
        print(f'  id {BIG_BASKET_ID} category ................... {big_basket[1]!r}  OK')

        p2p = conn.execute(text(
            "SELECT COUNT(*) FROM global_entity_memory WHERE category = 'Transfer / P2P'"
        )).scalar()
        print(f'  Transfer / P2P rows (untouched) ........ {p2p}')

    print('\nCommitted.')
    print(f'Restore from: {backup_path}')


if __name__ == '__main__':
    main()
