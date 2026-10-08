"""Command, response and event payloads.

The envelopes are part of the protocol::

    command payload  = command id u8 | arguments
    response payload = command id u8 | status u8 | data
    event payload    = event id u8 | data

The layouts of the arguments, of the response data and of the event data are
**provisional** until the protocol is frozen. Every one of them is defined in
this module, so the client and the simulator cannot disagree, and a change has
a single place to happen.

Functions named ``build_*`` create a message and functions named ``parse_*``
read one. Arguments are parsed strictly: the length has to match exactly.
Response and event data are read tolerantly: extra trailing bytes are ignored,
so that a newer instrument can append fields.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from s3_power_profiler.errors import PayloadError
from s3_power_profiler.protocol._defs import (
    CAL_TARGET_DAC,
    COMMAND_MAX_PAYLOAD,
    FRAME_MAX_PAYLOAD,
    RANGE_AUTO,
    RANGE_COUNT,
    Command,
    DeviceState,
    Event,
    Fault,
    Mode,
    Status,
)

_ID = struct.Struct("<B")
_RESPONSE_HEADER = struct.Struct("<BB")
_ID_LIMIT = 1 << 8

MAX_COMMAND_ARGUMENTS = COMMAND_MAX_PAYLOAD - _ID.size
"""Largest number of argument bytes a command may carry."""

MAX_RESPONSE_DATA = FRAME_MAX_PAYLOAD - _RESPONSE_HEADER.size
"""Largest number of data bytes a response may carry."""

MAX_EVENT_DATA = FRAME_MAX_PAYLOAD - _ID.size
"""Largest number of data bytes an event may carry."""


# --- Envelopes -------------------------------------------------------------


def _check_id(value: int, what: str) -> None:
    if not 0 <= value < _ID_LIMIT:
        raise ValueError(f"{what} {value} does not fit in 8 bits")


@dataclass(frozen=True, slots=True)
class CommandMessage:
    """A command sent by the host.

    The identifier is kept as a plain number, so that a receiver can answer an
    identifier it does not know.

    Attributes:
        command_id: Identifier of the command.
        arguments: Argument bytes, empty for commands without arguments.

    Raises:
        ValueError: If the identifier or the arguments are outside the limits.
    """

    command_id: int
    arguments: bytes = b""

    def __post_init__(self) -> None:
        _check_id(self.command_id, "command id")
        if len(self.arguments) > MAX_COMMAND_ARGUMENTS:
            raise ValueError(
                f"{len(self.arguments)} argument bytes exceed the limit of {MAX_COMMAND_ARGUMENTS}"
            )
        object.__setattr__(self, "arguments", bytes(self.arguments))


@dataclass(frozen=True, slots=True)
class ResponseMessage:
    """The answer of the instrument to one command.

    Attributes:
        command_id: Identifier of the command being answered.
        status_code: Outcome of the command, a ``Status`` value when known.
        data: Result bytes, empty when the command returns nothing.

    Raises:
        ValueError: If a field is outside the limits.
    """

    command_id: int
    status_code: int
    data: bytes = b""

    def __post_init__(self) -> None:
        _check_id(self.command_id, "command id")
        _check_id(self.status_code, "status code")
        if len(self.data) > MAX_RESPONSE_DATA:
            raise ValueError(f"{len(self.data)} data bytes exceed the limit of {MAX_RESPONSE_DATA}")
        object.__setattr__(self, "data", bytes(self.data))

    @property
    def ok(self) -> bool:
        """True when the command succeeded."""
        return self.status_code == Status.OK


@dataclass(frozen=True, slots=True)
class EventMessage:
    """An unsolicited notification from the instrument.

    Attributes:
        event_id: Identifier of the event, an ``Event`` value when known.
        data: Event data, empty when the event carries none.

    Raises:
        ValueError: If a field is outside the limits.
    """

    event_id: int
    data: bytes = b""

    def __post_init__(self) -> None:
        _check_id(self.event_id, "event id")
        if len(self.data) > MAX_EVENT_DATA:
            raise ValueError(f"{len(self.data)} data bytes exceed the limit of {MAX_EVENT_DATA}")
        object.__setattr__(self, "data", bytes(self.data))


def encode_command(message: CommandMessage) -> bytes:
    """Serialize a command into a frame payload."""
    return _ID.pack(message.command_id) + message.arguments


def decode_command(payload: bytes | bytearray | memoryview) -> CommandMessage:
    """Parse the payload of a command frame.

    Raises:
        PayloadError: If the payload is empty or longer than a command may be.
    """
    if not _ID.size <= len(payload) <= COMMAND_MAX_PAYLOAD:
        raise PayloadError(
            f"command payload of {len(payload)} bytes is outside "
            f"{_ID.size} to {COMMAND_MAX_PAYLOAD}"
        )
    return CommandMessage(command_id=payload[0], arguments=bytes(payload[_ID.size :]))


def encode_response(message: ResponseMessage) -> bytes:
    """Serialize a response into a frame payload."""
    return _RESPONSE_HEADER.pack(message.command_id, message.status_code) + message.data


def decode_response(payload: bytes | bytearray | memoryview) -> ResponseMessage:
    """Parse the payload of a response frame.

    Raises:
        PayloadError: If the payload is shorter than the response header.
    """
    if len(payload) < _RESPONSE_HEADER.size:
        raise PayloadError(
            f"response payload of {len(payload)} bytes is shorter than its "
            f"{_RESPONSE_HEADER.size}-byte header"
        )
    command_id, status_code = _RESPONSE_HEADER.unpack_from(payload)
    return ResponseMessage(
        command_id=command_id,
        status_code=status_code,
        data=bytes(payload[_RESPONSE_HEADER.size :]),
    )


def encode_event(message: EventMessage) -> bytes:
    """Serialize an event into a frame payload."""
    return _ID.pack(message.event_id) + message.data


def decode_event(payload: bytes | bytearray | memoryview) -> EventMessage:
    """Parse the payload of an event frame.

    Raises:
        PayloadError: If the payload is empty.
    """
    if len(payload) < _ID.size:
        raise PayloadError("event payload is empty")
    return EventMessage(event_id=payload[0], data=bytes(payload[_ID.size :]))


def describe_command(command_id: int) -> str:
    """Return the name of a command, or its number when it is not known."""
    try:
        return Command(command_id).name
    except ValueError:
        return f"0x{command_id:02X}"


def describe_status(status_code: int) -> str:
    """Return the name of a status code, or its number when it is not known."""
    try:
        return Status(status_code).name
    except ValueError:
        return f"status {status_code}"


# --- Provisional layouts -----------------------------------------------------
#
# Everything below may change before the protocol is frozen.

_U8 = struct.Struct("<B")
_U16 = struct.Struct("<H")
_INFO = struct.Struct("<BBBBB")
_STATUS = struct.Struct("<BHI")
_CAL_WRITE = struct.Struct("<Bff")


def _pack(layout: struct.Struct, what: str, *values: object) -> bytes:
    """Pack values chosen by the caller, reporting a bad one as ``ValueError``."""
    try:
        return layout.pack(*values)
    except (struct.error, OverflowError) as error:
        # A float too large for 32 bits raises OverflowError, not struct.error.
        raise ValueError(f"{what}: {error}") from error


def _unpack_exact(layout: struct.Struct, data: bytes, what: str) -> tuple[Any, ...]:
    """Unpack arguments, which must have exactly the size of the layout."""
    if len(data) != layout.size:
        raise PayloadError(f"{what} takes {layout.size} argument bytes, got {len(data)}")
    return layout.unpack(data)


def _unpack_prefix(layout: struct.Struct, data: bytes, what: str) -> tuple[Any, ...]:
    """Unpack the start of response or event data, ignoring any extra bytes."""
    if len(data) < layout.size:
        raise PayloadError(f"{what} needs {layout.size} data bytes, got {len(data)}")
    return layout.unpack_from(data)


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Identity of an instrument, returned by GET_INFO.

    Attributes:
        protocol_version: Version of the wire protocol the instrument speaks.
        hardware_revision: Revision of the board, 0 for the first one.
        firmware_version: Firmware version as major, minor and patch numbers.
    """

    protocol_version: int
    hardware_revision: int
    firmware_version: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """State of an instrument, returned by GET_STATUS.

    Attributes:
        state: State of the device state machine.
        faults: Faults that are latched.
        dropped_blocks: Blocks dropped by the instrument since it started.
    """

    state: DeviceState
    faults: Fault
    dropped_blocks: int


