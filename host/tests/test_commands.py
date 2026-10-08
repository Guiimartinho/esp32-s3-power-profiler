from __future__ import annotations

import struct
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from s3_power_profiler.errors import PayloadError
from s3_power_profiler.protocol import commands
from s3_power_profiler.protocol._defs import (
    CAL_TARGET_DAC,
    COMMAND_MAX_PAYLOAD,
    FRAME_MAX_PAYLOAD,
    PROTOCOL_VERSION,
    RANGE_AUTO,
    RANGE_COUNT,
    Command,
    DeviceState,
    Event,
    Fault,
    Mode,
    Status,
)
from s3_power_profiler.protocol.commands import (
    MAX_COMMAND_ARGUMENTS,
    MAX_EVENT_DATA,
    MAX_RESPONSE_DATA,
    CalibrationWrite,
    CommandMessage,
    DeviceInfo,
    DeviceStatus,
    EventMessage,
    ResponseMessage,
    decode_command,
    decode_event,
    decode_response,
    encode_command,
    encode_event,
    encode_response,
)

UNKNOWN_ID = 0xEE
identifiers = st.integers(min_value=0, max_value=0xFF)

command_messages = st.builds(
    CommandMessage, command_id=identifiers, arguments=st.binary(max_size=MAX_COMMAND_ARGUMENTS)
)
response_messages = st.builds(
    ResponseMessage, command_id=identifiers, status_code=identifiers, data=st.binary(max_size=64)
)
event_messages = st.builds(EventMessage, event_id=identifiers, data=st.binary(max_size=64))

NamedFrame = Callable[[str], dict[str, Any]]


def payload_of(frame_named: NamedFrame, name: str) -> bytes:
    return bytes.fromhex(frame_named(name)["payload"])


# --- Envelopes against the shared vectors -----------------------------------


def test_get_info_command_matches_shared_vector(frame_named: NamedFrame) -> None:
    payload = payload_of(frame_named, "command_get_info")

    assert decode_command(payload) == CommandMessage(Command.GET_INFO)
    assert encode_command(commands.build_get_info()) == payload


def test_set_voltage_command_matches_shared_vector(frame_named: NamedFrame) -> None:
    payload = payload_of(frame_named, "command_set_voltage_3300mv")

    message = decode_command(payload)

    assert message.command_id == Command.SET_VOLTAGE
    assert commands.parse_set_voltage(message.arguments) == 3300
    assert encode_command(commands.build_set_voltage(3300)) == payload


def test_ok_response_matches_shared_vector(frame_named: NamedFrame) -> None:
    payload = payload_of(frame_named, "response_start_ok")

    message = decode_response(payload)

    assert message == ResponseMessage(Command.START, Status.OK)
    assert message.ok
    assert encode_response(message) == payload


def test_failed_response_matches_shared_vector(frame_named: NamedFrame) -> None:
    payload = payload_of(frame_named, "response_set_mode_wrong_state")

    message = decode_response(payload)

    assert message == ResponseMessage(Command.SET_MODE, Status.WRONG_STATE)
    assert not message.ok
    assert encode_response(message) == payload


def test_fault_event_matches_shared_vector(frame_named: NamedFrame) -> None:
    payload = payload_of(frame_named, "event_fault_overcurrent")

    message = decode_event(payload)

    assert message.event_id == Event.FAULT_RAISED
    assert commands.parse_fault_raised(message.data) == Fault.OVERCURRENT
    assert encode_event(commands.build_fault_raised(Fault.OVERCURRENT)) == payload


# --- Envelope round trips and limits ----------------------------------------


@given(message=command_messages)
def test_command_round_trips(message: CommandMessage) -> None:
    assert decode_command(encode_command(message)) == message


@given(message=response_messages)
def test_response_round_trips(message: ResponseMessage) -> None:
    assert decode_response(encode_response(message)) == message


@given(message=event_messages)
def test_event_round_trips(message: EventMessage) -> None:
    assert decode_event(encode_event(message)) == message


def test_largest_messages_fit_in_their_frames() -> None:
    command = CommandMessage(Command.CAL_WRITE, bytes(MAX_COMMAND_ARGUMENTS))
    response = ResponseMessage(Command.GET_INFO, Status.OK, bytes(MAX_RESPONSE_DATA))
    event = EventMessage(Event.STATE_CHANGED, bytes(MAX_EVENT_DATA))

    assert len(encode_command(command)) == COMMAND_MAX_PAYLOAD
    assert len(encode_response(response)) == FRAME_MAX_PAYLOAD
    assert len(encode_event(event)) == FRAME_MAX_PAYLOAD


