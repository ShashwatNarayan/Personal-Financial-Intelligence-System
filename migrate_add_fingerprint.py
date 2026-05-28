"""
Comprehensive schema migration: adds all columns/constraints that exist in
models.py but are missing from the Neon DB. Run once, then delete this file.
"""
from app import create_app, db

app = create_app()

def column_exists(conn, table, column):
    r = conn.execute(db.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    return r.fetchone() is not None

def constraint_exists(conn, table, constraint):
    r = conn.execute(db.text("""
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = :t AND constraint_name = :c
    """), {"t": table, "c": constraint})
    return r.fetchone() is not None

migrations = [
    # (description, check_fn, sql)
    (
        "transactions.fingerprint column",
        lambda c: column_exists(c, "transactions", "fingerprint"),
        "ALTER TABLE transactions ADD COLUMN fingerprint VARCHAR(32)"
    ),
    (
        "uq_transactions_user_fingerprint constraint",
        lambda c: constraint_exists(c, "transactions", "uq_transactions_user_fingerprint"),
        "ALTER TABLE transactions ADD CONSTRAINT uq_transactions_user_fingerprint UNIQUE (user_id, fingerprint)"
    ),
    (
        "uploads_log.file_hash column",
        lambda c: column_exists(c, "uploads_log", "file_hash"),
        "ALTER TABLE uploads_log ADD COLUMN file_hash VARCHAR(64)"
    ),
    (
        "uq_uploads_user_file_hash constraint",
        lambda c: constraint_exists(c, "uploads_log", "uq_uploads_user_file_hash"),
        "ALTER TABLE uploads_log ADD CONSTRAINT uq_uploads_user_file_hash UNIQUE (user_id, file_hash)"
    ),
]

with app.app_context():
    with db.engine.connect() as conn:
        for description, already_exists, sql in migrations:
            if already_exists(conn):
                print(f"  SKIP  {description} (already exists)")
            else:
                conn.execute(db.text(sql))
                print(f"  ADDED {description}")
        conn.commit()
        print("\nMigration complete.")
