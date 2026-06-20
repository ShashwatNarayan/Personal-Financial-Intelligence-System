"""add check constraint normalizing global_entity_memory entity_name

Revision ID: 38608c90f036
Revises: 463ffe6f87a6
Create Date: 2026-06-20 23:16:24.848877

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '38608c90f036'
down_revision = '463ffe6f87a6'
branch_labels = None
depends_on = None


def upgrade():
    # Codify the invariant both writers already enforce in code (routes.py
    # /correct and cli.py backfill both store entity_name.lower().strip()):
    # entity_name is always stored lowercase and trimmed. Additive only — no
    # data change, no table rewrite. Verified 0 violating rows before adding.
    op.create_check_constraint(
        'ck_global_entity_name_normalized',
        'global_entity_memory',
        'entity_name = lower(trim(entity_name))',
    )


def downgrade():
    op.drop_constraint(
        'ck_global_entity_name_normalized',
        'global_entity_memory',
        type_='check',
    )