def test_messages_store_their_bytes_as_bytes() -> None:
    command = CommandMessage(1, bytearray(b"\x01"))  # type: ignore[arg-type]
    response = ResponseMessage(1, 0, bytearray(b"\x02"))  # type: ignore[arg-type]
    event = EventMessage(1, bytearray(b"\x03"))  # type: ignore[arg-type]

    assert isinstance(command.arguments, bytes)
    assert isinstance(response.data, bytes)
    assert isinstance(event.data, bytes)


def test_decoders_accept_bytearray_and_memoryview() -> None:
    assert decode_command(bytearray(b"\x01\x02")) == CommandMessage(1, b"\x02")
    assert decode_response(memoryview(b"\x01\x00\x03")) == ResponseMessage(1, 0, b"\x03")
    assert decode_event(bytearray(b"\x03\x04")) == EventMessage(3, b"\x04")


@pytest.mark.parametrize("identifier", [-1, 0x100])
def test_messages_reject_an_identifier_outside_8_bits(identifier: int) -> None:
    with pytest.raises(ValueError, match="command id"):
        CommandMessage(identifier)
    with pytest.raises(ValueError, match="command id"):
        ResponseMessage(identifier, 0)
    with pytest.raises(ValueError, match="status code"):
        ResponseMessage(0, identifier)
    with pytest.raises(ValueError, match="event id"):
        EventMessage(identifier)


def test_messages_reject_more_bytes_than_a_frame_carries() -> None:
    with pytest.raises(ValueError, match="argument bytes"):
        CommandMessage(1, bytes(MAX_COMMAND_ARGUMENTS + 1))
    with pytest.raises(ValueError, match="data bytes"):
        ResponseMessage(1, 0, bytes(MAX_RESPONSE_DATA + 1))
    with pytest.raises(ValueError, match="data bytes"):
        EventMessage(1, bytes(MAX_EVENT_DATA + 1))


@pytest.mark.parametrize("size", [0, COMMAND_MAX_PAYLOAD + 1])
def test_decode_command_rejects_a_payload_of_the_wrong_size(size: int) -> None:
    with pytest.raises(PayloadError, match="command payload"):
        decode_command(bytes(size))


@pytest.mark.parametrize("size", [0, 1])
def test_decode_response_rejects_a_payload_shorter_than_its_header(size: int) -> None:
    with pytest.raises(PayloadError, match="response payload"):
        decode_response(bytes(size))


def test_decode_event_rejects_an_empty_payload() -> None:
    with pytest.raises(PayloadError, match="event payload"):
        decode_event(b"")


def test_unknown_identifiers_survive_decoding() -> None:
    assert decode_command(bytes([UNKNOWN_ID])).command_id == UNKNOWN_ID
    assert decode_response(bytes([UNKNOWN_ID, UNKNOWN_ID])).status_code == UNKNOWN_ID
    assert decode_event(bytes([UNKNOWN_ID])).event_id == UNKNOWN_ID


def test_describe_names_known_values_and_numbers_unknown_ones() -> None:
    assert commands.describe_command(Command.SET_RANGE) == "SET_RANGE"
    assert commands.describe_command(UNKNOWN_ID) == "0xEE"
    assert commands.describe_status(Status.BUSY) == "BUSY"
    assert commands.describe_status(UNKNOWN_ID) == "status 238"


# --- Commands without arguments ---------------------------------------------


@pytest.mark.parametrize(
    ("build", "command"),
    [
        (commands.build_get_info, Command.GET_INFO),
        (commands.build_get_status, Command.GET_STATUS),
        (commands.build_start, Command.START),
        (commands.build_stop, Command.STOP),
        (commands.build_cal_zero, Command.CAL_ZERO),
        (commands.build_clear_fault, Command.CLEAR_FAULT),
    ],
)
def test_commands_without_arguments(build: Callable[[], CommandMessage], command: Command) -> None:
    assert build() == CommandMessage(command, b"")


def test_parse_no_arguments_accepts_nothing_and_rejects_anything() -> None:
    commands.parse_no_arguments(b"", "START")
    with pytest.raises(PayloadError, match="START takes no arguments"):
        commands.parse_no_arguments(b"\x00", "START")


