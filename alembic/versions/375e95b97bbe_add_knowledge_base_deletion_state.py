"""add knowledge base deletion state

Revision ID: 375e95b97bbe
Revises: 7ee22ff5dcf6
Create Date: 2026-11-09 21:07:26.145535

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "375e95b97bbe"
down_revision: str | Sequence[str] | None = "7ee22ff5dcf6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add knowledge base lifecycle state."""
    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="active",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "deletion_error",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "status_valid",
            "status IN ('active', 'deleting')",
        )


def downgrade() -> None:
    """Remove knowledge base lifecycle state."""
    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.drop_constraint("status_valid", type_="check")
        batch_op.drop_column("deletion_error")
        batch_op.drop_column("status")
