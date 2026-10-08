from __future__ import annotations

import struct
import threading
from typing import Any

import pytest

from s3_power_profiler.device import DeviceClient
from s3_power_profiler.protocol import (
    BLOCK_SAMPLES,
    CAL_TARGET_DAC,
    COMMAND_MAX_PAYLOAD,
    MAX_STREAM_SAMPLES,
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
    decode_event,
    decode_response,
    decode_stream_payload,
    encode_command,
    encode_frame,
    split_words,
)
from s3_power_profiler.protocol.commands import CalibrationWrite
from s3_power_profiler.sim.simulator import Simulator, SimulatorConfig
from s3_power_profiler.transport.memory import memory_pair

THREAD_LIMIT = 5.0
UNKNOWN_COMMAND = 0xEE


class Bench:
    """A simulator with a frame-level host side, driven step by step."""

    def __init__(self, config: SimulatorConfig | None = None, *, boot: bool = True) -> None:
        self.host, device = memory_pair()
        self.simulator = Simulator(device, config)
        self.decoder = FrameDecoder()
        self.sequence = 0
        if boot:
            self.simulator.boot()
            self.drain()

    def drain(self) -> list[Frame]:
        """Return every frame the simulator has sent since the last call."""
        frames = []
        while data := self.host.read(65536, 0):
            frames += self.decoder.feed(data)
        return frames

    def send(self, message: CommandMessage) -> list[Frame]:
        """Send a command, let the simulator run, and return what it sent."""
        self.host.write(
            encode_frame(Frame(FrameType.COMMAND, self.sequence, encode_command(message)))
        )
        self.sequence += 1
        self.simulator.poll()
        return self.drain()

    def ask(self, message: CommandMessage) -> ResponseMessage:
        """Send a command and return its single response."""
        responses = [
            frame for frame in self.send(message) if frame.frame_type is FrameType.RESPONSE
        ]
        assert len(responses) == 1
        assert responses[0].sequence == self.sequence - 1
        return decode_response(responses[0].payload)

    def stream(self, blocks: int) -> list[Frame]:
        """Let the simulator produce and return the stream frames it sent."""
        self.simulator.produce(blocks)
        return [frame for frame in self.drain() if frame.frame_type is FrameType.STREAM]

    def payloads(self, blocks: int) -> list[StreamPayload]:
        return [decode_stream_payload(frame.payload) for frame in self.stream(blocks)]

    def enter(self, state: DeviceState) -> None:
        """Bring a booted simulator to ``state``."""
        if state in (DeviceState.ARMED, DeviceState.STREAMING):
            assert self.ask(commands.build_dut_power(True)).ok
        if state is DeviceState.STREAMING:
            assert self.ask(commands.build_start()).ok
        if state is DeviceState.FAULT:
            self.simulator.inject_fault(Fault.OVERCURRENT)
            self.drain()
        assert self.simulator.state is state


def events_in(frames: list[Frame]) -> list[EventMessage]:
    return [decode_event(frame.payload) for frame in frames if frame.frame_type is FrameType.EVENT]


def state_changes(frames: list[Frame]) -> list[DeviceState]:
    return [
        commands.parse_state_changed(event.data)
        for event in events_in(frames)
        if event.event_id == Event.STATE_CHANGED
    ]


SET_SOURCE = commands.build_set_mode(Mode.SOURCE_METER)
POWER_ON = commands.build_dut_power(True)
POWER_OFF = commands.build_dut_power(False)
CAL_WRITE = commands.build_cal_write(0, 1.0, 0.0)


# --- Start-up ---------------------------------------------------------------


def test_new_simulator_waits_in_boot() -> None:
    bench = Bench(boot=False)

    assert bench.simulator.state is DeviceState.BOOT
    assert bench.drain() == []


def test_boot_runs_the_selftest_and_reaches_idle() -> None:
    bench = Bench(boot=False)

    bench.simulator.boot()

    frames = bench.drain()
    assert bench.simulator.state is DeviceState.IDLE
    assert state_changes(frames) == [DeviceState.SELFTEST, DeviceState.IDLE]
    assert [frame.sequence for frame in frames] == [0, 1]


