from __future__ import annotations

from collections.abc import Iterator

import pytest
import serial

from s3_power_profiler.errors import TransportClosedError, TransportError
from s3_power_profiler.transport.base import Transport
from s3_power_profiler.transport.serial import SerialTransport

LOOPBACK = "loop://"
SHORT_WAIT = 0.01


class FakePort:
    """Serial port double that records its use and can be told to fail."""

    def __init__(self) -> None:
        self.is_open = True
        self.incoming = bytearray()
        self.written = bytearray()
        self.timeouts: list[float | None] = []
        self.flushes = 0
        self.closes = 0
        self.error: Exception | None = None
        self._timeout: float | None = None

    @property
    def timeout(self) -> float | None:
        return self._timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self.timeouts.append(value)
        self._timeout = value

    @property
    def in_waiting(self) -> int:
        return len(self.incoming)

    def read(self, size: int = 1) -> bytes:
        if self.error is not None:
            raise self.error
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def write(self, data: bytes, /) -> int | None:
        if self.error is not None:
            raise self.error
        self.written += data
        return len(data)

    def flush(self) -> None:
        self.flushes += 1

    def close(self) -> None:
        self.closes += 1
        self.is_open = False


@pytest.fixture
def loopback() -> Iterator[SerialTransport]:
    transport = SerialTransport.open(LOOPBACK)
    yield transport
    transport.close()


# --- Through the pyserial loopback port --------------------------------------


def test_adapter_satisfies_the_transport_interface(loopback: SerialTransport) -> None:
    transport: Transport = loopback

    transport.write(b"ping")

    assert transport.read(64, SHORT_WAIT) == b"ping"


def test_read_returns_what_is_available_without_waiting_for_more(
    loopback: SerialTransport,
) -> None:
    loopback.write(b"0123456789")

    assert loopback.read(4, SHORT_WAIT) == b"0123"
    assert loopback.read(1, SHORT_WAIT) == b"4"
    assert loopback.read(64, SHORT_WAIT) == b"56789"


@pytest.mark.parametrize("timeout", [0, SHORT_WAIT])
def test_read_returns_empty_when_the_timeout_expires(
    loopback: SerialTransport, timeout: float
) -> None:
    assert loopback.read(64, timeout) == b""


def test_closed_adapter_refuses_to_read_and_write(loopback: SerialTransport) -> None:
    loopback.close()
    loopback.close()

    with pytest.raises(TransportClosedError, match="closed"):
        loopback.read(64, 0)
    with pytest.raises(TransportClosedError, match="closed"):
        loopback.write(b"data")


@pytest.mark.parametrize("url", ["no-such-scheme://device", "port-that-does-not-exist-42"])
def test_open_reports_a_port_that_cannot_be_opened(url: str) -> None:
    with pytest.raises(TransportError, match="cannot open serial port"):
        SerialTransport.open(url)


# --- Through a fake port ------------------------------------------------------


@pytest.mark.parametrize("max_bytes", [0, -1])
def test_read_rejects_a_size_that_is_not_positive(max_bytes: int) -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        SerialTransport(FakePort()).read(max_bytes, 0)


def test_read_asks_for_one_byte_then_for_what_is_waiting() -> None:
    port = FakePort()
    port.incoming += b"abcdef"

    assert SerialTransport(port).read(4, 0.5) == b"abcd"
    assert bytes(port.incoming) == b"ef"


def test_read_returns_a_single_byte_when_nothing_else_is_waiting() -> None:
    port = FakePort()
    port.incoming += b"a"

    assert SerialTransport(port).read(4, 0.5) == b"a"


def test_timeout_is_set_only_when_it_changes() -> None:
    port = FakePort()
    transport = SerialTransport(port)

    transport.read(8, 0.5)
    transport.read(8, 0.5)
    transport.read(8, None)
    transport.read(8, None)
    transport.read(8, 0.25)

    assert port.timeouts == [0.5, None, 0.25]


def test_negative_timeout_does_not_wait() -> None:
    port = FakePort()

    SerialTransport(port).read(8, -1.0)

    assert port.timeouts == [0.0]


def test_write_sends_everything_and_flushes() -> None:
    port = FakePort()

    SerialTransport(port).write(b"frame bytes")

    assert bytes(port.written) == b"frame bytes"
    assert port.flushes == 1


@pytest.mark.parametrize(
    "error", [serial.SerialException("unplugged"), serial.SerialTimeoutException("stuck")]
)
def test_port_failures_become_transport_errors(error: Exception) -> None:
    port = FakePort()
    port.error = error
    transport = SerialTransport(port)

    with pytest.raises(TransportError, match="serial read failed"):
        transport.read(8, 0)
    with pytest.raises(TransportError, match="serial write failed"):
        transport.write(b"data")


def test_port_closed_from_outside_is_reported_as_closed() -> None:
    port = FakePort()
    transport = SerialTransport(port)
    port.is_open = False

    with pytest.raises(TransportClosedError, match="closed"):
        transport.read(8, 0)


def test_close_closes_the_port_once() -> None:
    port = FakePort()
    transport = SerialTransport(port)

    transport.close()
    transport.close()

    assert port.closes == 1
