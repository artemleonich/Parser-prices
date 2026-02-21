"""initial schema

Revision ID: 001
Revises: None
Create Date: 2025-02-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column(
            "subscription_plan",
            sa.Enum("free", "basic", "pro", name="subscriptionplan"),
            nullable=False,
            server_default="free",
        ),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_tracked_products", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "tracked_products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "marketplace",
            sa.Enum("wildberries", "ozon", "yandex_market", name="marketplace"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("previous_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image_url", sa.String(2048), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("parse_errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_tracked_products"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_tracked_products_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id", "marketplace", "external_id",
            name="uq_user_marketplace_product",
        ),
    )
    op.create_index("ix_tracked_products_user_id", "tracked_products", ["user_id"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("original_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_percent", sa.Integer(), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_price_history"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["tracked_products.id"],
            name="fk_price_history_product_id_tracked_products",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_price_history_product_id", "price_history", ["product_id"])
    op.create_index("ix_price_history_recorded_at", "price_history", ["recorded_at"])

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "rule_type",
            sa.Enum(
                "price_drop", "price_rise", "price_below", "price_above", "back_in_stock",
                name="ruletype",
            ),
            nullable=False,
        ),
        sa.Column("threshold_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_alert_rules"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_alert_rules_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["tracked_products.id"],
            name="fk_alert_rules_product_id_tracked_products",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_alert_rules_user_id", "alert_rules", ["user_id"])

    op.create_table(
        "alert_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alert_rule_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("old_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("new_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("message_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_alert_logs"),
        sa.ForeignKeyConstraint(
            ["alert_rule_id"], ["alert_rules.id"],
            name="fk_alert_logs_alert_rule_id_alert_rules",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["tracked_products.id"],
            name="fk_alert_logs_product_id_tracked_products",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("alert_logs")
    op.drop_table("alert_rules")
    op.drop_table("price_history")
    op.drop_table("tracked_products")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS subscriptionplan")
    op.execute("DROP TYPE IF EXISTS marketplace")
    op.execute("DROP TYPE IF EXISTS ruletype")
