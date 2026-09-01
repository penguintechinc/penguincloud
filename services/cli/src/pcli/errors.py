"""pcli's own exception hierarchy.

Every exception here carries the exit code ``cli.main`` should return for
it, so a raise site never has to also remember to set ``sys.exit(...)``
correctly.
"""

from __future__ import annotations

from typing import Any

from .exit_codes import (
    EXIT_CONFIG,
    EXIT_GENERAL,
    EXIT_UNAUTHENTICATED,
    exit_code_for_status,
)


class PcliError(Exception):
    """Base for every error pcli raises deliberately (never a bare Exception)."""

    exit_code: int = EXIT_GENERAL

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        """Record the user-facing message and, optionally, override the exit code."""
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class ConfigurationError(PcliError):
    """Bad local configuration -- no portal URL, malformed flags, etc."""

    exit_code = EXIT_CONFIG


class KeyringUnavailableError(PcliError):
    """No usable platform keyring backend, and no PCLI_TOKEN fallback.

    Deliberately its own class rather than a bare ConfigurationError: the
    fix is different (configure a keyring backend, or export PCLI_TOKEN for
    headless/CI use) and the falsification test for the "never a silent
    plaintext-file fallback" requirement asserts on this exact type.
    """

    exit_code = EXIT_CONFIG


class AuthenticationRequiredError(PcliError):
    """No stored credentials, or they could not be refreshed. Run `pcli login`."""

    exit_code = EXIT_UNAUTHENTICATED


class PortalAPIError(PcliError):
    """The portal (or a product behind it) answered with an HTTP error.

    ``status_code``/``body`` are kept for callers that want to inspect the
    portal's own error taxonomy (``app.adapter_errors``) beyond the exit
    code -- e.g. a future ``--verbose`` flag.
    """

    def __init__(self, message: str, *, status_code: int, body: Any = None) -> None:
        """Map ``status_code`` onto pcli's exit-code taxonomy and record the raw body."""
        super().__init__(message, exit_code=exit_code_for_status(status_code))
        self.status_code = status_code
        self.body = body


class ManifestError(PcliError):
    """A served manifest could not be parsed, or its envelope didn't match."""

    exit_code = EXIT_GENERAL


class DeviceFlowError(PcliError):
    """Base for RFC 8628 device-authorization-grant client failures."""

    exit_code = EXIT_UNAUTHENTICATED


class DeviceFlowExpiredError(DeviceFlowError):
    """The device_code expired before the human approved it."""


class DeviceFlowDeniedError(DeviceFlowError):
    """The human explicitly denied the pending authorization."""
