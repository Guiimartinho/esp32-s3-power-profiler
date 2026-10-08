from __future__ import annotations

from collections import deque
from collections.abc import Iterable

import pytest

from s3_power_profiler.device.client import DeviceClient, LinkStatistics
from s3_power_profiler.errors import (
    CommandError,
    PayloadError,
    ProtocolError,
    ResponseTimeoutError,
    TransportClosedError,
)
from s3_power_profiler.protocol import (
    BLOCK_SAMPLES,
    CAL_TARGET_DAC,
    PROTOCOL_VERSION,
    Command,
    CommandMessage,
    DeviceInfo,
    DeviceState,
    DeviceStatus,
    Event,
    EventMessage,
    Fault,
    Frame,
    FrameDecoder,
    FrameType,
    Mode,
    ResponseMessage,
    Status,
    StreamPayload,
    commands,
    decode_command,
    encode_event,
    encode_frame,
    encode_response,
    encode_stream_payload,
)
from s3_power_profiler.protocol.commands import CalibrationWrite
from s3_power_profiler.sim import SimulatorConfig, connect_simulator


class ScriptedTransport:
    """Transport that returns prepared chunks and records what is written."""

    def __init__(self, chunks: Iterable[bytes] = ()) -> None:
        self.chunks = deque(chunks)
        self.written: list[bytes] = []
        self.reads: list[tuple[int, float | None]] = []
        self.closed = False

    def read(self, max_bytes: int, timeout: float | None) -> bytes:
        self.reads.append((max_bytes, timeout))
        return self.chunks.popleft() if self.chunks else b""

    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))

    def close(self) -> None:
        self.closed = True

    def sent_frames(self) -> list[Frame]:
        return FrameDecoder().feed(b"".join(self.written))


class FakeClock:
    """Clock that advances by a fixed step every time it is read."""

    def __init__(self, step: float = 0.25) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def response(sequence: int, command: int, status: int = Status.OK, data: bytes = b"") -> bytes:
    payload = encode_response(ResponseMessage(command, status, data))
    return encode_frame(Frame(FrameType.RESPONSE, sequence, payload))


def stream(sequence: int, first_index: int) -> bytes:
    payload = encode_stream_payload(StreamPayload(first_index, 0, (first_index,)))
    return encode_frame(Frame(FrameType.STREAM, sequence, payload))


def event(sequence: int, message: EventMessage) -> bytes:
    return encode_frame(Frame(FrameType.EVENT, sequence, encode_event(message)))


# --- Against the simulator ---------------------------------------------------


def test_get_info_returns_the_identity_of_the_instrument() -> None:
    transport, _simulator = connect_simulator(SimulatorConfig(firmware_version=(1, 2, 3)))

    with DeviceClient(transport) as client:
        info = client.get_info()

    assert info == DeviceInfo(
        protocol_version=PROTOCOL_VERSION, hardware_revision=0, firmware_version=(1, 2, 3)
    )


def test_get_status_returns_the_state_of_the_instrument() -> None:
    transport, _simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_dut_power(True)
        status = client.get_status()

    assert status == DeviceStatus(state=DeviceState.ARMED, faults=Fault(0), dropped_blocks=0)


def test_settings_reach_the_instrument() -> None:
    transport, simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_mode(Mode.SOURCE_METER)
        client.set_voltage(3300)
        client.set_range(2)
        client.set_down_n(40)
        client.calibrate_zero()
        client.write_calibration(CAL_TARGET_DAC, 2.0, 0.5)

    assert simulator.mode is Mode.SOURCE_METER
    assert simulator.voltage_mv == 3300
    assert simulator.range_lock == 2
    assert simulator.down_n == 40
    assert simulator.calibration[CAL_TARGET_DAC] == CalibrationWrite(CAL_TARGET_DAC, 2.0, 0.5)


def test_capture_delivers_consecutive_blocks() -> None:
    transport, simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_dut_power(True)
        client.start()
        payloads = [client.read_stream() for _ in range(4)]
        client.stop()
        client.set_dut_power(False)
        statistics = client.statistics

    assert [payload.first_index for payload in payloads if payload is not None] == [
        index * BLOCK_SAMPLES for index in range(4)
    ]
    assert simulator.state is DeviceState.IDLE
    assert statistics.crc_errors == 0
    assert statistics.discarded_bytes == 0
    assert statistics.malformed_payloads == 0


def test_refused_command_raises_with_the_status_of_the_instrument() -> None:
    transport, _simulator = connect_simulator()

    with DeviceClient(transport) as client, pytest.raises(CommandError) as raised:
        client.start()

    assert raised.value.command_id == Command.START
    assert raised.value.status_code == Status.WRONG_STATE
    assert str(raised.value) == "START failed: WRONG_STATE"


def test_state_changes_arrive_as_events() -> None:
    transport, _simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_dut_power(True)
        client.poll()
        events = client.take_events()

    states = [commands.parse_state_changed(message.data) for message in events]
    assert all(message.event_id == Event.STATE_CHANGED for message in events)
    assert states == [DeviceState.SELFTEST, DeviceState.IDLE, DeviceState.ARMED]