def test_boot_does_nothing_the_second_time() -> None:
    bench = Bench()

    bench.simulator.boot()

    assert bench.drain() == []
    assert bench.simulator.state is DeviceState.IDLE


def test_failed_selftest_ends_in_fault() -> None:
    bench = Bench(SimulatorConfig(selftest_passes=False), boot=False)

    bench.simulator.boot()

    events = events_in(bench.drain())
    assert bench.simulator.state is DeviceState.FAULT
    assert bench.simulator.faults == Fault.SELFTEST
    assert [event.event_id for event in events] == [
        Event.STATE_CHANGED,
        Event.FAULT_RAISED,
        Event.STATE_CHANGED,
    ]
    assert commands.parse_fault_raised(events[1].data) == Fault.SELFTEST


@pytest.mark.parametrize(
    "message",
    [SET_SOURCE, POWER_ON, commands.build_start(), commands.build_clear_fault(), CAL_WRITE],
)
def test_commands_are_answered_busy_before_boot(message: CommandMessage) -> None:
    bench = Bench(boot=False)

    assert bench.ask(message).status_code == Status.BUSY
    assert bench.simulator.state is DeviceState.BOOT


def test_queries_are_answered_before_boot() -> None:
    bench = Bench(boot=False)

    assert bench.ask(commands.build_get_info()).ok
    status = commands.decode_device_status(bench.ask(commands.build_get_status()).data)
    assert status.state is DeviceState.BOOT


# --- Queries ----------------------------------------------------------------


def test_get_info_reports_the_configured_identity() -> None:
    bench = Bench(SimulatorConfig(hardware_revision=2, firmware_version=(1, 4, 7)))

    info = commands.decode_device_info(bench.ask(commands.build_get_info()).data)

    assert info == DeviceInfo(
        protocol_version=PROTOCOL_VERSION, hardware_revision=2, firmware_version=(1, 4, 7)
    )


def test_get_status_reports_state_faults_and_dropped_blocks() -> None:
    bench = Bench(SimulatorConfig(drop_every=1))
    bench.enter(DeviceState.STREAMING)
    bench.stream(3)

    status = commands.decode_device_status(bench.ask(commands.build_get_status()).data)

    assert status == DeviceStatus(state=DeviceState.STREAMING, faults=Fault(0), dropped_blocks=2)


# --- State machine ----------------------------------------------------------


