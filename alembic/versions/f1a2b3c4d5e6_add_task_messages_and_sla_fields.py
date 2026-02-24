from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e2a1b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("escalation_level", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("escalated_to_id", sa.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_tasks_escalated_to",
        "tasks",
        "users",
        ["escalated_to_id"],
        ["id"],
    )

    message_author_type = sa.Enum(
        "EAM", "CLIENT", "SYSTEM", name="taskmessageauthortype"
    )
    message_author_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_messages",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("task_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("client_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "author_type",
            sa.Enum("EAM", "CLIENT", "SYSTEM", name="taskmessageauthortype"),
            nullable=False,
        ),
        sa.Column("author_user_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("author_client_user_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("reply_to_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["author_client_user_id"], ["client_users.id"]),
        sa.ForeignKeyConstraint(["reply_to_id"], ["task_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_task_messages_tenant_id"), "task_messages", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_task_messages_task_id"), "task_messages", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_task_messages_client_id"), "task_messages", ["client_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_messages_client_id"), table_name="task_messages")
    op.drop_index(op.f("ix_task_messages_task_id"), table_name="task_messages")
    op.drop_index(op.f("ix_task_messages_tenant_id"), table_name="task_messages")
    op.drop_table("task_messages")
    sa.Enum(name="taskmessageauthortype").drop(op.get_bind(), checkfirst=True)

    op.drop_constraint("fk_tasks_escalated_to", "tasks", type_="foreignkey")
    op.drop_column("tasks", "escalated_to_id")
    op.drop_column("tasks", "escalated_at")
    op.drop_column("tasks", "escalation_level")
