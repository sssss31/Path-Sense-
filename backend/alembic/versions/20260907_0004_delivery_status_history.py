"""delivery status history for controlled status updates"""
from alembic import op
import sqlalchemy as sa
revision="20260907_0004";down_revision="20260907_0003";branch_labels=None;depends_on=None
def upgrade():
    op.add_column("deliveries",sa.Column("status_history",sa.JSON(),nullable=False,server_default="[]"))
def downgrade():
    op.drop_column("deliveries","status_history")