@dataclass(frozen=True, slots=True)
class CalibrationWrite:
    """Arguments of CAL_WRITE.

    Attributes:
        target: Range index, or ``CAL_TARGET_DAC`` for the DAC.
        gain: Gain to store.
        offset: Offset to store.
    """

    target: int
    gain: float
    offset: float


def parse_no_arguments(arguments: bytes, what: str) -> None:
    """Check that a command without arguments received none.

    Raises:
        PayloadError: If there are argument bytes.
    """
    if arguments:
        raise PayloadError(f"{what} takes no arguments, got {len(arguments)} bytes")


def build_get_info() -> CommandMessage:
    """Create a GET_INFO command."""
    return CommandMessage(Command.GET_INFO)


def encode_device_info(info: DeviceInfo) -> bytes:
    """Serialize the data of a GET_INFO response.

    Raises:
        ValueError: If a field does not fit in 8 bits.
    """
    return _pack(
        _INFO, "device info", info.protocol_version, info.hardware_revision, *info.firmware_version
    )


def decode_device_info(data: bytes) -> DeviceInfo:
    """Parse the data of a GET_INFO response.

    Raises:
        PayloadError: If the data is too short.
    """
    protocol_version, hardware_revision, major, minor, patch = _unpack_prefix(
        _INFO, data, "GET_INFO"
    )
    return DeviceInfo(
        protocol_version=int(protocol_version),
        hardware_revision=int(hardware_revision),
        firmware_version=(int(major), int(minor), int(patch)),
    )


