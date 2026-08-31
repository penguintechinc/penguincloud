"""`python3 -m pcli` entry point -- delegates to `pcli.cli.main`."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
