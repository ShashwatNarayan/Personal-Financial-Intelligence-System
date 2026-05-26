"""
One-time migration: data/entity_memory.json → entity_memory table in Postgres.

Usage (from project root):
    python scripts/migrate_entity_memory.py

Requires DATABASE_URL to be set in .env or the environment.
Does NOT modify the JSON file — it stays in place for the app to use until Phase 4.
"""

import json
import os
import sys

# Resolve project root so this script can be run from anywhere
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from app import create_app, db
from app.models import EntityMemory, User

JSON_PATH = os.path.join(PROJECT_ROOT, 'data', 'entity_memory.json')
SEED_EMAIL = 'seed@local.dev'
SEED_PASSWORD_HASH = 'not-a-real-hash'


def main():
    app = create_app()

    with app.app_context():
        # Ensure tables exist (safe no-op if already created via flask db upgrade)
        db.create_all()

        # 1. Load JSON
        if not os.path.exists(JSON_PATH):
            print(f"No entity memory file found at {JSON_PATH}. Nothing to migrate.")
            return

        with open(JSON_PATH, 'r') as f:
            data = json.load(f)

        if not data:
            print("entity_memory.json is empty. Nothing to migrate.")
            return

        # 2. Get or create seed user
        seed_user = User.query.filter_by(email=SEED_EMAIL).first()
        if seed_user is None:
            if User.query.count() > 0:
                print(
                    "Users already exist and no seed user found. "
                    "Skipping seed user creation — assign migrated records to an existing user manually."
                )
                return
            seed_user = User(email=SEED_EMAIL, password_hash=SEED_PASSWORD_HASH)
            db.session.add(seed_user)
            db.session.flush()  # get seed_user.id without committing
            print(f"Created seed user: {SEED_EMAIL} (id={seed_user.id})")
        else:
            print(f"Using existing seed user: {SEED_EMAIL} (id={seed_user.id})")

        # 3. Insert entity mappings (skip any already present for this user)
        migrated = 0
        skipped = 0

        for entity_name, attrs in data.items():
            existing = EntityMemory.query.filter_by(
                user_id=seed_user.id,
                entity_name=entity_name,
            ).first()

            if existing:
                skipped += 1
                continue

            record = EntityMemory(
                user_id=seed_user.id,
                entity_name=entity_name,
                category=attrs.get('category', 'Other'),
                entity_type=attrs.get('entity_type'),
                confidence=1.0 if attrs.get('source') == 'user' else 0.8,
                correction_count=1 if attrs.get('source') == 'user' else 0,
            )
            db.session.add(record)
            migrated += 1

        db.session.commit()

        print(f"Migrated {migrated} entity mappings to database.")
        if skipped:
            print(f"Skipped {skipped} already-existing entries.")


if __name__ == '__main__':
    main()
