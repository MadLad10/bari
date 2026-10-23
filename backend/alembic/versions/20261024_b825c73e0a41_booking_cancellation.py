"""Record why and when a booking was cancelled or rejected."""
from alembic import op
import sqlalchemy as sa

revision = "b825c73e0a41"
down_revision = "a19d483c0d12"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bookings", sa.Column("cancellation_reason", sa.String(30), nullable=True))
    op.add_column("bookings", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("bookings", "cancelled_at")
    op.drop_column("bookings", "cancellation_reason")
