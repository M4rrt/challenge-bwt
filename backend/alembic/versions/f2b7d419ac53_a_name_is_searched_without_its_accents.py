"""a name is searched without its accents

Revision ID: f2b7d419ac53
Revises: d8f1a5c37b92
Create Date: 2026-09-24

The chat list is filtered by the name of the person somebody was talking to,
and the names in it are Brazilian. Somebody looking for João types "joao" about
as often as they type "João", and the monolith has both spellings stored for
different people. Matched exactly, the search box fails on the most common
surnames in the Company's own country — and fails silently, because an empty
list reads as "no such thread".

Three objects, each needed by the one after it:

- `unaccent`, which is the normalisation itself.
- `immutable_unaccent`, a wrapper. `unaccent(text)` is only STABLE, because it
  reads whichever dictionary the search path resolves — so it cannot appear in
  an index. The two-argument form names the dictionary outright, which is what
  makes the wrapper honestly immutable rather than merely declared so.
- `pg_trgm` and a GIN index over the wrapped column. A btree over the
  expression would be dead weight: the filter is `ILIKE '%...%'`, and a leading
  wildcard is exactly what a btree cannot answer. Trigrams are the index type
  that serves this query, and the ticket's premise — hundreds of threads, found
  by typing — is what makes an unindexed scan of every profile worth avoiding.

Both extensions have to be creatable by the migration's role. They are in the
allowed list on RDS, and the compose Postgres runs as the database owner; a
managed Postgres that forbids them fails here, loudly, rather than silently
returning nothing for an accented name.
"""

from alembic import op

revision = "f2b7d419ac53"
down_revision = "d8f1a5c37b92"
branch_labels = None
depends_on = None

_INDEX = "ix_user_profiles_display_name_unaccented"

_FUNCTION = """
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$ SELECT public.unaccent('public.unaccent', $1) $$
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(_FUNCTION)
    op.execute(
        f"CREATE INDEX {_INDEX} ON user_profiles "
        "USING gin (immutable_unaccent(display_name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # The extensions stay. Dropping one takes every other index and default
    # built on it with it, and nothing here knows whether something outside
    # this migration has come to depend on them.
