"""Exceptions for the De'Longhi Comfort integration."""


class DeLonghiError(Exception):
    """Base exception for integration-specific failures."""


class DeLonghiAuthError(DeLonghiError):
    """Credentials were rejected; the user must reauthenticate."""


class DeLonghiConnectionError(DeLonghiError):
    """A request failed or returned unusable data; retry without changing credentials."""
