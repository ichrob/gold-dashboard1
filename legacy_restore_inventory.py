"""Inventory ordinary tables in the expiring Render database using a dedicated login."""
import os
from datetime import datetime, timezone

DB_HOST = "dpg-dbi97pqjnfac73d5q3rg-a"
DB_NAME = "bob_archive_restore_test"
READER = "bob_legacy_inventory_reader"
PASSWORD_ENV = "BOB_LEGACY_INVENTORY_PASSWORD"


def inventory():
    password = os.getenv(PASSWORD_ENV)
    if not password:
        return {"status": "unconfigured"}
    import psycopg
    from psycopg import sql

    try:
        with psycopg.connect(host=DB_HOST, port=5432, dbname=DB_NAME, user=READER,
                             password=password, connect_timeout=3, sslmode="require",
                             options="-c default_transaction_read_only=on -c transaction_timeout=5000 -c statement_timeout=2500 "
                                     "-c lock_timeout=300 -c row_security=off") as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                cur.execute("SELECT current_database(), current_user, rolcreaterole OR "
                            "rolcreatedb OR rolsuper OR rolbypassrls OR rolreplication "
                            "FROM pg_roles WHERE rolname = current_user")
                if cur.fetchone() != (DB_NAME, READER, False):
                    return {"status": "unexpected-role-or-target"}
                cur.execute("""
                    SELECT n.nspname, c.relname, c.relkind
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
                      AND c.relkind IN ('r','m','f','p')
                    ORDER BY n.nspname, c.relname LIMIT 33
                """)
                relations = cur.fetchall()
                if len(relations) > 32:
                    return {"status": "inventory-limit"}
                known = {}
                other_tables = other_rows = 0
                for schema, table, kind in relations:
                    if kind == "f":
                        return {"status": "foreign-table-needs-review"}
                    if kind == "p":
                        continue  # Physical child tables are counted separately.
                    cur.execute(sql.SQL("SELECT count(*) FROM ONLY {}").format(
                        sql.Identifier(schema, table)))
                    count = cur.fetchone()[0]
                    if schema == "bob_replay_audit" and table in (
                            "cold_checkpoints", "history_coverage_reports"):
                        known[table] = count
                    else:
                        other_tables += 1
                        other_rows += count
                return {"status": "observed", "observedAt": datetime.now(timezone.utc).isoformat(),
                        "scope": "local-table-and-materialized-view-row-counts",
                        "knownRows": known, "otherTables": other_tables, "otherRows": other_rows}
    except psycopg.Error as exc:
        return {"status": "unavailable", "sqlstate": exc.sqlstate}


if __name__ == "__main__":
    import json
    print(json.dumps(inventory()))
