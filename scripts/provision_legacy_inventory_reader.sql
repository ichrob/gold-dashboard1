-- Run once with psql as the test database owner on the internal Render host.
-- Enter a fresh reader password when prompted. Configure only this password in
-- the scanner's BOB_LEGACY_INVENTORY_PASSWORD secret.
\set ON_ERROR_STOP on
BEGIN;
DO $$
BEGIN
    IF current_database() <> 'bob_archive_restore_test' THEN
        RAISE EXCEPTION 'Expected legacy restore test database';
    END IF;
END $$;
CREATE ROLE bob_legacy_inventory_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
GRANT CONNECT ON DATABASE bob_archive_restore_test TO bob_legacy_inventory_reader;
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT DISTINCT n.nspname, c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r', 'p', 'm')
    LOOP
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO bob_legacy_inventory_reader', item.nspname);
        EXECUTE format('GRANT SELECT ON %I.%I TO bob_legacy_inventory_reader',
                       item.nspname, item.relname);
    END LOOP;
END $$;
ALTER ROLE bob_legacy_inventory_reader SET default_transaction_read_only = on;
\password bob_legacy_inventory_reader
COMMIT;
