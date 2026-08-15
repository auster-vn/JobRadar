\set ON_ERROR_STOP on

-- JobRadar's application tables are created and versioned by Alembic.
-- This psql entrypoint verifies/mirrors the managed-domain contract, then
-- applies Auth user synchronization, row-level security, grants, and the
-- private candidate-files Storage bucket.
\ir migrations/202608150000_application_schema_contract.sql
\ir migrations/202608150001_supabase_auth_rls_storage.sql
