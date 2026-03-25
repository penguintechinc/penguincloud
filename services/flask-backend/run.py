#!/usr/bin/env python3
"""Flask Backend Entry Point."""

import os
import sys
import time

from app import create_app
from app.auth import hash_password
from app.config import Config


def wait_for_database(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """Wait for database to be available."""
    from pydal import DAL

    db_uri = Config.get_db_uri()
    print(f"Waiting for database connection: {Config.DB_HOST}:{Config.DB_PORT}")

    for attempt in range(1, max_retries + 1):
        try:
            db = DAL(db_uri, pool_size=1, migrate=False)
            db.executesql("SELECT 1")
            db.close()
            print(f"Database connection successful after {attempt} attempt(s)")
            return True
        except Exception as e:
            print(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(retry_delay)

    return False


def create_default_admin():
    """Create default admin user if no users exist."""
    from app.models import create_user, get_db, get_user_by_email

    db = get_db()
    user_count = db(db.users).count()

    if user_count == 0:
        admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
        admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme123")

        # Check if admin already exists (shouldn't, but safety check)
        existing = get_user_by_email(admin_email)
        if not existing:
            print(f"Creating default admin user: {admin_email}")
            create_user(
                email=admin_email,
                password_hash=hash_password(admin_password),
                full_name="System Administrator",
                role="admin",
            )
            print("Default admin user created successfully")
            print("WARNING: Change the default password immediately!")
        else:
            print("Admin user already exists")
    else:
        print(
            f"Database has {user_count} existing user(s), skipping default admin creation"
        )


def main():
    """Main entry point."""
    # Wait for database
    if not wait_for_database():
        print("ERROR: Could not connect to database after maximum retries")
        sys.exit(1)

    # Create Flask app
    app = create_app()

    # Create default admin user
    with app.app_context():
        create_default_admin()

    # Get configuration
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    print(f"Starting Flask backend on {host}:{port}")

    if debug:
        # Development mode with auto-reload
        app.run(host=host, port=port, debug=True)
    else:
        # Production mode - use gunicorn instead
        # This is just for simple testing; use gunicorn in production
        app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