@pytest.mark.parametrize(
    ("initial", "message", "status", "final"),
    [
        (DeviceState.IDLE, POWER_ON, Status.OK, DeviceState.ARMED),
        (DeviceState.IDLE, POWER_OFF, Status.OK, DeviceState.IDLE),
        (DeviceState.IDLE, commands.build_start(), Status.WRONG_STATE, DeviceState.IDLE),
        (DeviceState.IDLE, commands.build_stop(), Status.WRONG_STATE, DeviceState.IDLE),
        (DeviceState.IDLE, SET_SOURCE, Status.OK, DeviceState.IDLE),
        (DeviceState.IDLE, commands.build_cal_zero(), Status.OK, DeviceState.IDLE),
        (DeviceState.IDLE, CAL_WRITE, Status.OK, DeviceState.IDLE),
        (DeviceState.IDLE, commands.build_clear_fault(), Status.OK, DeviceState.IDLE),
        (DeviceState.ARMED, POWER_ON, Status.OK, DeviceState.ARMED),
        (DeviceState.ARMED, POWER_OFF, Status.OK, DeviceState.IDLE),
        (DeviceState.ARMED, commands.build_start(), Status.OK, DeviceState.STREAMING),
        (DeviceState.ARMED, commands.build_stop(), Status.WRONG_STATE, DeviceState.ARMED),
        (DeviceState.ARMED, SET_SOURCE, Status.WRONG_STATE, DeviceState.ARMED),
        (DeviceState.ARMED, commands.build_cal_zero(), Status.WRONG_STATE, DeviceState.ARMED),
        (DeviceState.ARMED, CAL_WRITE, Status.OK, DeviceState.ARMED),
        (DeviceState.STREAMING, POWER_ON, Status.OK, DeviceState.STREAMING),
        (DeviceState.STREAMING, POWER_OFF, Status.WRONG_STATE, DeviceState.STREAMING),
        (DeviceState.STREAMING, commands.build_start(), Status.WRONG_STATE, DeviceState.STREAMING),
        (DeviceState.STREAMING, commands.build_stop(), Status.OK, DeviceState.ARMED),
        (DeviceState.STREAMING, SET_SOURCE, Status.WRONG_STATE, DeviceState.STREAMING),
        (
            DeviceState.STREAMING,
            commands.build_cal_zero(),
            Status.WRONG_STATE,
            DeviceState.STREAMING,
        ),
        (DeviceState.STREAMING, CAL_WRITE, Status.WRONG_STATE, DeviceState.STREAMING),
        (DeviceState.FAULT, POWER_ON, Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, POWER_OFF, Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_start(), Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_stop(), Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, SET_SOURCE, Status.FAULT_ACTIVE, DeviceState.FAULT),
        (
            DeviceState.FAULT,
            commands.build_set_voltage(3300),
            Status.FAULT_ACTIVE,
            DeviceState.FAULT,
        ),
        (DeviceState.FAULT, commands.build_set_range(1), Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_set_down_n(10), Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_cal_zero(), Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, CAL_WRITE, Status.FAULT_ACTIVE, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_get_info(), Status.OK, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_get_status(), Status.OK, DeviceState.FAULT),
        (DeviceState.FAULT, commands.build_clear_fault(), Status.OK, DeviceState.IDLE),
    ],
)
def test_state_machine(
    initial: DeviceState, message: CommandMessage, status: Status, final: DeviceState
) -> None:
    bench = Bench()
    bench.enter(initial)

    response = bench.ask(message)

    assert response.status_code == status
    assert response.command_id == message.command_id
    assert bench.simulator.state is final


def test_state_change_is_announced_after_the_response() -> None:
    bench = Bench()

    frames = bench.send(POWER_ON)

    assert [frame.frame_type for frame in frames] == [FrameType.RESPONSE, FrameType.EVENT]
    assert state_changes(frames) == [DeviceState.ARMED]


def test_command_that_changes_no_state_sends_no_event() -> None:
    bench = Bench()

    assert events_in(bench.send(POWER_OFF)) == []
    assert events_in(bench.send(commands.build_start())) == []


def test_event_sequence_numbers_count_up() -> None:
    bench = Bench()

    frames = (
        bench.send(POWER_ON)
        + bench.send(commands.build_start())
        + bench.send(commands.build_stop())
    )

    events = [frame for frame in frames if frame.frame_type is FrameType.EVENT]
    assert [frame.sequence for frame in events] == [2, 3, 4]
    assert state_changes(frames) == [
        DeviceState.ARMED,
        DeviceState.STREAMING,
        DeviceState.ARMED,
    ]


# --- Command details --------------------------------------------------------


def test_unknown_command_is_answered_with_its_own_identifier() -> None:
    bench = Bench()

    response = bench.ask(CommandMessage(UNKNOWN_COMMAND, b"\x01\x02"))

    assert response == ResponseMessage(UNKNOWN_COMMAND, Status.UNKNOWN_COMMAND)


def test_unknown_command_is_reported_even_in_fault() -> None:
    bench = Bench()
    bench.enter(DeviceState.FAULT)

    assert bench.ask(CommandMessage(UNKNOWN_COMMAND)).status_code == Status.UNKNOWN_COMMAND


def test_command_frame_without_payload_is_a_bad_argument() -> None:
    bench = Bench()
    bench.host.write(encode_frame(Frame(FrameType.COMMAND, 0x1234, b"")))
    bench.simulator.poll()

    (frame,) = bench.drain()

    assert frame.frame_type is FrameType.RESPONSE
    assert frame.sequence == 0x1234
    assert decode_response(frame.payload) == ResponseMessage(0, Status.BAD_ARGUMENT)


