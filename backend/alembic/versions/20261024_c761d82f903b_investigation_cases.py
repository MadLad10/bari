"""Private investigation cases, updates, and existing forum report intake."""
from alembic import op
import sqlalchemy as sa

revision = "c761d82f903b"
down_revision = "b825c73e0a41"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("investigation_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reporter_name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="open"),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="SET NULL")),
        sa.Column("property_title", sa.String(200)),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id", ondelete="SET NULL")),
        sa.Column("booking_reference", sa.Integer()),
        sa.Column("forum_post_id", sa.Integer(), sa.ForeignKey("forum_posts.id", ondelete="SET NULL"), unique=True),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolution", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_investigation_cases_reporter_id", "investigation_cases", ["reporter_id"])
    op.create_index("ix_investigation_cases_status", "investigation_cases", ["status"])
    op.create_table("case_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("investigation_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(25), nullable=False),
        sa.Column("internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_case_updates_case_id", "case_updates", ["case_id"])
    # Retain original report attribution. Anonymous demo posts stay unassigned to any user account.
    op.execute("""
        INSERT INTO investigation_cases
            (reporter_id, reporter_name, category, title, description, property_id, property_title, forum_post_id, created_at, updated_at)
        SELECT f.author_id, f.author_name, 'forum_report', f.title, f.body, f.property_id, p.title, f.id, f.created_at, f.created_at
        FROM forum_posts f LEFT JOIN properties p ON p.id = f.property_id
        WHERE f.post_type = 'report'
    """)
    op.execute("""
        INSERT INTO case_updates (case_id, actor_id, actor_name, kind, body, created_at)
        SELECT id, reporter_id, reporter_name, 'opened', 'Forum report received for admin investigation.', created_at
        FROM investigation_cases
    """)


def downgrade():
    op.drop_table("case_updates")
    op.drop_table("investigation_cases")
