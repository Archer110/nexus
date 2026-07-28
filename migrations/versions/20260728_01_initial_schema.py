"""Create the inventory and order ledger schema.

Revision ID: 20260728_01
Revises:
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory",
        sa.Column("product_id", sa.String(length=24), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stock >= 0",
            name="ck_inventory_stock_nonnegative",
        ),
        sa.PrimaryKeyConstraint("product_id"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "customer_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "customer_email",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "shipping_address",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("zip_code", sa.String(length=20), nullable=False),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "Processing",
                "Shipped",
                "Delivered",
                "Cancelled",
                name="order_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "total_amount >= 0",
            name="ck_orders_total_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orders_created_at",
        "orders",
        ["created_at"],
    )
    op.create_index(
        "ix_orders_customer_email",
        "orders",
        ["customer_email"],
    )
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column(
            "product_id_str",
            sa.String(length=24),
            nullable=False,
        ),
        sa.Column(
            "product_name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "product_image",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column("product_specs", sa.JSON(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "price_at_purchase",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.CheckConstraint(
            "price_at_purchase >= 0",
            name="ck_order_items_price_nonnegative",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_order_items_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_items_product_id",
        "order_items",
        ["product_id_str"],
    )


def downgrade():
    op.drop_index(
        "ix_order_items_product_id",
        table_name="order_items",
    )
    op.drop_table("order_items")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index(
        "ix_orders_customer_email",
        table_name="orders",
    )
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_table("orders")

    op.drop_table("inventory")
