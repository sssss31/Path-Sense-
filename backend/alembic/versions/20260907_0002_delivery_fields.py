"""complete delivery workflow fields"""
from alembic import op
import sqlalchemy as sa
revision="20260907_0002";down_revision="20260907_0001";branch_labels=None;depends_on=None
def upgrade():
    op.add_column("deliveries",sa.Column("source_location_id",sa.Uuid(),nullable=True));op.add_column("deliveries",sa.Column("destination_location_id",sa.Uuid(),nullable=True));op.add_column("deliveries",sa.Column("actual_arrival",sa.DateTime(timezone=True)));op.add_column("deliveries",sa.Column("notes",sa.Text()));op.create_foreign_key("fk_deliveries_source_location_id_locations","deliveries","locations",["source_location_id"],["id"]);op.create_foreign_key("fk_deliveries_destination_location_id_locations","deliveries","locations",["destination_location_id"],["id"]);op.create_index("ix_deliveries_source_location_id","deliveries",["source_location_id"]);op.create_index("ix_deliveries_destination_location_id","deliveries",["destination_location_id"])
def downgrade():
    op.drop_index("ix_deliveries_destination_location_id",table_name="deliveries");op.drop_index("ix_deliveries_source_location_id",table_name="deliveries");op.drop_constraint("fk_deliveries_destination_location_id_locations","deliveries",type_="foreignkey");op.drop_constraint("fk_deliveries_source_location_id_locations","deliveries",type_="foreignkey");op.drop_column("deliveries","notes");op.drop_column("deliveries","actual_arrival");op.drop_column("deliveries","destination_location_id");op.drop_column("deliveries","source_location_id")