def test_take_events_forgets_what_it_returned() -> None:
    transport, _simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.poll()
        first = client.take_events()
        second = client.take_events()

    assert len(first) == 2
    assert second == []


def test_fault_is_reported_and_can_be_cleared() -> None:
    transport, simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_dut_power(True)
        client.start()
        client.take_events()
        simulator.inject_fault(Fault.OVERCURRENT)
        with pytest.raises(CommandError) as raised:
            client.stop()
        events = client.take_events()
        status = client.get_status()
        client.clear_fault()
        cleared = client.get_status()

    assert raised.value.status_code == Status.FAULT_ACTIVE
    assert [message.event_id for message in events][-2:] == [
        Event.FAULT_RAISED,
        Event.STATE_CHANGED,
    ]
    assert status.state is DeviceState.FAULT
    assert status.faults == Fault.OVERCURRENT
    assert cleared == DeviceStatus(state=DeviceState.IDLE, faults=Fault(0), dropped_blocks=0)


def test_start_discards_stream_frames_of_an_earlier_run() -> None:
    transport, _simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_dut_power(True)
        client.start()
        earlier = client.read_stream()
        client.poll()
        client.poll()
        client.stop()
        client.start()
        payload = client.read_stream()

    # Without the discard, the next payload would be a leftover that starts later.
    assert earlier is not None
    assert earlier.first_index == 0
    assert payload is not None
    assert payload.first_index == 0


# --- Frames on the wire ------------------------------------------------------


def test_command_is_sent_as_a_command_frame_with_a_new_sequence_each_time() -> None:
    transport = ScriptedTransport([response(0, Command.STOP), response(1, Command.SET_VOLTAGE)])
    client = DeviceClient(transport)

    client.stop()
    client.set_voltage(3300)

    frames = transport.sent_frames()
    assert [frame.frame_type for frame in frames] == [FrameType.COMMAND, FrameType.COMMAND]
    assert [frame.sequence for frame in frames] == [0, 1]
    assert [decode_command(frame.payload) for frame in frames] == [
        commands.build_stop(),
        commands.build_set_voltage(3300),
    ]


