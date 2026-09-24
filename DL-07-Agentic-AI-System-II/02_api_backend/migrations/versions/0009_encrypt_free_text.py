"""messages.content and feedback.comment: column encryption (D-15, D-81)

The ciphertext is longer than the text, so the length checks move to the application
(messages: 4,000 characters, feedback comments: 1,000) and both columns become TEXT.
Rows written before this revision are encrypted with the active key.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.core.encryption import PREFIX, column_cipher

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (("messages", "content"), ("feedback", "comment"))


def _rewrite(table: str, column: str, *, encrypt: bool) -> None:
    if context.is_offline_mode():
        # Offline SQL cannot run the cipher; existing rows stay readable as plaintext.
        op.execute(f"-- encrypt existing {table}.{column} rows with the app (online upgrade)")
        return
    connection = op.get_bind()
    cipher = column_cipher()
    label = f"{table}.{column}"
    condition = "NOT LIKE" if encrypt else "LIKE"
    rows = connection.execute(
        sa.text(
            f"SELECT id, {column} FROM {table} "  # noqa: S608 - fixed names above
            f"WHERE {column} IS NOT NULL AND {column} {condition} :prefix"
        ),
        # A bind parameter: in text() the colon in 'enc:v1:' would start a parameter name.
        {"prefix": f"{PREFIX}%"},
    ).all()
    for row_id, value in rows:
        new = (
            cipher.encrypt(value, column=label) if encrypt else cipher.decrypt(value, column=label)
        )
        connection.execute(
            sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),  # noqa: S608
            {"value": new, "id": row_id},
        )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_messages_content_length"), "messages", type_="check")
    op.alter_column("feedback", "comment", type_=sa.Text(), existing_type=sa.String(1000))
    for table, column in _COLUMNS:
        _rewrite(table, column, encrypt=True)


def downgrade() -> None:
    for table, column in _COLUMNS:
        _rewrite(table, column, encrypt=False)
    op.alter_column(
        "feedback",
        "comment",
        type_=sa.String(1000),
        existing_type=sa.Text(),
        postgresql_using="left(comment, 1000)",
    )
    op.create_check_constraint(
        op.f("ck_messages_content_length"), "messages", "char_length(content) <= 4000"
    )
