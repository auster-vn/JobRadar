# Supabase migrations

Application tables and indexes are versioned by the root Alembic chain in
`migrations/versions/`. The SQL migration in this directory is the managed
Supabase layer: Auth identity synchronization, RLS/grants, view security, and
the private Storage bucket.

Apply in this order:

1. Run `alembic upgrade head` with `MIGRATION_DATABASE_URL`.
2. Convert the URL scheme for libpq and run
   `psql "${MIGRATION_DATABASE_URL/postgresql+asyncpg:/postgresql:}" -v ON_ERROR_STOP=1 -f database/schema.sql`.

The `202608150000` file is a declarative SQL mirror of the managed-domain
tables added by Alembic 008. The `202608150001` file applies Supabase security
and Storage. The Render Blueprint performs both steps on every release. Both
files are idempotent and deliberately refuse to run unless Alembic has created
the 008 managed-domain schema, preventing schema ownership conflicts while still
allowing later Alembic descendants.
