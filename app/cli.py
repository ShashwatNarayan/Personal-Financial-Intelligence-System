"""
Flask CLI commands for database maintenance.

Usage:
    flask deduplicate --dry-run    # preview what would be removed
    flask deduplicate              # remove duplicates and backfill fingerprints
"""

import hashlib
from collections import defaultdict

import click
from flask.cli import with_appcontext
from sqlalchemy import func


def _make_fp(txn):
    """Compute the fingerprint for an existing Transaction ORM object."""
    date_str = str(txn.txn_date)[:10] if txn.txn_date else ''
    desc_str = str(txn.description or '').lower().strip()
    amt_str = f"{float(txn.amount or 0):.2f}"
    return hashlib.md5(f"{txn.user_id}|{date_str}|{desc_str}|{amt_str}".encode('utf-8')).hexdigest()


@click.command('deduplicate')
@click.option('--dry-run', is_flag=True, default=False,
              help='Preview changes without committing anything to the database.')
@with_appcontext
def deduplicate_cmd(dry_run):
    """
    Remove duplicate transactions and backfill fingerprints.

    Run this once after the migration that adds the fingerprint column.
    Prefer keeping the transaction that has user corrections; otherwise keep
    the one with the lowest id (earliest inserted).
    """
    from app import db
    from app.models import Correction, Transaction

    if dry_run:
        click.echo('=== DRY RUN — database will not be changed ===\n')

    # ── 1. Load all transactions ordered by id ──────────────────────────────
    all_txns = Transaction.query.order_by(Transaction.user_id, Transaction.id).all()
    click.echo(f'Loaded {len(all_txns):,} transactions.')

    # ── 2. Compute fingerprints in memory (no DB writes yet) ────────────────
    fp_of = {}   # txn.id → fingerprint string
    for txn in all_txns:
        fp_of[txn.id] = txn.fingerprint if txn.fingerprint else _make_fp(txn)

    # ── 3. Group by (user_id, fingerprint) ──────────────────────────────────
    groups = defaultdict(list)
    for txn in all_txns:
        groups[(txn.user_id, fp_of[txn.id])].append(txn)

    dup_groups = [(key, txns) for key, txns in groups.items() if len(txns) > 1]

    if not dup_groups:
        click.echo('No duplicate transactions found.\n')
        if not dry_run:
            _backfill(all_txns, fp_of, db)
        return

    # ── 4. Preload correction counts in one query ───────────────────────────
    correction_counts = dict(
        db.session.query(Correction.transaction_id, func.count(Correction.id))
        .group_by(Correction.transaction_id)
        .all()
    )

    # ── 5. Decide what to keep vs delete ────────────────────────────────────
    to_delete = []
    total_dup_rows = 0

    click.echo(f'Found {len(dup_groups)} duplicate group(s):\n')
    for (user_id, fp), txns in sorted(dup_groups, key=lambda x: (x[0][0], min(t.id for t in x[1]))):
        # Prefer the transaction that already has corrections; otherwise min(id)
        with_corrections = [t for t in txns if correction_counts.get(t.id, 0) > 0]
        keep = with_corrections[0] if with_corrections else min(txns, key=lambda t: t.id)
        delete_these = [t for t in txns if t.id != keep.id]

        total_dup_rows += len(delete_these)
        to_delete.extend(delete_these)

        click.echo(
            f'  User {user_id} | {keep.txn_date} | '
            f'{str(keep.description or "")[:45]!r} | ₹{keep.amount}'
        )
        click.echo(f'    KEEP   id={keep.id:>6}  upload_id={keep.upload_id}')
        for d in delete_these:
            corr = correction_counts.get(d.id, 0)
            corr_note = f'  ⚠ has {corr} correction(s)' if corr else ''
            click.echo(f'    DELETE id={d.id:>6}  upload_id={d.upload_id}{corr_note}')
        click.echo()

    click.echo(f'Summary: {total_dup_rows} duplicate row(s) will be removed.')

    if dry_run:
        click.echo('\nDry run complete. Re-run without --dry-run to apply changes.')
        return

    # ── 6. Apply: backfill fingerprints then delete duplicates ───────────────
    _backfill(all_txns, fp_of, db)

    delete_ids = {t.id for t in to_delete}
    for txn in all_txns:
        if txn.id in delete_ids:
            db.session.delete(txn)

    db.session.commit()
    click.echo(f'\n✓ Deleted {total_dup_rows} duplicate transaction(s).')
    click.echo('✓ Fingerprints backfilled for all remaining transactions.')


def _backfill(all_txns, fp_of, db):
    """Assign computed fingerprints to rows that currently have NULL."""
    updated = 0
    for txn in all_txns:
        if not txn.fingerprint:
            txn.fingerprint = fp_of[txn.id]
            updated += 1
    if updated:
        db.session.commit()
        click.echo(f'✓ Backfilled fingerprints for {updated} existing transaction(s).')


@click.command('clear-data')
@click.option('--yes', is_flag=True, default=False,
              help='Skip the confirmation prompt.')
@with_appcontext
def clear_data_cmd(yes):
    """
    Permanently delete all uploaded data for ALL users.

    Removes: transactions, uploads_log, corrections, entity_memory.
    Keeps:   user accounts (email + password).

    This cannot be undone.
    """
    from app import db
    from app.models import Correction, EntityMemory, Transaction, UploadLog

    if not yes:
        click.echo('This will permanently delete:')
        click.echo('  • ALL transactions')
        click.echo('  • ALL upload logs')
        click.echo('  • ALL corrections')
        click.echo('  • ALL entity memory (category learning)')
        click.echo('  for every user in the database.')
        click.echo('  User accounts (email / password) will NOT be deleted.')
        click.echo()
        confirm = click.prompt('Type "yes" to confirm')
        if confirm.strip().lower() != 'yes':
            click.echo('Aborted — nothing was deleted.')
            return

    # Delete in child-first order to satisfy FK constraints
    n_corr  = db.session.query(Correction).delete(synchronize_session=False)
    n_txn   = db.session.query(Transaction).delete(synchronize_session=False)
    n_upl   = db.session.query(UploadLog).delete(synchronize_session=False)
    n_mem   = db.session.query(EntityMemory).delete(synchronize_session=False)
    db.session.commit()

    click.echo()
    click.echo(f'✓ {n_corr:>6,}  corrections deleted')
    click.echo(f'✓ {n_txn:>6,}  transactions deleted')
    click.echo(f'✓ {n_upl:>6,}  upload logs deleted')
    click.echo(f'✓ {n_mem:>6,}  entity memory entries deleted')
    click.echo()
    click.echo('Done. User accounts are intact.')
