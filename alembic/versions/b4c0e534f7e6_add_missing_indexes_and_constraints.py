"""add_missing_indexes_and_constraints"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b4c0e534f7e6"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Unique constraint on entity_aliases (entity_id, alias)
    op.create_index(
        "uq_entity_aliases_entity_alias",
        "entity_aliases",
        ["entity_id", "alias"],
        unique=True,
    )

    # Index on documents.session_id
    op.create_index(
        "ix_documents_session_id",
        "documents",
        ["session_id"],
    )

    # Index on entity_relationship_facts.source_entity_id
    op.create_index(
        "ix_relationship_facts_source_entity_id",
        "entity_relationship_facts",
        ["source_entity_id"],
    )

    # Index on entity_relationship_facts.target_entity_id
    op.create_index(
        "ix_relationship_facts_target_entity_id",
        "entity_relationship_facts",
        ["target_entity_id"],
    )

    # Index on entity_fact_audiences.player_id
    op.create_index(
        "ix_fact_audiences_player_id",
        "entity_fact_audiences",
        ["player_id"],
    )

    # Index on entity_relationship_fact_audiences.player_id
    op.create_index(
        "ix_relationship_fact_audiences_player_id",
        "entity_relationship_fact_audiences",
        ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_relationship_fact_audiences_player_id", table_name="entity_relationship_fact_audiences")
    op.drop_index("ix_fact_audiences_player_id", table_name="entity_fact_audiences")
    op.drop_index("ix_relationship_facts_target_entity_id", table_name="entity_relationship_facts")
    op.drop_index("ix_relationship_facts_source_entity_id", table_name="entity_relationship_facts")
    op.drop_index("ix_documents_session_id", table_name="documents")
    op.drop_index("uq_entity_aliases_entity_alias", table_name="entity_aliases")