@pytest.mark.parametrize(
    "message",
    [
        CommandMessage(Command.GET_INFO, b"\x00"),
        CommandMessage(Command.GET_STATUS, b"\x00"),
        CommandMessage(Command.SET_MODE),
        CommandMessage(Command.SET_MODE, bytes([len(Mode)])),
        CommandMessage(Command.SET_VOLTAGE, b"\x00"),
        CommandMessage(Command.DUT_POWER, b"\x02"),
        CommandMessage(Command.SET_RANGE, b"\x07"),
        CommandMessage(Command.SET_DOWN_N, b"\x01"),
        CommandMessage(Command.SET_DOWN_N, struct.pack("<H", 0)),
        CommandMessage(Command.START, b"\x00"),
        CommandMessage(Command.STOP, b"\x00"),
        CommandMessage(Command.CAL_ZERO, b"\x00"),
        CommandMessage(Command.CAL_WRITE, b"\x00"),
        CommandMessage(Command.CAL_WRITE, struct.pack("<Bff", 9, 1.0, 0.0)),
        CommandMessage(Command.CLEAR_FAULT, b"\x00"),
    ],
)
def test_malformed_arguments_are_a_bad_argument(message: CommandMessage) -> None:
    bench = Bench()

    assert bench.ask(message).status_code == Status.BAD_ARGUMENT
    assert bench.simulator.state is DeviceState.IDLE


def test_set_mode_selects_the_mode() -> None:
    bench = Bench()
    before = bench.simulator.mode

    assert bench.ask(SET_SOURCE).ok

    assert (before, bench.simulator.mode) == (Mode.AMPERE_METER, Mode.SOURCE_METER)


def test_set_voltage_needs_source_meter_mode() -> None:
    bench = Bench()

    assert bench.ask(commands.build_set_voltage(3300)).status_code == Status.WRONG_STATE


@pytest.mark.parametrize(
    ("millivolts", "status"),
    [
        (800, Status.OK),
        (3300, Status.OK),
        (5000, Status.OK),
        (799, Status.BAD_ARGUMENT),
        (5001, Status.BAD_ARGUMENT),
    ],
)
def test_set_voltage_accepts_the_range_of_the_source_meter(millivolts: int, status: Status) -> None:
    bench = Bench()
    bench.ask(SET_SOURCE)
    before = bench.simulator.voltage_mv

    assert bench.ask(commands.build_set_voltage(millivolts)).status_code == status
    assert bench.simulator.voltage_mv == (millivolts if status is Status.OK else before)


def test_set_range_locks_and_releases_the_range() -> None:
    bench = Bench()
    locks = [bench.simulator.range_lock]

    assert bench.ask(commands.build_set_range(2)).ok
    locks.append(bench.simulator.range_lock)
    assert bench.ask(commands.build_set_range(None)).ok
    locks.append(bench.simulator.range_lock)

    assert locks == [None, 2, None]


def test_set_down_n_changes_the_step_down_rule() -> None:
    bench = Bench(SimulatorConfig(down_n=100))
    assert bench.simulator.down_n == 100

    assert bench.ask(commands.build_set_down_n(25)).ok

    assert bench.simulator.down_n == 25


def test_cal_write_stores_the_values_of_each_target() -> None:
    bench = Bench()

    assert bench.ask(commands.build_cal_write(1, 2.0, 0.5)).ok
    assert bench.ask(commands.build_cal_write(CAL_TARGET_DAC, 4.0, -1.0)).ok

    assert dict(bench.simulator.calibration) == {
        1: CalibrationWrite(1, 2.0, 0.5),
        CAL_TARGET_DAC: CalibrationWrite(CAL_TARGET_DAC, 4.0, -1.0),
    }


def test_calibration_view_is_read_only() -> None:
    calibration: Any = Bench().simulator.calibration

    with pytest.raises(TypeError, match="does not support item assignment"):
        calibration[0] = CalibrationWrite(0, 1.0, 0.0)


