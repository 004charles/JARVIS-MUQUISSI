"""add Céu bible tables

Revision ID: c3e0b1b1e001
Revises: 6e65039a850b
Create Date: 2026-11-21
"""

from alembic import op
import sqlalchemy as sa

revision = "c3e0b1b1e001"
down_revision = "6e65039a850b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bible_translations",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("license", sa.String(120), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(300), nullable=False),
    )
    op.create_table(
        "bible_verses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("translation", sa.String(16), nullable=False),
        sa.Column("book", sa.Integer(), nullable=False),
        sa.Column("chapter", sa.Integer(), nullable=False),
        sa.Column("verse", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("translation", "book", "chapter", "verse", name="uq_bible_verse"),
    )
    op.create_index("ix_bible_verses_translation", "bible_verses", ["translation"])
    op.create_index("ix_bible_verse_lookup", "bible_verses", ["translation", "book", "chapter", "verse"])
    op.create_table(
        "bible_cross_refs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("from_book", sa.Integer(), nullable=False),
        sa.Column("from_chapter", sa.Integer(), nullable=False),
        sa.Column("from_verse", sa.Integer(), nullable=False),
        sa.Column("to_book", sa.Integer(), nullable=False),
        sa.Column("to_chapter", sa.Integer(), nullable=False),
        sa.Column("to_verse", sa.Integer(), nullable=False),
        sa.Column("to_end_chapter", sa.Integer(), nullable=False),
        sa.Column("to_end_verse", sa.Integer(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False),
    )
    op.create_index("ix_bible_xref_from", "bible_cross_refs", ["from_book", "from_chapter", "from_verse"])


def downgrade() -> None:
    op.drop_index("ix_bible_xref_from", table_name="bible_cross_refs")
    op.drop_table("bible_cross_refs")
    op.drop_index("ix_bible_verse_lookup", table_name="bible_verses")
    op.drop_index("ix_bible_verses_translation", table_name="bible_verses")
    op.drop_table("bible_verses")
    op.drop_table("bible_translations")
