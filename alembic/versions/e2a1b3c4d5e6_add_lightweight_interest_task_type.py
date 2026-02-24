from typing import Sequence, Union

from alembic import op

revision: str = "e2a1b3c4d5e6"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'LIGHTWEIGHT_INTEREST'")


def downgrade() -> None:
    pass