def test_frames_that_are_not_commands_are_ignored() -> None:
    bench = Bench()
    bench.host.write(encode_frame(Frame(FrameType.RESPONSE, 0, b"\x01\x00")))
    bench.host.write(encode_frame(Frame(FrameType.EVENT, 0, b"\x01")))

    assert bench.simulator.poll() == 2
    assert bench.drain() == []
    assert bench.simulator.ignored_frames == 2


def test_command_longer_than_the_limit_is_not_a_frame_for_the_instrument() -> None:
    bench = Bench()
    bench.host.write(encode_frame(Frame(FrameType.COMMAND, 0, bytes(COMMAND_MAX_PAYLOAD + 1))))

    assert bench.simulator.poll() == 0
    assert bench.drain() == []


def test_poll_without_input_handles_nothing() -> None:
    bench = Bench()

    assert bench.simulator.poll() == 0
    assert bench.drain() == []


def test_poll_handles_several_commands_at_once() -> None:
    bench = Bench()
    for sequence, message in enumerate(
        (commands.build_get_info(), POWER_ON, commands.build_start())
    ):
        bench.host.write(encode_frame(Frame(FrameType.COMMAND, sequence, encode_command(message))))

    assert bench.simulator.poll() == 3

    responses = [f for f in bench.drain() if f.frame_type is FrameType.RESPONSE]
    assert [frame.sequence for frame in responses] == [0, 1, 2]
    assert bench.simulator.state is DeviceState.STREAMING


# --- Stream -----------------------------------------------------------------


def test_nothing_is_produced_outside_streaming() -> None:
    bench = Bench()
    bench.enter(DeviceState.ARMED)

    assert bench.simulator.produce(3) == 0
    assert bench.drain() == []


def test_stream_frames_are_consecutive_blocks() -> None:
    bench = Bench()
    bench.enter(DeviceState.STREAMING)

    assert bench.simulator.produce(3) == 3

    frames = [frame for frame in bench.drain() if frame.frame_type is FrameType.STREAM]
    payloads = [decode_stream_payload(frame.payload) for frame in frames]
    assert [frame.sequence for frame in frames] == [0, 1, 2]
    assert [payload.first_index for payload in payloads] == [0, BLOCK_SAMPLES, 2 * BLOCK_SAMPLES]
    assert all(payload.count == BLOCK_SAMPLES and payload.dropped == 0 for payload in payloads)


def test_same_commands_produce_the_same_bytes() -> None:
    runs = []
    for _ in range(2):
        bench = Bench()
        bench.enter(DeviceState.STREAMING)
        runs.append([encode_frame(frame) for frame in bench.stream(4)])

    assert runs[0] == runs[1]


def test_block_size_follows_the_configuration() -> None:
    bench = Bench(SimulatorConfig(block_samples=MAX_STREAM_SAMPLES))
    bench.enter(DeviceState.STREAMING)

    payloads = bench.payloads(2)

    assert [payload.count for payload in payloads] == [MAX_STREAM_SAMPLES] * 2
    assert payloads[1].first_index == MAX_STREAM_SAMPLES


def test_waveform_is_a_triangle_between_the_configured_codes() -> None:
    bench = Bench(SimulatorConfig(block_samples=16, waveform_period=8, adc_low=100, adc_high=900))
    bench.enter(DeviceState.STREAMING)

    (payload,) = bench.payloads(1)

    assert split_words(payload.words).adc == (100, 300, 500, 700, 900, 700, 500, 300) * 2


def test_waveform_with_an_odd_period_stays_within_the_codes() -> None:
    bench = Bench(SimulatorConfig(block_samples=10, waveform_period=5, adc_low=0, adc_high=65535))
    bench.enter(DeviceState.STREAMING)

    (payload,) = bench.payloads(1)

    assert split_words(payload.words).adc == (0, 32767, 65535, 65535, 32767) * 2


