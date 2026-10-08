"""Exceptions raised by the package.

Every exception derives from :class:`ProfilerError`, so a caller can catch one type.
A wrong argument passed by the caller raises the built-in ``ValueError`` instead.

This module imports nothing from the package, so every layer can use it.
"""

from __future__ import annotations


class ProfilerError(Exception):
    """Base class of every error raised by this package."""


class ProtocolError(ProfilerError):
    """Received data does not follow the wire protocol."""


class PayloadError(ProtocolError):
    """A payload is too short, too long or inconsistent with its own fields."""


class TransportError(ProfilerError):
    """The byte stream to the instrument failed."""


class TransportClosedError(TransportError):
    """The transport was used after being closed, or the other side closed it."""


class ResponseTimeoutError(ProfilerError, TimeoutError):
    """The instrument did not answer a command in time.

    Attributes:
        command_id: Identifier of the command that got no answer.
        timeout: Time waited, in seconds.
    """

    def __init__(self, command_id: int, timeout: float, message: str | None = None) -> None:
        self.command_id = command_id
        self.timeout = timeout
        super().__init__(
            message or f"no response to command 0x{command_id:02X} within {timeout:g} s"
        )


class CommandError(ProfilerError):
    """The instrument answered a command with a status other than OK.

    Attributes:
        command_id: Identifier of the command that failed.
        status_code: Status code returned by the instrument.
    """

    def __init__(self, command_id: int, status_code: int, message: str | None = None) -> None:
        self.command_id = command_id
        self.status_code = status_code
        super().__init__(message or f"command 0x{command_id:02X} failed with status {status_code}")
