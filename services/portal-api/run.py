#!/usr/bin/env python3
"""Quart backend entry point: wait for the database, seed, serve via hypercorn.

The container's CMD invokes hypercorn directly against `app:create_app()`;
this script is the local/dev equivalent that additionally waits for the
database and can seed the first admin user.
"""

import asyncio
import os
import sys

from app import create_app
from app.config import Config
from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig
from penguin_dal.quart_ext import get_db
from quart import Quart

#: A seeded admin is a real credential; refuse anything short enough to be a
#: placeholder. There is deliberately no default password — an unset
#: DEFAULT_ADMIN_PASSWORD skips seeding rather than inventing one.
MIN_ADMIN_PASSWORD_LENGTH = 12


async def wait_for_database(app: Quart, max_retries: int = 30, retry_delay: float = 2.0) -> bool:
    """Poll the database until it answers a trivial query, or give up.

    Uses penguin-dal through the app context — the same path the running
    service uses — rather than opening a second, differently-configured
    connection.
    """
    print(f"Waiting for database: {Config.DB_HOST}:{Config.DB_PORT}", flush=True)

    for attempt in range(1, max_retries + 1):
        try:
            async with app.app_context():
                # mypy infers `.executesql` as pydal's dynamic-attribute
                # TableProxy rather than the bound method it resolves to at
                # runtime -- narrow suppression per mypy.ini's documented
                # policy for third-party stub limitations (see background.py).
                await get_db().executesql("SELECT 1")  # type: ignore[operator]
            print(f"Database ready after {attempt} attempt(s)", flush=True)
            return True
        except Exception as e:
            print(
                f"Database attempt {attempt}/{max_retries} failed: {e}",
                file=sys.stderr,
                flush=True,
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)

    return False


async def create_default_admin(app: Quart) -> None:
    """Seed an initial admin user, but only when explicitly configured.

    Skipped unless DEFAULT_ADMIN_PASSWORD is set, so no deployment ever comes
    up with a well-known password baked in.
    """
    from app.auth import hash_password_async
    from app.models import create_user, get_user_by_email

    admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "")
    if not admin_password:
        print(
            "DEFAULT_ADMIN_PASSWORD not set - skipping admin seeding",
            flush=True,
        )
        return

    if len(admin_password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise SystemExit(
            "DEFAULT_ADMIN_PASSWORD must be at least "
            f"{MIN_ADMIN_PASSWORD_LENGTH} characters; refusing to seed a "
            "weak administrator credential."
        )

    admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")

    async with app.app_context():
        db = get_db()
        rows = await db(db.users.id > 0).select(limitby=(0, 1))
        if rows:
            print("Users already exist - skipping admin seeding", flush=True)
            return

        if await get_user_by_email(admin_email):
            print("Admin user already exists", flush=True)
            return

        print(f"Creating default admin user: {admin_email}", flush=True)
        await create_user(
            email=admin_email,
            password_hash=await hash_password_async(admin_password),
            full_name="System Administrator",
            role="admin",
        )
        print(
            "Default admin created - change this password immediately",
            flush=True,
        )


async def main() -> None:
    """Bring up the database, seed if configured, then serve under hypercorn."""
    app = create_app()

    if not await wait_for_database(app):
        print("ERROR: database unreachable after maximum retries", file=sys.stderr)
        raise SystemExit(1)

    await create_default_admin(app)

    # Default to localhost; set HOST=0.0.0.0 explicitly (e.g. via container
    # ENV) when the process needs to accept connections on all interfaces.
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")

    hypercorn_config = HypercornConfig()
    hypercorn_config.bind = [f"{host}:{port}"]
    hypercorn_config.accesslog = "-"

    print(f"Starting Quart backend on {host}:{port} (hypercorn)", flush=True)
    await serve(app, hypercorn_config)


if __name__ == "__main__":
    asyncio.run(main())
