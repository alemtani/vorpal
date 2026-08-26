"""Refusal taxonomy. Do not collapse these classes."""


class VorpalError(Exception):
    """Base error. The message is safe to print to stderr."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class UnsupportedLeague(VorpalError):
    """Permanent refusal: the league format is out of v1 scope."""


class DataRefusal(VorpalError):
    """Fixable by a better file (projections, override, or mapping)."""


class PlatformError(VorpalError):
    """The documented API or projections host failed."""


class UserRefusal(VorpalError):
    """The operator identity or seat cannot be resolved."""
