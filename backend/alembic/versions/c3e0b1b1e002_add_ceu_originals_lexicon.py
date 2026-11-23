"""add Céu original-language words and lexicon

Revision ID: c3e0b1b1e002
Revises: c3e0b1b1e001
Create Date: 2026-11-21
"""

from alembic import op
import sqlalchemy as sa

revision = "c3e0b1b1e002"
down_revision = "c3e0b1b1e001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bible_original_words",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("book", sa.Integer(), nullable=False),
        sa.Column("chapter", sa.Integer(), nullable=False),
        sa.Column("verse", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("word", sa.String(80), nullable=False),
        sa.Column("translit", sa.String(80), nullable=False),
        sa.Column("gloss", sa.String(160), nullable=False),
        sa.Column("strong", sa.String(16), nullable=False),
        sa.Column("morph", sa.String(40), nullable=False),
        sa.Column("lemma", sa.String(80), nullable=False),
        sa.Column("editions", sa.String(120), nullable=False),
    )
    op.create_index("ix_bible_orig_verse", "bible_original_words", ["book", "chapter", "verse", "position"])
    op.create_index("ix_bible_original_words_strong", "bible_original_words", ["strong"])
    op.create_table(
        "bible_lexicon",
        sa.Column("strong", sa.String(16), primary_key=True),
        sa.Column("estrong", sa.String(16), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("lemma", sa.String(80), nullable=False),
        sa.Column("translit", sa.String(80), nullable=False),
        sa.Column("morph", sa.String(40), nullable=False),
        sa.Column("gloss", sa.String(160), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
    )
    op.create_index("ix_bible_lexicon_estrong", "bible_lexicon", ["estrong"])


def downgrade() -> None:
    op.drop_index("ix_bible_lexicon_estrong", table_name="bible_lexicon")
    op.drop_table("bible_lexicon")
    op.drop_index("ix_bible_original_words_strong", table_name="bible_original_words")
    op.drop_index("ix_bible_orig_verse", table_name="bible_original_words")
    op.drop_table("bible_original_words")