def build_get_status() -> CommandMessage:
    """Create a GET_STATUS command."""
    return CommandMessage(Command.GET_STATUS)


def encode_device_status(status: DeviceStatus) -> bytes:
    """Serialize the data of a GET_STATUS response.

    Raises:
        ValueError: If a field does not fit in its bytes.
    """
    return _pack(
        _STATUS, "device status", int(status.state), int(status.faults), status.dropped_blocks
    )


def decode_device_status(data: bytes) -> DeviceStatus:
    """Parse the data of a GET_STATUS response.

    Raises:
        PayloadError: If the data is too short or names an unknown state.
    """
    state, faults, dropped_blocks = _unpack_prefix(_STATUS, data, "GET_STATUS")
    try:
        known_state = DeviceState(state)
    except ValueError as error:
        raise PayloadError(f"GET_STATUS reports unknown state {state}") from error
    return DeviceStatus(
        state=known_state, faults=Fault(int(faults)), dropped_blocks=int(dropped_blocks)
    )


def build_set_mode(mode: Mode) -> CommandMessage:
    """Create a SET_MODE command.

    Raises:
        ValueError: If ``mode`` is not a known mode.
    """
    return CommandMessage(Command.SET_MODE, _U8.pack(Mode(mode)))


def parse_set_mode(arguments: bytes) -> Mode:
    """Read the arguments of SET_MODE.

    Raises:
        PayloadError: If the length is wrong or the mode is unknown.
    """
    (value,) = _unpack_exact(_U8, arguments, "SET_MODE")
    try:
        return Mode(value)
    except ValueError as error:
        raise PayloadError(f"SET_MODE got unknown mode {value}") from error


def build_set_voltage(millivolts: int) -> CommandMessage:
    """Create a SET_VOLTAGE command for an output voltage in millivolts.

    Raises:
        ValueError: If the voltage does not fit in 16 bits.
    """
    return CommandMessage(Command.SET_VOLTAGE, _pack(_U16, "voltage in mV", millivolts))


def parse_set_voltage(arguments: bytes) -> int:
    """Read the arguments of SET_VOLTAGE and return the voltage in millivolts.

    Raises:
        PayloadError: If the length is wrong.
    """
    (millivolts,) = _unpack_exact(_U16, arguments, "SET_VOLTAGE")
    return int(millivolts)


def build_dut_power(on: bool) -> CommandMessage:
    """Create a DUT_POWER command that closes or opens the output switch."""
    return CommandMessage(Command.DUT_POWER, _U8.pack(1 if on else 0))


def parse_dut_power(arguments: bytes) -> bool:
    """Read the arguments of DUT_POWER and return True for "on".

    Raises:
        PayloadError: If the length is wrong or the value is neither 0 nor 1.
    """
    (value,) = _unpack_exact(_U8, arguments, "DUT_POWER")
    if value not in (0, 1):
        raise PayloadError(f"DUT_POWER takes 0 or 1, got {value}")
    return bool(value)


def build_set_range(range_index: int | None) -> CommandMessage:
    """Create a SET_RANGE command.

    Args:
        range_index: Range to lock, or None for automatic ranging.

    Raises:
        ValueError: If the range does not exist.
    """
    if range_index is None:
        return CommandMessage(Command.SET_RANGE, _U8.pack(RANGE_AUTO))
    if not 0 <= range_index < RANGE_COUNT:
        raise ValueError(f"range {range_index} is outside 0 to {RANGE_COUNT - 1}")
    return CommandMessage(Command.SET_RANGE, _U8.pack(range_index))