# --- Commands with arguments ------------------------------------------------


@pytest.mark.parametrize("mode", list(Mode))
def test_set_mode_round_trips(mode: Mode) -> None:
    message = commands.build_set_mode(mode)

    assert message.command_id == Command.SET_MODE
    assert commands.parse_set_mode(message.arguments) is mode


def test_set_mode_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="Mode"):
        commands.build_set_mode(len(Mode))  # type: ignore[arg-type]
    with pytest.raises(PayloadError, match="unknown mode"):
        commands.parse_set_mode(bytes([len(Mode)]))
    with pytest.raises(PayloadError, match="SET_MODE takes 1 argument bytes"):
        commands.parse_set_mode(b"")


@given(millivolts=st.integers(min_value=0, max_value=0xFFFF))
def test_set_voltage_round_trips(millivolts: int) -> None:
    message = commands.build_set_voltage(millivolts)

    assert message.command_id == Command.SET_VOLTAGE
    assert commands.parse_set_voltage(message.arguments) == millivolts


def test_set_voltage_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="voltage in mV"):
        commands.build_set_voltage(0x10000)
    with pytest.raises(PayloadError, match="SET_VOLTAGE takes 2 argument bytes"):
        commands.parse_set_voltage(b"\x00")


@pytest.mark.parametrize("on", [True, False])
def test_dut_power_round_trips(on: bool) -> None:
    message = commands.build_dut_power(on)

    assert message.command_id == Command.DUT_POWER
    assert commands.parse_dut_power(message.arguments) is on


def test_dut_power_rejects_bad_input() -> None:
    with pytest.raises(PayloadError, match="takes 0 or 1"):
        commands.parse_dut_power(b"\x02")
    with pytest.raises(PayloadError, match="DUT_POWER takes 1 argument bytes"):
        commands.parse_dut_power(b"\x01\x01")


@pytest.mark.parametrize("range_index", [None, *range(RANGE_COUNT)])
def test_set_range_round_trips(range_index: int | None) -> None:
    message = commands.build_set_range(range_index)

    assert message.command_id == Command.SET_RANGE
    assert commands.parse_set_range(message.arguments) == range_index


def test_set_range_sends_the_automatic_marker_for_none() -> None:
    assert commands.build_set_range(None).arguments == bytes([RANGE_AUTO])


def test_set_range_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="range"):
        commands.build_set_range(RANGE_COUNT)
    with pytest.raises(ValueError, match="range"):
        commands.build_set_range(-1)
    with pytest.raises(PayloadError, match="unknown range"):
        commands.parse_set_range(bytes([RANGE_COUNT]))
    with pytest.raises(PayloadError, match="SET_RANGE takes 1 argument bytes"):
        commands.parse_set_range(b"")


@given(samples=st.integers(min_value=0, max_value=0xFFFF))
def test_set_down_n_round_trips(samples: int) -> None:
    message = commands.build_set_down_n(samples)

    assert message.command_id == Command.SET_DOWN_N
    assert commands.parse_set_down_n(message.arguments) == samples


def test_set_down_n_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="sample count"):
        commands.build_set_down_n(-1)
    with pytest.raises(PayloadError, match="SET_DOWN_N takes 2 argument bytes"):
        commands.parse_set_down_n(b"\x00\x00\x00")


@pytest.mark.parametrize("target", [*range(RANGE_COUNT), CAL_TARGET_DAC])
def test_cal_write_round_trips(target: int) -> None:
    message = commands.build_cal_write(target, gain=2.0, offset=-0.5)

    assert message.command_id == Command.CAL_WRITE
    assert commands.parse_cal_write(message.arguments) == CalibrationWrite(target, 2.0, -0.5)


def test_cal_write_sends_32_bit_floats() -> None:
    gain = 1.9073486328125e-09

    written = commands.parse_cal_write(commands.build_cal_write(0, gain, 1310.72).arguments)

    assert written.gain == pytest.approx(gain, rel=1e-6)
    assert written.offset == struct.unpack("<f", struct.pack("<f", 1310.72))[0]


def test_cal_write_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="calibration target"):
        commands.build_cal_write(RANGE_COUNT, 1.0, 0.0)
    with pytest.raises(ValueError, match="calibration values"):
        commands.build_cal_write(0, 1e300, 0.0)
    with pytest.raises(PayloadError, match="unknown target"):
        commands.parse_cal_write(struct.pack("<Bff", RANGE_COUNT, 1.0, 0.0))
    with pytest.raises(PayloadError, match="CAL_WRITE takes 9 argument bytes"):
        commands.parse_cal_write(b"")


