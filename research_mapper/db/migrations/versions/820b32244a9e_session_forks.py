"""session forks

Revision ID: 820b32244a9e
Revises: f7ab2b8af61b
Create Date: 2026-09-02 09:12:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "820b32244a9e"
down_revision: Union[str, Sequence[str], None] = "f7ab2b8af61b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_sessions", sa.Column("forked_from_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "research_sessions", sa.Column("forked_at_step", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_research_sessions_forked_from_id_research_sessions"),
        "research_sessions",
        "research_sessions",
        ["forked_from_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_research_sessions_forked_from_id_research_sessions"),
        "research_sessions",
        type_="foreignkey",
    )
    op.drop_column("research_sessions", "forked_at_step")
    op.drop_column("research_sessions", "forked_from_id")
