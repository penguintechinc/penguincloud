"""pcli -- the PenguinCloud portal command-line client.

Its command tree (`pcli <product> <resource> list/get`) is discovered from
each connected product's console manifest (the same document
``app.adapters.manifest`` composes for the future generic web renderer),
never compiled per-product -- see ``pcli.commands.resource_group`` for the
Click ``list_commands``/``get_command`` lazy-loading hook that makes that
true.
"""

from __future__ import annotations

__version__ = "0.1.0"