def test_sequence_wraps_around(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("s3_power_profiler.device.client.SEQUENCE_MODULO", 2)
    transport = ScriptedTransport(
        [response(0, Command.STOP), response(1, Command.STOP), response(0, Command.STOP)]
    )
    client = DeviceClient(transport)

    for _ in range(3):
        client.stop()

    assert [frame.sequence for frame in transport.sent_frames()] == [0, 1, 0]


def test_response_split_over_several_reads_is_put_together() -> None:
    frame = response(0, Command.GET_INFO, data=bytes([PROTOCOL_VERSION, 0, 0, 1, 0]))
    transport = ScriptedTransport([frame[:3], frame[3:9], frame[9:]])

    info = DeviceClient(transport).get_info()

    assert info.firmware_version == (0, 1, 0)


def test_request_returns_the_response_message() -> None:
    transport = ScriptedTransport(
        [response(0, Command.GET_STATUS, data=b"\x02\x00\x00\x00\x00\x00\x00")]
    )

    answer = DeviceClient(transport).request(commands.build_get_status())

    assert answer == ResponseMessage(Command.GET_STATUS, Status.OK, b"\x02\x00\x00\x00\x00\x00\x00")


# --- Timeouts ----------------------------------------------------------------


def test_silent_instrument_raises_a_timeout() -> None:
    client = DeviceClient(ScriptedTransport(), response_timeout=1.0, clock=FakeClock(0.25))

    with pytest.raises(ResponseTimeoutError) as raised:
        client.get_info()

    assert isinstance(raised.value, TimeoutError)
    assert raised.value.command_id == Command.GET_INFO
    assert raised.value.timeout == 1.0
    assert str(raised.value) == "no response to GET_INFO within 1 s"


def test_request_timeout_overrides_the_default() -> None:
    transport = ScriptedTransport()
    client = DeviceClient(transport, response_timeout=100.0, clock=FakeClock(1.0))

    with pytest.raises(ResponseTimeoutError) as raised:
        client.request(commands.build_stop(), timeout=2.5)

    assert raised.value.timeout == 2.5
    assert [timeout for _size, timeout in transport.reads] == [1.5, 0.5]


def test_reads_ask_for_the_configured_size() -> None:
    transport = ScriptedTransport([response(0, Command.STOP)])

    DeviceClient(transport, read_size=128).stop()

    assert transport.reads[0][0] == 128


def test_read_stream_returns_none_when_nothing_arrives() -> None:
    client = DeviceClient(ScriptedTransport(), clock=FakeClock(0.5))

    assert client.read_stream(timeout=1.0) is None
    assert client.read_stream() is None


# --- Unexpected input --------------------------------------------------------


def test_response_to_another_sequence_is_dropped() -> None:
    transport = ScriptedTransport([response(7, Command.STOP) + response(0, Command.STOP)])
    client = DeviceClient(transport)

    client.stop()

    assert client.statistics.stale_responses == 1


def test_response_that_names_another_command_is_a_protocol_error() -> None:
    client = DeviceClient(ScriptedTransport([response(0, Command.START)]))

    with pytest.raises(ProtocolError, match="response to STOP names START"):
        client.stop()


def test_unknown_status_code_is_still_a_command_error() -> None:
    client = DeviceClient(ScriptedTransport([response(0, Command.STOP, status=0x7F)]))

    with pytest.raises(CommandError, match="STOP failed: status 127") as raised:
        client.stop()

    assert raised.value.status_code == 0x7F


def test_response_data_that_is_too_short_is_a_payload_error() -> None:
    client = DeviceClient(ScriptedTransport([response(0, Command.GET_INFO, data=b"\x01")]))

    with pytest.raises(PayloadError, match="GET_INFO needs 5 data bytes"):
        client.get_info()


def test_frames_with_unreadable_payloads_are_counted_and_skipped() -> None:
    broken = [
        encode_frame(Frame(FrameType.RESPONSE, 0, b"\x21")),
        encode_frame(Frame(FrameType.STREAM, 0, b"\x00\x01\x02")),
        encode_frame(Frame(FrameType.EVENT, 0, b"")),
    ]
    transport = ScriptedTransport([b"".join(broken) + response(0, Command.STOP)])
    client = DeviceClient(transport)

    client.stop()

    assert client.statistics.malformed_payloads == 3
    assert client.take_events() == []
    assert client.read_stream(timeout=0) is None


def test_command_frame_from_the_instrument_is_counted_as_unexpected() -> None:
    stray = encode_frame(Frame(FrameType.COMMAND, 0, b"\x01"))
    client = DeviceClient(ScriptedTransport([stray + response(0, Command.STOP)]))

    client.stop()

    assert client.statistics.unexpected_frames == 1


def test_noise_between_frames_is_counted() -> None:
    client = DeviceClient(ScriptedTransport([b"\x00\x01\x02" + response(0, Command.STOP)]))

    client.stop()

    assert client.statistics == LinkStatistics(
        frames=1,
        discarded_bytes=3,
        crc_errors=0,
        malformed_payloads=0,
        unexpected_frames=0,
        stale_responses=0,
        stream_overflows=0,
    )


def test_stream_and_events_received_while_waiting_are_kept() -> None:
    state_event = commands.build_state_changed(DeviceState.STREAMING)
    transport = ScriptedTransport(
        [stream(0, 100) + event(0, state_event) + stream(1, 101) + response(0, Command.STOP)]
    )
    client = DeviceClient(transport)

    client.stop()

    assert client.take_events() == [state_event]
    first, second = client.read_stream(), client.read_stream()
    assert first is not None
    assert second is not None
    assert (first.first_index, second.first_index) == (100, 101)


def test_oldest_stream_frame_is_lost_when_the_queue_is_full() -> None:
    chunk = b"".join(stream(sequence, sequence) for sequence in range(3))
    transport = ScriptedTransport([chunk + response(0, Command.STOP)])
    client = DeviceClient(transport, stream_queue=2)

    client.stop()

    first, second = client.read_stream(), client.read_stream()
    assert first is not None
    assert second is not None
    assert (first.first_index, second.first_index) == (1, 2)
    assert client.statistics.stream_overflows == 1


def test_poll_collects_frames_without_a_pending_command() -> None:
    state_event = commands.build_state_changed(DeviceState.FAULT)
    client = DeviceClient(ScriptedTransport([event(0, state_event)]))

    client.poll()

    assert client.take_events() == [state_event]


# --- Lifetime ----------------------------------------------------------------


def test_leaving_the_context_closes_the_transport() -> None:
    transport = ScriptedTransport()

    with DeviceClient(transport) as client:
        assert not transport.closed
        assert isinstance(client, DeviceClient)

    assert transport.closed


def test_closed_transport_error_reaches_the_caller() -> None:
    transport, _simulator = connect_simulator()
    client = DeviceClient(transport)
    client.close()

    with pytest.raises(TransportClosedError, match="closed"):
        client.get_info()


@pytest.mark.parametrize(
    "arguments",
    [{"response_timeout": 0}, {"response_timeout": -1.0}, {"read_size": 0}, {"stream_queue": 0}],
)
def test_client_rejects_settings_that_are_not_positive(arguments: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        DeviceClient(ScriptedTransport(), **arguments)  # type: ignore[arg-type]


def test_arbitrary_command_can_be_sent_with_request() -> None:
    transport, _simulator = connect_simulator()

    with DeviceClient(transport) as client, pytest.raises(CommandError) as raised:
        client.request(CommandMessage(0xEE))

    assert raised.value.status_code == Status.UNKNOWN_COMMAND
    assert str(raised.value) == "0xEE failed: UNKNOWN_COMMAND"