# --- Response data ----------------------------------------------------------


def test_device_info_round_trips() -> None:
    info = DeviceInfo(
        protocol_version=PROTOCOL_VERSION, hardware_revision=1, firmware_version=(2, 3, 4)
    )

    assert commands.decode_device_info(commands.encode_device_info(info)) == info
    assert commands.encode_device_info(info) == bytes([PROTOCOL_VERSION, 1, 2, 3, 4])


def test_device_info_ignores_fields_added_by_a_newer_instrument() -> None:
    info = DeviceInfo(protocol_version=1, hardware_revision=0, firmware_version=(0, 1, 0))

    assert commands.decode_device_info(commands.encode_device_info(info) + b"\xff\xff") == info


def test_device_info_rejects_bad_input() -> None:
    with pytest.raises(PayloadError, match="GET_INFO needs 5 data bytes"):
        commands.decode_device_info(bytes(4))
    with pytest.raises(ValueError, match="device info"):
        commands.encode_device_info(DeviceInfo(256, 0, (0, 0, 0)))


@given(
    state=st.sampled_from(DeviceState),
    faults=st.integers(min_value=0, max_value=0xFFFF),
    dropped=st.integers(min_value=0, max_value=0xFFFFFFFF),
)
def test_device_status_round_trips(state: DeviceState, faults: int, dropped: int) -> None:
    status = DeviceStatus(state=state, faults=Fault(faults), dropped_blocks=dropped)

    assert commands.decode_device_status(commands.encode_device_status(status)) == status


def test_device_status_layout() -> None:
    status = DeviceStatus(
        state=DeviceState.FAULT, faults=Fault.OVERCURRENT | Fault.THERMAL, dropped_blocks=258
    )

    encoded = commands.encode_device_status(status)

    assert encoded == struct.pack("<BHI", DeviceState.FAULT, 0b101, 258)
    assert commands.decode_device_status(encoded + b"\x00") == status


def test_device_status_rejects_bad_input() -> None:
    with pytest.raises(PayloadError, match="GET_STATUS needs 7 data bytes"):
        commands.decode_device_status(bytes(6))
    with pytest.raises(PayloadError, match="unknown state"):
        commands.decode_device_status(struct.pack("<BHI", len(DeviceState), 0, 0))
    with pytest.raises(ValueError, match="device status"):
        commands.encode_device_status(DeviceStatus(DeviceState.IDLE, Fault(0), -1))


# --- Event data -------------------------------------------------------------


@given(faults=st.integers(min_value=0, max_value=0xFFFF))
def test_fault_raised_round_trips(faults: int) -> None:
    event = commands.build_fault_raised(Fault(faults))

    assert event.event_id == Event.FAULT_RAISED
    assert commands.parse_fault_raised(event.data) == Fault(faults)
    assert commands.parse_fault_raised(event.data + b"\x00") == Fault(faults)


@given(milliwatts=st.integers(min_value=0, max_value=0xFFFF))
def test_power_budget_changed_round_trips(milliwatts: int) -> None:
    event = commands.build_power_budget_changed(milliwatts)

    assert event.event_id == Event.POWER_BUDGET_CHANGED
    assert commands.parse_power_budget_changed(event.data) == milliwatts


@pytest.mark.parametrize("state", list(DeviceState))
def test_state_changed_round_trips(state: DeviceState) -> None:
    event = commands.build_state_changed(state)

    assert event.event_id == Event.STATE_CHANGED
    assert commands.parse_state_changed(event.data) is state


def test_event_data_rejects_bad_input() -> None:
    with pytest.raises(PayloadError, match="FAULT_RAISED needs 2 data bytes"):
        commands.parse_fault_raised(b"\x00")
    with pytest.raises(PayloadError, match="POWER_BUDGET_CHANGED needs 2 data bytes"):
        commands.parse_power_budget_changed(b"")
    with pytest.raises(ValueError, match="power budget"):
        commands.build_power_budget_changed(0x10000)
    with pytest.raises(PayloadError, match="STATE_CHANGED needs 1 data bytes"):
        commands.parse_state_changed(b"")
    with pytest.raises(PayloadError, match="unknown state"):
        commands.parse_state_changed(bytes([len(DeviceState)]))
