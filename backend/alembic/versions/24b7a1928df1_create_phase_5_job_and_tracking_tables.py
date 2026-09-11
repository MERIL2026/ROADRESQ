"""create_phase_5_job_and_tracking_tables

Revision ID: 24b7a1928df1
Revises: 16a620519dc3
Create Date: 2026-09-11 11:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "24b7a1928df1"
down_revision: Union[str, None] = "16a620519dc3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. provider_location_updates
    op.create_table(
        "provider_location_updates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("booking_id", sa.UUID(), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("accuracy_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("heading", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("speed_kmh", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_provider_location_updates_booking_id"),
        "provider_location_updates",
        ["booking_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_location_updates_provider_id"),
        "provider_location_updates",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_provider_location_updates_booking_recorded",
        "provider_location_updates",
        ["booking_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_provider_location_updates_provider_recorded",
        "provider_location_updates",
        ["provider_id", "recorded_at"],
        unique=False,
    )

    # 2. job_cards
    op.create_table(
        "job_cards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("booking_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("mechanic_user_id", sa.UUID(), nullable=True),
        sa.Column("job_status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("provider_notes", sa.Text(), nullable=True),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        sa.Column("completion_evidence_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mechanic_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_index(
        op.f("ix_job_cards_booking_id"),
        "job_cards",
        ["booking_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_job_cards_provider_id"),
        "job_cards",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_cards_mechanic_user_id"),
        "job_cards",
        ["mechanic_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_cards_provider_status",
        "job_cards",
        ["provider_id", "job_status"],
        unique=False,
    )

    # 3. inspections
    op.create_table(
        "inspections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_card_id", sa.UUID(), nullable=False),
        sa.Column("odometer_km", sa.Integer(), nullable=True),
        sa.Column("overall_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_card_id"], ["job_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inspections_job_card_id"),
        "inspections",
        ["job_card_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inspections_created_by"),
        "inspections",
        ["created_by"],
        unique=False,
    )

    # 4. inspection_items
    op.create_table(
        "inspection_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("inspection_id", sa.UUID(), nullable=False),
        sa.Column("component", sa.String(length=100), nullable=False),
        sa.Column("condition", sa.String(length=40), nullable=False),
        sa.Column("finding", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inspection_items_inspection_id"),
        "inspection_items",
        ["inspection_id"],
        unique=False,
    )

    # 5. estimates
    op.create_table(
        "estimates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_card_id", sa.UUID(), nullable=False),
        sa.Column("estimate_number", sa.String(length=30), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.UUID(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_card_id"], ["job_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estimate_number"),
    )
    op.create_index(
        op.f("ix_estimates_estimate_number"),
        "estimates",
        ["estimate_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_estimates_job_card_id"),
        "estimates",
        ["job_card_id"],
        unique=False,
    )
    op.create_index(
        "ix_estimates_job_card_status",
        "estimates",
        ["job_card_id", "status"],
        unique=False,
    )

    # 6. estimate_items
    op.create_table(
        "estimate_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("estimate_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["estimate_id"], ["estimates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_estimate_items_estimate_id"),
        "estimate_items",
        ["estimate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_estimate_items_estimate_id"), table_name="estimate_items")
    op.drop_table("estimate_items")

    op.drop_index("ix_estimates_job_card_status", table_name="estimates")
    op.drop_index(op.f("ix_estimates_job_card_id"), table_name="estimates")
    op.drop_index(op.f("ix_estimates_estimate_number"), table_name="estimates")
    op.drop_table("estimates")

    op.drop_index(op.f("ix_inspection_items_inspection_id"), table_name="inspection_items")
    op.drop_table("inspection_items")

    op.drop_index(op.f("ix_inspections_created_by"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_job_card_id"), table_name="inspections")
    op.drop_table("inspections")

    op.drop_index("ix_job_cards_provider_status", table_name="job_cards")
    op.drop_index(op.f("ix_job_cards_mechanic_user_id"), table_name="job_cards")
    op.drop_index(op.f("ix_job_cards_provider_id"), table_name="job_cards")
    op.drop_index(op.f("ix_job_cards_booking_id"), table_name="job_cards")
    op.drop_table("job_cards")

    op.drop_index("ix_provider_location_updates_provider_recorded", table_name="provider_location_updates")
    op.drop_index("ix_provider_location_updates_booking_recorded", table_name="provider_location_updates")
    op.drop_index(op.f("ix_provider_location_updates_provider_id"), table_name="provider_location_updates")
    op.drop_index(op.f("ix_provider_location_updates_booking_id"), table_name="provider_location_updates")
    op.drop_table("provider_location_updates")
