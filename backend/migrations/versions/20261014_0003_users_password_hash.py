"""users.password_hash for Auth.js credentials in Postgres

Revision ID: 20261014_0003
Revises: 20260924_0002
Create Date: 2026-10-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0003"
down_revision: Union[str, Sequence[str], None] = "20260924_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
