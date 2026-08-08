"""gRPC surface for the portal backend — not yet implemented.

`server.py` was removed during the Flask→Quart migration (Phase 1a). It was
unreachable (no importer anywhere in the repo), its protos were never
compiled, and it called APIs this codebase does not have (`from app import
db`, Flask-SQLAlchemy `db.User.query`). It also still validated tokens with
the hand-rolled HS256 scheme this phase replaced, defaulting the signing
secret to the literal "dev-secret".

`protos/template.proto` is kept as the design artifact. A real
implementation must follow backend.md: versioned proto packages
(`myservice.v1`), an `api_version` field routed at runtime, penguin-aaa
token verification (never a local HS256 secret), and SPIFFE/mTLS identity.
"""
