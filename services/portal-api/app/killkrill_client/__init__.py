"""
Killkrill Receiver Client Module

Provides unified client interface for submitting logs and metrics to Killkrill receivers
with JWT authentication and automatic gRPC/REST protocol fallback.
"""

from .client import ReceiverClient
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    ReceiverClientError,
    SubmissionError,
    TokenExpiredError,
)

__all__ = [
    "ReceiverClient",
    "AuthenticationError",
    "ConnectionError",
    "SubmissionError",
    "ReceiverClientError",
    "TokenExpiredError",
]
__version__ = "1.0.0"
