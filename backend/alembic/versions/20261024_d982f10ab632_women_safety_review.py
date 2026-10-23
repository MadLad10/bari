"""Separate women-only safety approval from owner intent and document checks."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d982f10ab632"
down_revision = "c761d82f903b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("women_safety_status", sa.String(25), nullable=False, server_default="not_submitted"))
    op.add_column("properties", sa.Column("women_safety_submission", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("properties", sa.Column("women_safety_feedback", sa.Text(), nullable=True))
    op.add_column("properties", sa.Column("women_safety_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("properties", sa.Column("women_safety_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("women_safety_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewer_name", sa.String(100), nullable=False),
        sa.Column("verdict", sa.String(25), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checklist", postgresql.JSONB(), nullable=False),
        sa.Column("submission", postgresql.JSONB(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_women_safety_reviews_property_id", "women_safety_reviews", ["property_id"])
    # Legacy owner-selected flags are requests, never evidence of approval.
    op.execute("UPDATE properties SET status = 'pending' WHERE is_female_only AND status = 'active'")
    op.execute("DELETE FROM documents WHERE source_type IN ('listing', 'safety') AND property_id IN (SELECT id FROM properties WHERE is_female_only)")


def downgrade():
    op.drop_table("women_safety_reviews")
    for field in ("women_safety_reviewed_at", "women_safety_version", "women_safety_feedback", "women_safety_submission", "women_safety_status"):
        op.drop_column("properties", field)
