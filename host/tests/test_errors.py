from __future__ import annotations

import pytest

from s3_power_profiler.errors import (
    CommandError,
    PayloadError,
    ProfilerError,
    ProtocolError,
    ResponseTimeoutError,
    TransportClosedError,
    TransportError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        ProtocolError,
        PayloadError,
        TransportError,
        TransportClosedError,
        ResponseTimeoutError,
        CommandError,
    ],
)
def test_every_error_derives_from_the_package_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, ProfilerError)


def test_specific_errors_derive_from_their_family() -> None:
    assert issubclass(PayloadError, ProtocolError)
    assert issubclass(TransportClosedError, TransportError)
    assert issubclass(ResponseTimeoutError, TimeoutError)


def test_response_timeout_keeps_the_command_and_the_time_waited() -> None:
    error = ResponseTimeoutError(0x20, 1.5)

    assert error.command_id == 0x20
    assert error.timeout == 1.5
    assert str(error) == "no response to command 0x20 within 1.5 s"


def test_response_timeout_accepts_a_message() -> None:
    assert str(ResponseTimeoutError(0x20, 1.0, "no response to START")) == "no response to START"


def test_command_error_keeps_the_command_and_the_status() -> None:
    error = CommandError(0x10, 2)

    assert error.command_id == 0x10
    assert error.status_code == 2
    assert str(error) == "command 0x10 failed with status 2"


def test_command_error_accepts_a_message() -> None:
    assert str(CommandError(0x10, 2, "SET_MODE failed: WRONG_STATE")) == (
        "SET_MODE failed: WRONG_STATE"
    )
