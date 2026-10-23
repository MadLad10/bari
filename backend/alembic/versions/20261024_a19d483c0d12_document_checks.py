"""Private ownership documents and automated document-check results."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a19d483c0d12"
down_revision = "557eca252f28"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("document_check_status", sa.String(20), nullable=False,
                                          server_default="not_submitted"))
    op.add_column("properties", sa.Column("document_check_reasons", postgresql.JSONB(), nullable=False,
                                          server_default="[]"))
    op.add_column("properties", sa.Column("document_checked_at", sa.DateTime(timezone=True)))
    op.create_table("property_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stored_name", sa.String(80), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("text_hash", sa.String(64)),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("extraction_error", sa.String(250)),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for name in ("property_id", "content_hash", "text_hash"):
        op.create_index(f"ix_property_documents_{name}", "property_documents", [name])


def downgrade():
    op.drop_table("property_documents")
    for name in ("document_checked_at", "document_check_reasons", "document_check_status"):
        op.drop_column("properties", name)
