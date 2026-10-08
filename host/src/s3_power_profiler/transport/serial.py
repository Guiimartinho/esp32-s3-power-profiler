"""Serial-port transport built on pyserial.

The instrument appears as a USB CDC serial port. The adapter receives the port
object through its constructor, so tests can pass a fake one, and
:meth:`SerialTransport.open` builds the real one from a device name or URL.
"""

from __future__ import annotations

from typing import Protocol

import serial

from s3_power_profiler.errors import TransportClosedError, TransportError

DEFAULT_BAUD_RATE = 115200
"""Baud rate requested when opening a port. A USB CDC port ignores it."""

DEFAULT_WRITE_TIMEOUT = 1.0
"""Seconds a write may block before it fails."""


class SerialPort(Protocol):
    """The part of a pyserial port that the adapter uses."""

    timeout: float | None

    @property
    def is_open(self) -> bool:
        """True while the port is open."""

    @property
    def in_waiting(self) -> int:
        """Number of received bytes waiting to be read."""

    def read(self, size: int = 1) -> bytes:
        """Read up to ``size`` bytes, waiting at most ``timeout`` seconds."""

    def write(self, data: bytes, /) -> int | None:
        """Send ``data``."""

    def flush(self) -> None:
        """Wait until everything written was sent."""

    def close(self) -> None:
        """Close the port."""


class SerialTransport:
    """Transport over a serial port.

    Args:
        port: An open pyserial port, or an object with the same interface.
    """

    def __init__(self, port: SerialPort) -> None:
        self._port = port
        self._closed = False

    @classmethod
    def open(
        cls,
        url: str,
        *,
        baudrate: int = DEFAULT_BAUD_RATE,
        write_timeout: float | None = DEFAULT_WRITE_TIMEOUT,
    ) -> SerialTransport:
        """Open a serial port.

        Args:
            url: Device name such as ``COM5`` or ``/dev/ttyACM0``, or a pyserial
                URL such as ``loop://``.
            baudrate: Baud rate to request.
            write_timeout: Seconds a write may block, or None for no limit.

        Raises:
            TransportError: If the port cannot be opened.
        """
        try:
            port = serial.serial_for_url(url, baudrate=baudrate, write_timeout=write_timeout)
        except (serial.SerialException, ValueError) as error:
            raise TransportError(f"cannot open serial port {url!r}: {error}") from error
        return cls(port)

    def read(self, max_bytes: int, timeout: float | None) -> bytes:
        """Read up to ``max_bytes`` bytes from the port.

        Returns:
            The bytes read, or an empty value if the timeout expired.

        Raises:
            ValueError: If ``max_bytes`` is not positive.
            TransportClosedError: If the port is closed.
            TransportError: If the port failed.
        """
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._ensure_open()
        wait = None if timeout is None else max(timeout, 0.0)
        try:
            if self._port.timeout != wait:
                self._port.timeout = wait
            data = self._port.read(1)
            if data and max_bytes > 1:
                waiting = min(self._port.in_waiting, max_bytes - 1)
                if waiting:
                    data += self._port.read(waiting)
        except serial.SerialException as error:
            raise TransportError(f"serial read failed: {error}") from error
        return bytes(data)

    def write(self, data: bytes) -> None:
        """Send all of ``data`` through the port.

        Raises:
            TransportClosedError: If the port is closed.
            TransportError: If the port failed or the write timed out.
        """
        self._ensure_open()
        try:
            self._port.write(data)
            self._port.flush()
        except serial.SerialException as error:
            raise TransportError(f"serial write failed: {error}") from error

    def close(self) -> None:
        """Close the port. Closing a closed transport does nothing."""
        if self._closed:
            return
        self._closed = True
        self._port.close()

    def _ensure_open(self) -> None:
        if self._closed or not self._port.is_open:
            raise TransportClosedError("the serial port is closed")
