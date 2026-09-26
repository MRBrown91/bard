"""Initial Bard domain schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("auth_provider", sa.String(100), nullable=False),
        sa.Column("auth_subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        *_timestamps(),
    )
    op.create_index("uq_users_auth_identity", "users", ["auth_provider", "auth_subject"], unique=True)

    op.create_table(
        "campaigns",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"])

    op.create_table(
        "campaign_members",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        *_timestamps(),
    )
    op.create_index("uq_campaign_members_campaign_user", "campaign_members", ["campaign_id", "user_id"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("session_number", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_sessions_campaign_id", "sessions", ["campaign_id"])
    op.create_index("uq_sessions_campaign_number", "sessions", ["campaign_id", "session_number"], unique=True)

    op.create_table(
        "entities",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_entities_campaign_id", "entities", ["campaign_id"])
    op.create_index("ix_entities_campaign_name", "entities", ["campaign_id", "name"])

    op.create_table(
        "entity_aliases",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_entity_aliases_entity_id", "entity_aliases", ["entity_id"])

    for table, fields in {
        "actors": [
            sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), primary_key=True),
            sa.Column("voice_instructions", sa.Text()), sa.Column("personality", sa.Text()),
            sa.Column("motivation", sa.Text()), sa.Column("appearance", sa.Text()),
        ],
        "players": [
            sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), primary_key=True),
            sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        ],
        "player_characters": [
            sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), primary_key=True),
            sa.Column("player_id", _uuid(), sa.ForeignKey("players.entity_id"), nullable=False),
        ],
        "locations": [
            sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), primary_key=True),
            sa.Column("environment", sa.Text()), sa.Column("atmosphere", sa.Text()),
        ],
        "items": [
            sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), primary_key=True),
            sa.Column("physical_description", sa.Text()), sa.Column("effect_description", sa.Text()),
        ],
        "factions": [
            sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), primary_key=True),
            sa.Column("purpose", sa.Text()), sa.Column("description", sa.Text()),
        ],
    }.items():
        op.create_table(table, *fields, *_timestamps())

    op.create_index("ix_players_user_id", "players", ["user_id"])
    op.create_index("ix_player_characters_player_id", "player_characters", ["player_id"])

    op.create_table(
        "documents",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("session_id", _uuid(), sa.ForeignKey("sessions.id")),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(50)),
        sa.Column("source_reference", sa.String(500)),
        *_timestamps(),
    )
    op.create_index("ix_documents_campaign_id", "documents", ["campaign_id"])

    op.create_table(
        "document_statements",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("document_id", _uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_document_statements_document_position", "document_statements", ["document_id", "position"])

    op.create_table(
        "events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("game_time", sa.String(255)),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        *_timestamps(),
    )
    op.create_index("ix_events_campaign_id", "events", ["campaign_id"])

    op.create_table(
        "entity_facts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("statement_id", _uuid(), sa.ForeignKey("document_statements.id")),
        sa.Column("entity_id", _uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("event_id", _uuid(), sa.ForeignKey("events.id")),
        sa.Column("fact_type", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        *_timestamps(),
    )
    op.create_index("ix_entity_facts_campaign_entity", "entity_facts", ["campaign_id", "entity_id"])
    op.create_index("ix_entity_facts_statement_id", "entity_facts", ["statement_id"])
    op.create_index("ix_entity_facts_event_id", "entity_facts", ["event_id"])

    op.create_table(
        "entity_relationship_facts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("statement_id", _uuid(), sa.ForeignKey("document_statements.id")),
        sa.Column("source_entity_id", _uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("target_entity_id", _uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("event_id", _uuid(), sa.ForeignKey("events.id")),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        *_timestamps(),
    )
    op.create_index("ix_relationship_facts_campaign_source", "entity_relationship_facts", ["campaign_id", "source_entity_id"])
    op.create_index("ix_relationship_facts_campaign_target", "entity_relationship_facts", ["campaign_id", "target_entity_id"])
    op.create_index("ix_relationship_facts_statement_id", "entity_relationship_facts", ["statement_id"])
    op.create_index("ix_relationship_facts_event_id", "entity_relationship_facts", ["event_id"])

    op.create_table(
        "entity_relationships",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("campaign_id", _uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("source_entity_id", _uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("target_entity_id", _uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("relationship_fact_id", _uuid(), sa.ForeignKey("entity_relationship_facts.id"), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_relationships_campaign_source", "entity_relationships", ["campaign_id", "source_entity_id"])
    op.create_index("ix_relationships_campaign_target", "entity_relationships", ["campaign_id", "target_entity_id"])
    op.create_index("ix_relationships_fact_id", "entity_relationships", ["relationship_fact_id"])

    op.create_table(
        "entity_fact_audiences",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("fact_id", _uuid(), sa.ForeignKey("entity_facts.id"), nullable=False),
        sa.Column("audience_type", sa.String(30), nullable=False, server_default="general"),
        sa.Column("player_id", _uuid(), sa.ForeignKey("players.entity_id")),
        *_timestamps(),
    )
    op.create_index("ix_fact_audiences_fact_id", "entity_fact_audiences", ["fact_id"])

    op.create_table(
        "entity_relationship_fact_audiences",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("fact_id", _uuid(), sa.ForeignKey("entity_relationship_facts.id"), nullable=False),
        sa.Column("audience_type", sa.String(30), nullable=False, server_default="general"),
        sa.Column("player_id", _uuid(), sa.ForeignKey("players.entity_id")),
        *_timestamps(),
    )
    op.create_index("ix_relationship_fact_audiences_fact_id", "entity_relationship_fact_audiences", ["fact_id"])


def downgrade() -> None:
    for table in [
        "entity_relationship_fact_audiences",
        "entity_fact_audiences",
        "entity_relationships",
        "entity_relationship_facts",
        "entity_facts",
        "events",
        "document_statements",
        "documents",
        "factions",
        "items",
        "locations",
        "player_characters",
        "players",
        "actors",
        "entity_aliases",
        "entities",
        "sessions",
        "campaign_members",
        "campaigns",
        "users",
    ]:
        op.drop_table(table)
