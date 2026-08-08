"""
Custom exceptions for receiver client operations.
"""


class ReceiverClientError(Exception):
    """Base exception for receiver client errors."""

    pass


class AuthenticationError(ReceiverClientError):
    """Raised when authentication fails."""

    pass


class ConnectionError(ReceiverClientError):
    """Raised when connection to receiver fails."""

    pass


class SubmissionError(ReceiverClientError):
    """Raised when data submission fails."""

    pass


class TokenExpiredError(AuthenticationError):
    """Raised when JWT token has expired."""

    pass
