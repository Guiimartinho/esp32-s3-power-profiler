from __future__ import annotations

import threading

import pytest

from s3_power_profiler.errors import TransportClosedError
from s3_power_profiler.transport.base import Transport
from s3_power_profiler.transport.memory import MemoryTransport, memory_pair

SHORT_WAIT = 0.01
THREAD_LIMIT = 5.0


def test_ends_satisfy_the_transport_interface() -> None:
    near, far = memory_pair()
    transports: list[Transport] = [near, far]

    assert all(isinstance(transport, MemoryTransport) for transport in transports)


def test_bytes_written_at_one_end_are_read_at_the_other() -> None:
    near, far = memory_pair()

    near.write(b"to far")
    far.write(b"to near")

    assert far.read(64, 0) == b"to far"
    assert near.read(64, 0) == b"to near"


def test_writes_are_joined_and_reads_can_be_partial() -> None:
    near, far = memory_pair()
    near.write(b"abc")
    near.write(b"defg")

    assert far.read(2, 0) == b"ab"
    assert far.read(64, 0) == b"cdefg"
    assert far.read(64, 0) == b""


def test_nothing_is_echoed_back_to_the_writer() -> None:
    near, _far = memory_pair()

    near.write(b"data")

    assert near.read(64, 0) == b""


@pytest.mark.parametrize("timeout", [0, -1.0, SHORT_WAIT])
def test_read_returns_empty_when_the_timeout_expires(timeout: float) -> None:
    _near, far = memory_pair()

    assert far.read(64, timeout) == b""


@pytest.mark.parametrize("max_bytes", [0, -1])
def test_read_rejects_a_size_that_is_not_positive(max_bytes: int) -> None:
    near, _far = memory_pair()

    with pytest.raises(ValueError, match="max_bytes"):
        near.read(max_bytes, 0)


def test_closed_end_refuses_to_read_and_write() -> None:
    near, _far = memory_pair()

    near.close()

    assert near.closed
    with pytest.raises(TransportClosedError, match="is closed"):
        near.read(64, 0)
    with pytest.raises(TransportClosedError, match="is closed"):
        near.write(b"data")


def test_other_end_reads_what_was_sent_before_the_close() -> None:
    near, far = memory_pair()
    near.write(b"last words")

    near.close()

    assert not far.closed
    assert far.read(4, 0) == b"last"
    assert far.read(64, 0) == b" words"
    with pytest.raises(TransportClosedError, match="other end closed"):
        far.read(64, 0)


def test_other_end_cannot_write_after_the_close() -> None:
    near, far = memory_pair()

    near.close()

    with pytest.raises(TransportClosedError, match="other end closed"):
        far.write(b"data")


def test_close_can_be_repeated() -> None:
    near, _far = memory_pair()

    near.close()
    near.close()

    assert near.closed


def test_pump_runs_when_there_is_nothing_to_read() -> None:
    near, far = memory_pair()
    calls = []

    def peer() -> None:
        calls.append(far.read(64, 0))
        far.write(b"answer")

    near.set_pump(peer)
    near.write(b"question")

    assert near.read(64, 0) == b"answer"
    assert calls == [b"question"]


def test_pump_does_not_run_while_data_is_waiting() -> None:
    near, far = memory_pair()
    calls = []
    near.set_pump(lambda: calls.append("pumped"))
    far.write(b"ready")

    assert near.read(64, 0) == b"ready"
    assert calls == []


def test_pump_can_be_removed() -> None:
    near, _far = memory_pair()
    calls = []
    near.set_pump(lambda: calls.append("pumped"))
    near.set_pump(None)

    assert near.read(64, 0) == b""
    assert calls == []


def test_read_without_limit_waits_for_a_write_from_another_thread() -> None:
    near, far = memory_pair()
    received = []
    reader = threading.Thread(target=lambda: received.append(far.read(64, None)))
    reader.start()

    near.write(b"late")
    reader.join(THREAD_LIMIT)

    assert not reader.is_alive()
    assert received == [b"late"]


def test_close_wakes_a_reader_in_another_thread() -> None:
    near, far = memory_pair()
    outcome: list[type[BaseException] | None] = []

    def read() -> None:
        try:
            far.read(64, None)
        except TransportClosedError as error:
            outcome.append(type(error))
        else:
            outcome.append(None)

    reader = threading.Thread(target=read)
    reader.start()

    near.close()
    reader.join(THREAD_LIMIT)

    assert not reader.is_alive()
    assert outcome == [TransportClosedError]
