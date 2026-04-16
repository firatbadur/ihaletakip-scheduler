"""Custom exceptions for the scheduler service."""
from __future__ import annotations


class SchedulerError(Exception):
    """Base class for all scheduler exceptions."""


class EkapError(SchedulerError):
    """EKAP API-related errors."""


class TenderNotFound(EkapError):
    """The requested tender could not be retrieved from EKAP."""


class RateLimited(EkapError):
    """A 429 or Retry-After was received from an upstream service."""


class FirebaseError(SchedulerError):
    """Firebase/Firestore-related errors."""


class FcmTokenInvalid(FirebaseError):
    """The FCM token is unregistered or invalid."""
