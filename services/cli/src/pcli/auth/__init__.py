"""RFC 8628 device-flow client + platform-secure token storage.

See `device_flow.py` (the client half of the flow whose server half landed
in `app.device_auth`) and `keyring_store.py` (the "never a plaintext file"
persistence layer client.md requires).
"""

from __future__ import annotations
