"""Archive listings and prevent cascading deletion of booking history."""
from alembic import op
import sqlalchemy as sa

revision = "ea420f18c6d2"
down_revision = "d982f10ab632"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_properties_archived_at", "properties", ["archived_at"])
    constraint = next(fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys("bookings")
                      if fk["constrained_columns"] == ["property_id"])
    op.drop_constraint(constraint, "bookings", type_="foreignkey")
    op.create_foreign_key("bookings_property_id_fkey", "bookings", "properties", ["property_id"], ["id"], ondelete="RESTRICT")


def downgrade():
    op.drop_constraint("bookings_property_id_fkey", "bookings", type_="foreignkey")
    op.create_foreign_key("bookings_property_id_fkey", "bookings", "properties", ["property_id"], ["id"], ondelete="CASCADE")
    op.drop_index("ix_properties_archived_at", "properties")
    op.drop_column("properties", "archived_at")