def test_automatic_ranging_walks_the_ranges_and_flags_the_settling_samples() -> None:
    bench = Bench(SimulatorConfig(block_samples=20, range_dwell=4, settle_samples=1))
    bench.enter(DeviceState.STREAMING)

    (payload,) = bench.payloads(1)

    columns = split_words(payload.words)
    assert columns.range_index == (0,) * 4 + (1,) * 4 + (2,) * 4 + (3,) * 4 + (0,) * 4
    assert columns.invalid == (False,) * 4 + (True, False, False, False) * 4
    assert not any(columns.fault)


def test_locked_range_is_used_for_every_sample() -> None:
    bench = Bench(SimulatorConfig(block_samples=20, range_dwell=4, settle_samples=1))
    bench.ask(commands.build_set_range(3))
    bench.enter(DeviceState.STREAMING)

    (payload,) = bench.payloads(1)

    columns = split_words(payload.words)
    assert columns.range_index == (3,) * 20
    assert not any(columns.invalid)


def test_logic_inputs_count_slowly() -> None:
    bench = Bench(SimulatorConfig(block_samples=48))
    bench.enter(DeviceState.STREAMING)

    (payload,) = bench.payloads(1)

    assert split_words(payload.words).logic == (0,) * 16 + (1,) * 16 + (2,) * 16


def test_dropped_blocks_leave_a_gap_and_are_reported() -> None:
    bench = Bench(SimulatorConfig(block_samples=8, drop_every=2))
    bench.enter(DeviceState.STREAMING)

    payloads = bench.payloads(5)

    assert [payload.first_index for payload in payloads] == [0, 8, 24, 32, 48]
    assert [payload.dropped for payload in payloads] == [0, 0, 1, 0, 1]
    assert bench.simulator.dropped_blocks == 2


def test_start_restarts_the_sample_index_and_keeps_the_frame_sequence() -> None:
    bench = Bench(SimulatorConfig(block_samples=8, drop_every=2))
    bench.enter(DeviceState.STREAMING)
    bench.stream(2)
    bench.ask(commands.build_stop())
    bench.ask(commands.build_start())

    frames = bench.stream(2)

    payloads = [decode_stream_payload(frame.payload) for frame in frames]
    assert [frame.sequence for frame in frames] == [2, 3]
    assert [payload.first_index for payload in payloads] == [0, 8]
    assert [payload.dropped for payload in payloads] == [0, 0]


def test_step_answers_commands_then_produces_one_block() -> None:
    bench = Bench()
    bench.enter(DeviceState.ARMED)
    bench.host.write(
        encode_frame(Frame(FrameType.COMMAND, 9, encode_command(commands.build_start())))
    )

    bench.simulator.step()

    kinds = [frame.frame_type for frame in bench.drain()]
    assert kinds == [FrameType.RESPONSE, FrameType.EVENT, FrameType.STREAM]


# --- Faults -----------------------------------------------------------------


def test_fault_ends_the_stream_and_is_announced_before_the_state() -> None:
    bench = Bench()
    bench.enter(DeviceState.STREAMING)

    bench.simulator.inject_fault(Fault.OVERCURRENT)

    events = events_in(bench.drain())
    assert bench.simulator.state is DeviceState.FAULT
    assert [event.event_id for event in events] == [Event.FAULT_RAISED, Event.STATE_CHANGED]
    assert commands.parse_fault_raised(events[0].data) == Fault.OVERCURRENT
    assert commands.parse_state_changed(events[1].data) is DeviceState.FAULT
    assert bench.simulator.produce(1) == 0


def test_second_fault_adds_to_the_flags_without_a_state_change() -> None:
    bench = Bench()
    bench.enter(DeviceState.FAULT)

    bench.simulator.inject_fault(Fault.THERMAL)

    events = events_in(bench.drain())
    assert [event.event_id for event in events] == [Event.FAULT_RAISED]
    assert commands.parse_fault_raised(events[0].data) == Fault.OVERCURRENT | Fault.THERMAL
    assert bench.simulator.faults == Fault.OVERCURRENT | Fault.THERMAL


