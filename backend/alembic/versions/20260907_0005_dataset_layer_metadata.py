"""dataset layer type, attribution and temporal coverage"""
from alembic import op
import sqlalchemy as sa
revision="20260907_0005";down_revision="20260907_0004";branch_labels=None;depends_on=None
def upgrade():
    op.add_column("dataset_sources",sa.Column("layer_type",sa.String(40),nullable=False,server_default="hazard_zones"))
    op.add_column("dataset_sources",sa.Column("attribution",sa.Text()))
    op.add_column("dataset_sources",sa.Column("period_start",sa.DateTime(timezone=True)))
    op.add_column("dataset_sources",sa.Column("period_end",sa.DateTime(timezone=True)))
    op.create_index("ix_dataset_sources_layer_type","dataset_sources",["layer_type"])
def downgrade():
    op.drop_index("ix_dataset_sources_layer_type",table_name="dataset_sources")
    for column in ["period_end","period_start","attribution","layer_type"]:op.drop_column("dataset_sources",column)
