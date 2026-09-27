"""fix_fk_delete_behavior"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c68879a1a409"
down_revision: str | Sequence[str] | None = "b4c0e534f7e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Change FKs from fact/relationship/event tables to campaigns/entities to RESTRICT
    # This preserves provenance when parent is soft-deleted

    # entity_facts -> campaigns
    op.drop_constraint("entity_facts_campaign_id_fkey", "entity_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_facts_campaign_id_fkey",
        "entity_facts",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_facts -> entities
    op.drop_constraint("entity_facts_entity_id_fkey", "entity_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_facts_entity_id_fkey",
        "entity_facts",
        "entities",
        ["entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_facts -> events
    op.drop_constraint("entity_facts_event_id_fkey", "entity_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_facts_event_id_fkey",
        "entity_facts",
        "events",
        ["event_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationship_facts -> campaigns
    op.drop_constraint("entity_relationship_facts_campaign_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationship_facts_campaign_id_fkey",
        "entity_relationship_facts",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationship_facts -> entities (source)
    op.drop_constraint("entity_relationship_facts_source_entity_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationship_facts_source_entity_id_fkey",
        "entity_relationship_facts",
        "entities",
        ["source_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationship_facts -> entities (target)
    op.drop_constraint("entity_relationship_facts_target_entity_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationship_facts_target_entity_id_fkey",
        "entity_relationship_facts",
        "entities",
        ["target_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationship_facts -> events
    op.drop_constraint("entity_relationship_facts_event_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationship_facts_event_id_fkey",
        "entity_relationship_facts",
        "events",
        ["event_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationships -> campaigns
    op.drop_constraint("entity_relationships_campaign_id_fkey", "entity_relationships", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationships_campaign_id_fkey",
        "entity_relationships",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationships -> entities (source)
    op.drop_constraint("entity_relationships_source_entity_id_fkey", "entity_relationships", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationships_source_entity_id_fkey",
        "entity_relationships",
        "entities",
        ["source_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationships -> entities (target)
    op.drop_constraint("entity_relationships_target_entity_id_fkey", "entity_relationships", type_="foreignkey")
    op.create_foreign_key(
        "entity_relationships_target_entity_id_fkey",
        "entity_relationships",
        "entities",
        ["target_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entity_relationships -> entity_relationship_facts (keep CASCADE - materialized view dies with fact)
    # No change needed - this one stays CASCADE

    # events -> campaigns
    op.drop_constraint("events_campaign_id_fkey", "events", type_="foreignkey")
    op.create_foreign_key(
        "events_campaign_id_fkey",
        "events",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # documents -> campaigns
    op.drop_constraint("documents_campaign_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_campaign_id_fkey",
        "documents",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # documents -> sessions
    op.drop_constraint("documents_session_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_session_id_fkey",
        "documents",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # campaigns -> users
    op.drop_constraint("campaigns_user_id_fkey", "campaigns", type_="foreignkey")
    op.create_foreign_key(
        "campaigns_user_id_fkey",
        "campaigns",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # sessions -> campaigns
    op.drop_constraint("sessions_campaign_id_fkey", "sessions", type_="foreignkey")
    op.create_foreign_key(
        "sessions_campaign_id_fkey",
        "sessions",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # entities -> campaigns
    op.drop_constraint("entities_campaign_id_fkey", "entities", type_="foreignkey")
    op.create_foreign_key(
        "entities_campaign_id_fkey",
        "entities",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Revert all to CASCADE (default)
    # entity_facts
    op.drop_constraint("entity_facts_campaign_id_fkey", "entity_facts", type_="foreignkey")
    op.create_foreign_key("entity_facts_campaign_id_fkey", "entity_facts", "campaigns", ["campaign_id"], ["id"])
    op.drop_constraint("entity_facts_entity_id_fkey", "entity_facts", type_="foreignkey")
    op.create_foreign_key("entity_facts_entity_id_fkey", "entity_facts", "entities", ["entity_id"], ["id"])
    op.drop_constraint("entity_facts_event_id_fkey", "entity_facts", type_="foreignkey")
    op.create_foreign_key("entity_facts_event_id_fkey", "entity_facts", "events", ["event_id"], ["id"])

    # entity_relationship_facts
    op.drop_constraint("entity_relationship_facts_campaign_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key("entity_relationship_facts_campaign_id_fkey", "entity_relationship_facts", "campaigns", ["campaign_id"], ["id"])
    op.drop_constraint("entity_relationship_facts_source_entity_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key("entity_relationship_facts_source_entity_id_fkey", "entity_relationship_facts", "entities", ["source_entity_id"], ["id"])
    op.drop_constraint("entity_relationship_facts_target_entity_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key("entity_relationship_facts_target_entity_id_fkey", "entity_relationship_facts", "entities", ["target_entity_id"], ["id"])
    op.drop_constraint("entity_relationship_facts_event_id_fkey", "entity_relationship_facts", type_="foreignkey")
    op.create_foreign_key("entity_relationship_facts_event_id_fkey", "entity_relationship_facts", "events", ["event_id"], ["id"])

    # entity_relationships
    op.drop_constraint("entity_relationships_campaign_id_fkey", "entity_relationships", type_="foreignkey")
    op.create_foreign_key("entity_relationships_campaign_id_fkey", "entity_relationships", "campaigns", ["campaign_id"], ["id"])
    op.drop_constraint("entity_relationships_source_entity_id_fkey", "entity_relationships", type_="foreignkey")
    op.create_foreign_key("entity_relationships_source_entity_id_fkey", "entity_relationships", "entities", ["source_entity_id"], ["id"])
    op.drop_constraint("entity_relationships_target_entity_id_fkey", "entity_relationships", type_="foreignkey")
    op.create_foreign_key("entity_relationships_target_entity_id_fkey", "entity_relationships", "entities", ["target_entity_id"], ["id"])

    # events
    op.drop_constraint("events_campaign_id_fkey", "events", type_="foreignkey")
    op.create_foreign_key("events_campaign_id_fkey", "events", "campaigns", ["campaign_id"], ["id"])

    # documents
    op.drop_constraint("documents_campaign_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key("documents_campaign_id_fkey", "documents", "campaigns", ["campaign_id"], ["id"])
    op.drop_constraint("documents_session_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key("documents_session_id_fkey", "documents", "sessions", ["session_id"], ["id"])

    # campaigns
    op.drop_constraint("campaigns_user_id_fkey", "campaigns", type_="foreignkey")
    op.create_foreign_key("campaigns_user_id_fkey", "campaigns", "users", ["user_id"], ["id"])

    # sessions
    op.drop_constraint("sessions_campaign_id_fkey", "sessions", type_="foreignkey")
    op.create_foreign_key("sessions_campaign_id_fkey", "sessions", "campaigns", ["campaign_id"], ["id"])

    # entities
    op.drop_constraint("entities_campaign_id_fkey", "entities", type_="foreignkey")
    op.create_foreign_key("entities_campaign_id_fkey", "entities", "campaigns", ["campaign_id"], ["id"])