def test_clear_fault_returns_to_idle_without_faults() -> None:
    bench = Bench()
    bench.enter(DeviceState.FAULT)

    frames = bench.send(commands.build_clear_fault())

    assert bench.simulator.state is DeviceState.IDLE
    assert bench.simulator.faults == Fault(0)
    assert state_changes(frames) == [DeviceState.IDLE]


def test_fault_can_be_injected_before_boot() -> None:
    bench = Bench(boot=False)

    bench.simulator.inject_fault(Fault.POWER_LIMIT)

    assert bench.simulator.state is DeviceState.FAULT
    assert bench.ask(POWER_ON).status_code == Status.FAULT_ACTIVE


# --- Host connection --------------------------------------------------------


def test_stream_ends_when_the_host_disconnects() -> None:
    bench = Bench()
    bench.enter(DeviceState.STREAMING)

    bench.simulator.host_disconnected()

    assert bench.simulator.state is DeviceState.ARMED
    assert bench.drain() == []


@pytest.mark.parametrize("state", [DeviceState.IDLE, DeviceState.ARMED, DeviceState.FAULT])
def test_host_disconnect_changes_nothing_outside_streaming(state: DeviceState) -> None:
    bench = Bench()
    bench.enter(state)

    bench.simulator.host_disconnected()

    assert bench.simulator.state is state


def test_serve_answers_a_client_from_another_thread() -> None:
    host, device = memory_pair()
    simulator = Simulator(device)
    simulator.boot()
    stop = threading.Event()
    thread = threading.Thread(target=simulator.serve, args=(stop,), kwargs={"poll_interval": 0.001})
    thread.start()
    try:
        with DeviceClient(host, response_timeout=THREAD_LIMIT) as client:
            info = client.get_info()
            client.set_dut_power(True)
            client.start()
            payload = client.read_stream()
            client.stop()
    finally:
        stop.set()
        thread.join(THREAD_LIMIT)

    assert not thread.is_alive()
    assert info.protocol_version == PROTOCOL_VERSION
    assert payload is not None
    assert payload.first_index == 0


def test_serve_returns_when_asked_to_stop() -> None:
    _host, device = memory_pair()
    simulator = Simulator(device)
    stop = threading.Event()
    thread = threading.Thread(target=simulator.serve, args=(stop,), kwargs={"poll_interval": 0.001})
    thread.start()

    stop.set()
    thread.join(THREAD_LIMIT)

    assert not thread.is_alive()


def test_serve_returns_and_ends_the_stream_when_the_host_closes() -> None:
    host, device = memory_pair()
    simulator = Simulator(device)
    simulator.boot()
    bench_client = DeviceClient(host)
    stop = threading.Event()
    thread = threading.Thread(target=simulator.serve, args=(stop,), kwargs={"poll_interval": 0.001})
    thread.start()
    bench_client.set_dut_power(True)
    bench_client.start()

    bench_client.close()
    thread.join(THREAD_LIMIT)

    assert not thread.is_alive()
    assert not stop.is_set()
    assert simulator.state is DeviceState.ARMED


# --- Configuration ----------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("block_samples", 0, "block_samples"),
        ("block_samples", MAX_STREAM_SAMPLES + 1, "block_samples"),
        ("adc_low", -1, "adc_low"),
        ("adc_high", 65536, "adc_low"),
        ("adc_low", 60000, "adc_low"),
        ("waveform_period", 1, "waveform_period"),
        ("range_dwell", 0, "range_dwell"),
        ("settle_samples", -1, "settle_samples"),
        ("drop_every", -1, "drop_every"),
        ("min_voltage_mv", -1, "min_voltage_mv"),
        ("min_voltage_mv", 6000, "min_voltage_mv"),
        ("down_n", 0, "down_n"),
    ],
)
def test_configuration_rejects_values_the_protocol_cannot_carry(
    field: str, value: int, message: str
) -> None:
    fields: dict[str, Any] = {field: value}

    with pytest.raises(ValueError, match=message):
        SimulatorConfig(**fields)


def test_default_configuration_uses_the_block_size_of_the_protocol() -> None:
    assert SimulatorConfig().block_samples == BLOCK_SAMPLES
