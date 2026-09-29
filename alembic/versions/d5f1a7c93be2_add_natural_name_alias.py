"""add_natural_name_alias

Hold each entity's own name in ``entity_aliases`` as a ``name`` row, so every
term the matcher can recognise lives in one table. See ADR-027.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5f1a7c93be2"
down_revision: str | Sequence[str] | None = "c68879a1a409"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIND = sa.Column(
    "kind",
    sa.String(10),
    nullable=False,
    server_default="alias",
)


def upgrade() -> None:
    op.add_column("entity_aliases", KIND)

    # Backfill a name row for every entity, soft deleted ones included and
    # stamped, so the invariant is total rather than partial: a retcon then
    # un-deletes the row instead of having to invent one.
    #
    # An entity that already carries an alias equal to its own name adopts that
    # row rather than gaining a second, identical one, which the
    # (entity_id, alias) unique index would reject. None exist today; the guard
    # is here so the migration is correct on any other database.
    op.execute(
        """
        UPDATE entity_aliases AS a
           SET kind = 'name'
          FROM entities AS e
         WHERE a.entity_id = e.id
           AND a.alias = e.name
           AND a.deleted_at IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO entity_aliases (id, entity_id, alias, kind, deleted_at)
        SELECT gen_random_uuid()::uuid, e.id, e.name, 'name', e.deleted_at
          FROM entities AS e
         WHERE NOT EXISTS (
                   SELECT 1 FROM entity_aliases AS a
                    WHERE a.entity_id = e.id AND a.alias = e.name
               )
        """
    )

    op.create_index(
        "uq_entity_aliases_one_name",
        "entity_aliases",
        ["entity_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'name' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_entity_aliases_one_name", table_name="entity_aliases")
    op.execute("DELETE FROM entity_aliases WHERE kind = 'name'")
    op.drop_column("entity_aliases", "kind")