def parse_set_range(arguments: bytes) -> int | None:
    """Read the arguments of SET_RANGE.

    Returns:
        The range to lock, or None for automatic ranging.

    Raises:
        PayloadError: If the length is wrong or the range does not exist.
    """
    (value,) = _unpack_exact(_U8, arguments, "SET_RANGE")
    if value == RANGE_AUTO:
        return None
    if value >= RANGE_COUNT:
        raise PayloadError(f"SET_RANGE got unknown range {value}")
    return int(value)


def build_set_down_n(samples: int) -> CommandMessage:
    """Create a SET_DOWN_N command with the sample count of the step-down rule.

    Raises:
        ValueError: If the count does not fit in 16 bits.
    """
    return CommandMessage(Command.SET_DOWN_N, _pack(_U16, "sample count", samples))


def parse_set_down_n(arguments: bytes) -> int:
    """Read the arguments of SET_DOWN_N and return the sample count.

    Raises:
        PayloadError: If the length is wrong.
    """
    (samples,) = _unpack_exact(_U16, arguments, "SET_DOWN_N")
    return int(samples)


def build_start() -> CommandMessage:
    """Create a START command."""
    return CommandMessage(Command.START)


def build_stop() -> CommandMessage:
    """Create a STOP command."""
    return CommandMessage(Command.STOP)


def build_cal_zero() -> CommandMessage:
    """Create a CAL_ZERO command."""
    return CommandMessage(Command.CAL_ZERO)


def _is_calibration_target(target: int) -> bool:
    return 0 <= target < RANGE_COUNT or target == CAL_TARGET_DAC


def build_cal_write(target: int, gain: float, offset: float) -> CommandMessage:
    """Create a CAL_WRITE command.

    Args:
        target: Range index, or ``CAL_TARGET_DAC`` for the DAC.
        gain: Gain to store, sent as a 32-bit float.
        offset: Offset to store, sent as a 32-bit float.

    Raises:
        ValueError: If the target does not exist or a value cannot be sent.
    """
    if not _is_calibration_target(target):
        raise ValueError(f"calibration target {target} does not exist")
    return CommandMessage(
        Command.CAL_WRITE, _pack(_CAL_WRITE, "calibration values", target, gain, offset)
    )


def parse_cal_write(arguments: bytes) -> CalibrationWrite:
    """Read the arguments of CAL_WRITE.

    Raises:
        PayloadError: If the length is wrong or the target does not exist.
    """
    target, gain, offset = _unpack_exact(_CAL_WRITE, arguments, "CAL_WRITE")
    if not _is_calibration_target(target):
        raise PayloadError(f"CAL_WRITE got unknown target {target}")
    return CalibrationWrite(target=int(target), gain=float(gain), offset=float(offset))


def build_clear_fault() -> CommandMessage:
    """Create a CLEAR_FAULT command."""
    return CommandMessage(Command.CLEAR_FAULT)


def build_fault_raised(faults: Fault) -> EventMessage:
    """Create a FAULT_RAISED event carrying the latched faults."""
    return EventMessage(Event.FAULT_RAISED, _pack(_U16, "fault flags", int(faults)))


def parse_fault_raised(data: bytes) -> Fault:
    """Read the data of a FAULT_RAISED event.

    Raises:
        PayloadError: If the data is too short.
    """
    (faults,) = _unpack_prefix(_U16, data, "FAULT_RAISED")
    return Fault(int(faults))


def build_power_budget_changed(milliwatts: int) -> EventMessage:
    """Create a POWER_BUDGET_CHANGED event with the new budget in milliwatts.

    Raises:
        ValueError: If the budget does not fit in 16 bits.
    """
    return EventMessage(Event.POWER_BUDGET_CHANGED, _pack(_U16, "power budget in mW", milliwatts))


def parse_power_budget_changed(data: bytes) -> int:
    """Read the data of a POWER_BUDGET_CHANGED event, in milliwatts.

    Raises:
        PayloadError: If the data is too short.
    """
    (milliwatts,) = _unpack_prefix(_U16, data, "POWER_BUDGET_CHANGED")
    return int(milliwatts)


def build_state_changed(state: DeviceState) -> EventMessage:
    """Create a STATE_CHANGED event carrying the new state."""
    return EventMessage(Event.STATE_CHANGED, _U8.pack(DeviceState(state)))


def parse_state_changed(data: bytes) -> DeviceState:
    """Read the data of a STATE_CHANGED event.

    Raises:
        PayloadError: If the data is too short or names an unknown state.
    """
    (state,) = _unpack_prefix(_U8, data, "STATE_CHANGED")
    try:
        return DeviceState(state)
    except ValueError as error:
        raise PayloadError(f"STATE_CHANGED reports unknown state {state}") from error
