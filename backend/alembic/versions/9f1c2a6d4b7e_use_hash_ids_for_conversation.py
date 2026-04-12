"""use hash ids for conversation

Revision ID: 9f1c2a6d4b7e
Revises: 7c9d2e4a1b3f
Create Date: 2026-04-11 12:00:00.000000

"""

import secrets
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f1c2a6d4b7e"
down_revision: Union[str, Sequence[str], None] = "7c9d2e4a1b3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _new_hash_id(existing: set[str]) -> str:
    while True:
        value = secrets.token_urlsafe(12)
        if value not in existing:
            existing.add(value)
            return value


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        raise RuntimeError(
            "This migration currently supports sqlite only. "
            "Please add a dialect-specific migration path for this database."
        )

    # Disable FK enforcement while we rebuild the conversation/message tables.
    op.execute("PRAGMA foreign_keys=OFF")

    op.execute(
        """
        CREATE TABLE conversation_id_map (
            old_id INTEGER PRIMARY KEY,
            new_id VARCHAR(32) NOT NULL UNIQUE
        )
        """
    )

    rows = bind.execute(
        sa.text("SELECT id FROM conversation ORDER BY id ASC")
    ).fetchall()
    existing_ids: set[str] = set()
    for row in rows:
        old_id = int(row[0])
        bind.execute(
            sa.text(
                "INSERT INTO conversation_id_map (old_id, new_id) VALUES (:old_id, :new_id)"
            ),
            {
                "old_id": old_id,
                "new_id": _new_hash_id(existing_ids),
            },
        )

    op.execute(
        """
        CREATE TABLE conversation_new (
            id VARCHAR(32) NOT NULL,
            title VARCHAR(255),
            user_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO conversation_new (id, title, user_id, created_at, updated_at)
        SELECT m.new_id, c.title, c.user_id, c.created_at, c.updated_at
        FROM conversation c
        JOIN conversation_id_map m ON m.old_id = c.id
        """
    )

    op.execute(
        """
        CREATE TABLE message_new (
            id INTEGER NOT NULL,
            conversation_id VARCHAR(32) NOT NULL,
            role VARCHAR(9) NOT NULL,
            content TEXT NOT NULL,
            question TEXT,
            model VARCHAR(100),
            token_input INTEGER,
            token_output INTEGER,
            archived BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(conversation_id) REFERENCES conversation_new (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO message_new (
            id, conversation_id, role, content, question, model,
            token_input, token_output, archived, created_at, updated_at
        )
        SELECT
            msg.id, m.new_id, msg.role, msg.content, msg.question, msg.model,
            msg.token_input, msg.token_output, msg.archived, msg.created_at, msg.updated_at
        FROM message msg
        JOIN conversation_id_map m ON m.old_id = msg.conversation_id
        """
    )

    op.execute(
        """
        CREATE TABLE conversation_summaries_new (
            id INTEGER NOT NULL,
            conversation_id VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            up_to_message_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(conversation_id) REFERENCES conversation_new (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO conversation_summaries_new (
            id, conversation_id, content, up_to_message_id, created_at, updated_at
        )
        SELECT
            cs.id, m.new_id, cs.content, cs.up_to_message_id, cs.created_at, cs.updated_at
        FROM conversation_summaries cs
        JOIN conversation_id_map m ON m.old_id = cs.conversation_id
        """
    )

    op.execute("DROP TABLE conversation_summaries")
    op.execute("DROP TABLE message")
    op.execute("DROP TABLE conversation")

    op.execute("ALTER TABLE conversation_new RENAME TO conversation")
    op.execute("ALTER TABLE message_new RENAME TO message")
    op.execute(
        "ALTER TABLE conversation_summaries_new RENAME TO conversation_summaries"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_user_id ON conversation (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_message_conversation_id ON message (conversation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_summaries_conversation_id "
        "ON conversation_summaries (conversation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_summaries_up_to_message_id "
        "ON conversation_summaries (up_to_message_id)"
    )

    op.execute("DROP TABLE conversation_id_map")
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """Downgrade schema."""
    raise RuntimeError(
        "Downgrade is not supported for hash conversation IDs. "
        "Restore from backup if rollback is required."
    )
