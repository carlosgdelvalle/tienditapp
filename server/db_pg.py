"""PostgreSQL tenancy-aware connection pool for Abarpay.

This module is the production data path: the SQLite demo module
'server/db.py' is left untouched. It opens a psycopg connection pool,
assumes the single service role 'abarpay_app' on every connection (the role
is NOLOGIN, not a superuser, and not a table owner), and exposes
set_tenant_context to set the per-transaction RLS context variables
'app.tenant_id' and 'app.user_id'.

The context is set with is_local = true (equivalent to SET LOCAL), so it
reverts automatically when the transaction commits or rolls back. Global or
session values are never set, which keeps a reused pooled connection from
leaking one tenant's context into the next request.
"""

from __future__ import annotations

import getpass
import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool

__all__ = [
    "SERVICE_ROLE",
    "DEFAULT_DSN",
    "create_pool",
    "set_tenant_context",
    "pool_connection",
]

SERVICE_ROLE = "abarpay_app"

# Local development default (trust auth). Override with ABARPAY_PG_DSN.
DEFAULT_DSN = os.environ.get("ABARPAY_PG_DSN") or (
    "host=127.0.0.1 port=5432 dbname=abarpay_dev user=" + getpass.getuser()
)


def _configure(conn: psycopg.Connection[object]) -> None:
    """Assume the least-privileged service role on every pooled connection.

    SET ROLE is session-level (not transactional), so it is run with autocommit
    on: leaving the connection INTRANS here would make psycopg_pool discard it.
    """

    conn.autocommit = True
    try:
        conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(SERVICE_ROLE)))
    finally:
        conn.autocommit = False


def create_pool(
    conninfo: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 10,
    **kwargs: object,
) -> ConnectionPool:
    """Build a psycopg connection pool whose connections run as abarpay_app."""

    return ConnectionPool(
        conninfo or DEFAULT_DSN,
        min_size=min_size,
        max_size=max_size,
        open=True,
        configure=_configure,
        kwargs=kwargs,
    )


def set_tenant_context(
    conn: psycopg.Connection[object],
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    """Set the RLS context for the current transaction.

    The third argument 'true' is 'is_local', i.e. 'SET LOCAL': the value is
    reverted on COMMIT or ROLLBACK. NULLIF in the policies also covers the
    empty-string marker left on a reused connection.
    """

    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        cur.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))


@contextmanager
def pool_connection(pool: ConnectionPool) -> Iterator[psycopg.Connection[object]]:
    """Context manager that checks a connection out of the pool and back in."""

    with pool.connection() as conn:
        yield conn
