"""users.github_id for OAuth account linking

Revision ID: 20261014_0004
Revises: 20261014_0003
Create Date: 2026-10-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0004"
down_revision: Union[str, Sequence[str], None] = "20261014_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_id", sa.Text(), nullable=True))
    op.create_index("ix_users_github_id", "users", ["github_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_github_id", table_name="users")
    op.drop_column("users", "github_id")
