"""A deterministic fake instrument.

The simulator implements the device side of the protocol over a ``Transport``.
It answers the commands, follows the device state machine of section 6.4 of
the specification and produces stream frames with a synthetic waveform. The
same inputs always produce the same bytes, so tests can compare exact values.

It models the behavior of the protocol only. Nothing it reports is a
measurement, and it says nothing about the performance of the real instrument.

State rules, applied in this order:

* GET_INFO and GET_STATUS are answered in every state.
* During BOOT and SELFTEST every other command is answered with BUSY.
* In FAULT every other command except CLEAR_FAULT is answered with
  FAULT_ACTIVE. CLEAR_FAULT returns to IDLE.
* SET_MODE and CAL_ZERO are accepted only in IDLE.
* DUT_POWER on moves IDLE to ARMED; DUT_POWER off moves ARMED to IDLE and is
  refused while STREAMING. Asking for the present state changes nothing.
* START is accepted only in ARMED and STOP only in STREAMING.
* SET_VOLTAGE needs source meter mode; CAL_WRITE is refused while STREAMING.
* A command that asks for anything else is answered with WRONG_STATE.

Every state change is announced with a STATE_CHANGED event, sent after the
response when a command caused it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from s3_power_profiler.errors import PayloadError, TransportClosedError
from s3_power_profiler.protocol import (
    BLOCK_SAMPLES,
    COMMAND_MAX_PAYLOAD,
    INDEX_MODULO,
    MAX_STREAM_SAMPLES,
    PROTOCOL_VERSION,
    RANGE_COUNT,
    SAMPLE_ADC_MASK,
    SAMPLE_LOGIC_MASK,
    SEQUENCE_MODULO,
    Command,
    DeviceInfo,
    DeviceState,
    DeviceStatus,
    EventMessage,
    Fault,
    Frame,
    FrameDecoder,
    FrameType,
    Mode,
    ResponseMessage,
    Sample,
    Status,
    StreamPayload,
    commands,
    decode_command,
    encode_event,
    encode_frame,
    encode_response,
    encode_stream_payload,
    pack_sample,
)
from s3_power_profiler.protocol.commands import CalibrationWrite
from s3_power_profiler.transport.base import Transport

_Reply = tuple[Status, bytes]

_OK: _Reply = (Status.OK, b"")
_BAD_ARGUMENT: _Reply = (Status.BAD_ARGUMENT, b"")
_WRONG_STATE: _Reply = (Status.WRONG_STATE, b"")

_QUERIES = frozenset({int(Command.GET_INFO), int(Command.GET_STATUS)})
_STARTING_STATES = frozenset({DeviceState.BOOT, DeviceState.SELFTEST})
_UNKNOWN_COMMAND_ID = 0
_READ_SIZE = 4096
_LOGIC_SHIFT = 4


@dataclass(frozen=True, slots=True)
class SimulatorConfig:
    """Behavior of the simulated instrument.

    The voltage limits and the default of the step-down rule repeat design
    targets of the specification. The waveform values are arbitrary.

    Attributes:
        hardware_revision: Revision reported by GET_INFO.
        firmware_version: Version reported by GET_INFO.
        selftest_passes: Whether the start-up self-test succeeds.
        block_samples: Samples in each stream frame.
        adc_low: Lowest ADC code of the waveform.
        adc_high: Highest ADC code of the waveform.
        waveform_period: Samples in one period of the triangle waveform.
        range_dwell: Samples spent in a range before moving to the next one,
            while ranging is automatic.
        settle_samples: Samples flagged invalid after each range change.
        drop_every: Stream frames sent between two dropped blocks. Zero never
            drops a block.
        min_voltage_mv: Lowest voltage SET_VOLTAGE accepts, in millivolts.
        max_voltage_mv: Highest voltage SET_VOLTAGE accepts, in millivolts.
        down_n: Initial sample count of the step-down rule.

    Raises:
        ValueError: If a value is outside what the protocol can carry.
    """

    hardware_revision: int = 0
    firmware_version: tuple[int, int, int] = (0, 1, 0)
    selftest_passes: bool = True
    block_samples: int = BLOCK_SAMPLES
    adc_low: int = 1311
    adc_high: int = 53740
    waveform_period: int = 2000
    range_dwell: int = 1000
    settle_samples: int = 4
    drop_every: int = 0
    min_voltage_mv: int = 800
    max_voltage_mv: int = 5000
    down_n: int = 100

    def __post_init__(self) -> None:
        if not 1 <= self.block_samples <= MAX_STREAM_SAMPLES:
            raise ValueError(f"block_samples must be between 1 and {MAX_STREAM_SAMPLES}")
        if not 0 <= self.adc_low <= self.adc_high <= SAMPLE_ADC_MASK:
            raise ValueError(f"adc_low and adc_high must be ordered within 0 to {SAMPLE_ADC_MASK}")
        if self.waveform_period < 2:
            raise ValueError("waveform_period must be at least 2")
        if self.range_dwell < 1:
            raise ValueError("range_dwell must be at least 1")
        if self.settle_samples < 0 or self.drop_every < 0:
            raise ValueError("settle_samples and drop_every must not be negative")
        if not 0 <= self.min_voltage_mv <= self.max_voltage_mv:
            raise ValueError("min_voltage_mv and max_voltage_mv must be ordered and not negative")
        if self.down_n < 1:
            raise ValueError("down_n must be at least 1")


class Simulator:
    """Fake instrument that speaks the device side of the protocol.

    The simulator does nothing by itself. Call :meth:`poll` to let it answer
    the commands that arrived and :meth:`produce` to make it send stream
    frames, or run :meth:`serve` in a thread.

    Args:
        transport: The byte stream to the host.
        config: Behavior of the instrument, or None for the defaults.
    """

    def __init__(self, transport: Transport, config: SimulatorConfig | None = None) -> None:
        self._transport = transport
        self._config = config if config is not None else SimulatorConfig()
        self._decoder = FrameDecoder(max_payload=COMMAND_MAX_PAYLOAD)
        self._state = DeviceState.BOOT
        self._mode = Mode.AMPERE_METER
        self._voltage_mv = self._config.min_voltage_mv
        self._faults = Fault(0)
        self._range_lock: int | None = None
        self._down_n = self._config.down_n
        self._calibration: dict[int, CalibrationWrite] = {}
        self._sample_number = 0
        self._frames_since_drop = 0
        self._pending_dropped = 0
        self._dropped_blocks = 0
        self._ignored_frames = 0
        self._pending_events: list[EventMessage] = []
        self._sequences = {FrameType.STREAM: 0, FrameType.EVENT: 0}
        self._handlers: dict[int, Callable[[bytes], _Reply]] = {
            Command.GET_INFO: self._on_get_info,
            Command.GET_STATUS: self._on_get_status,
            Command.SET_MODE: self._on_set_mode,
            Command.SET_VOLTAGE: self._on_set_voltage,
            Command.DUT_POWER: self._on_dut_power,
            Command.SET_RANGE: self._on_set_range,
            Command.SET_DOWN_N: self._on_set_down_n,
            Command.START: self._on_start,
            Command.STOP: self._on_stop,
            Command.CAL_ZERO: self._on_cal_zero,
            Command.CAL_WRITE: self._on_cal_write,
            Command.CLEAR_FAULT: self._on_clear_fault,
        }

    # --- Inspection ----------------------------------------------------------

    @property
    def state(self) -> DeviceState:
        """State of the device state machine."""
        return self._state

    @property
    def mode(self) -> Mode:
        """Selected operating mode."""
        return self._mode

    @property
    def voltage_mv(self) -> int:
        """Output voltage set-point in millivolts."""
        return self._voltage_mv

    @property
    def faults(self) -> Fault:
        """Faults that are latched."""
        return self._faults

    @property
    def range_lock(self) -> int | None:
        """Locked range, or None while ranging is automatic."""
        return self._range_lock

    @property
    def down_n(self) -> int:
        """Sample count of the step-down rule."""
        return self._down_n

    @property
    def calibration(self) -> Mapping[int, CalibrationWrite]:
        """Values stored by CAL_WRITE, by target."""
        return MappingProxyType(self._calibration)

    @property
    def dropped_blocks(self) -> int:
        """Blocks dropped since the simulator was created."""
        return self._dropped_blocks

    @property
    def ignored_frames(self) -> int:
        """Frames received that were not commands."""
        return self._ignored_frames

    # --- Driving the simulator -----------------------------------------------

    def boot(self) -> None:
        """Run the start-up sequence: self-test, then IDLE or FAULT.

        Calling it again after the first time does nothing.
        """
        if self._state is not DeviceState.BOOT:
            return
        self._enter(DeviceState.SELFTEST)
        if self._config.selftest_passes:
            self._enter(DeviceState.IDLE)
            self._flush_events()
        else:
            self.inject_fault(Fault.SELFTEST)

    def poll(self, timeout: float | None = 0.0) -> int:
        """Answer the commands that arrived.

        Args:
            timeout: Seconds to wait for bytes; zero does not wait and None
                waits without limit.

        Returns:
            The number of frames received, commands or not.

        Raises:
            TransportError: If the transport failed or was closed.
        """
        frames = self._decoder.feed(self._transport.read(_READ_SIZE, timeout))
        for frame in frames:
            self._handle_frame(frame)
        return len(frames)

    def produce(self, blocks: int = 1) -> int:
        """Send stream frames.

        Args:
            blocks: Number of frames to send.

        Returns:
            The number of frames sent, zero unless the state is STREAMING.

        Raises:
            TransportError: If the transport failed or was closed.
        """
        if self._state is not DeviceState.STREAMING:
            return 0
        for _ in range(blocks):
            self._send_block()
        return blocks

    def step(self) -> None:
        """Answer pending commands, then send one stream frame if streaming."""
        self.poll(0.0)
        self.produce(1)

    def serve(self, stop: threading.Event, *, poll_interval: float = 0.01) -> None:
        """Run the simulator until ``stop`` is set or the host disconnects.

        Meant to be the target of a thread. Each turn waits up to
        ``poll_interval`` seconds for commands and then sends one stream frame
        if the state is STREAMING, so the stream is not paced in real time.
        """
        running = True
        while running and not stop.is_set():
            running = self._serve_once(poll_interval)

    def inject_fault(self, fault: Fault) -> None:
        """Latch a fault, as a hardware trip, a power limit or a thermal limit would.

        The state becomes FAULT, which also ends the stream. The fault is
        announced with a FAULT_RAISED event followed by STATE_CHANGED.
        """
        self._faults |= fault
        self._pending_events.append(commands.build_fault_raised(self._faults))
        if self._state is not DeviceState.FAULT:
            self._enter(DeviceState.FAULT)
        self._flush_events()

    def host_disconnected(self) -> None:
        """End the stream because the host closed the port."""
        if self._state is DeviceState.STREAMING:
            self._state = DeviceState.ARMED
        self._pending_events.clear()

    # --- Frames --------------------------------------------------------------

    def _serve_once(self, poll_interval: float) -> bool:
        """Run one turn of :meth:`serve`. Return False when the host is gone."""
        try:
            self.poll(poll_interval)
            self.produce(1)
        except TransportClosedError:
            self.host_disconnected()
            return False
        return True

    def _handle_frame(self, frame: Frame) -> None:
        if frame.frame_type is not FrameType.COMMAND:
            self._ignored_frames += 1
            return
        response = self._respond(frame.payload)
        self._send(FrameType.RESPONSE, frame.sequence, encode_response(response))
        self._flush_events()

    def _respond(self, payload: bytes) -> ResponseMessage:
        """Run the command in ``payload`` and return its response."""
        try:
            message = decode_command(payload)
        except PayloadError:
            return ResponseMessage(_UNKNOWN_COMMAND_ID, Status.BAD_ARGUMENT)
        handler = self._handlers.get(message.command_id)
        if handler is None:
            return ResponseMessage(message.command_id, Status.UNKNOWN_COMMAND)
        blocked = self._blocking_status(message.command_id)
        if blocked is not None:
            return ResponseMessage(message.command_id, blocked)
        try:
            status, data = handler(message.arguments)
        except PayloadError:
            status, data = _BAD_ARGUMENT
        return ResponseMessage(message.command_id, status, data)

    def _blocking_status(self, command_id: int) -> Status | None:
        """Return the status that refuses a command in the present state, if any."""
        if command_id in _QUERIES:
            return None
        if self._state in _STARTING_STATES:
            return Status.BUSY
        if self._state is DeviceState.FAULT and command_id != Command.CLEAR_FAULT:
            return Status.FAULT_ACTIVE
        return None

    def _send(self, frame_type: FrameType, sequence: int, payload: bytes) -> None:
        self._transport.write(encode_frame(Frame(frame_type, sequence, payload)))

    def _next_sequence(self, frame_type: FrameType) -> int:
        sequence = self._sequences[frame_type]
        self._sequences[frame_type] = (sequence + 1) % SEQUENCE_MODULO
        return sequence

    def _enter(self, state: DeviceState) -> None:
        """Change state and queue the event that announces it."""
        self._state = state
        self._pending_events.append(commands.build_state_changed(state))

    def _flush_events(self) -> None:
        events, self._pending_events = self._pending_events, []
        for event in events:
            self._send(FrameType.EVENT, self._next_sequence(FrameType.EVENT), encode_event(event))

    # --- Stream --------------------------------------------------------------

    def _send_block(self) -> None:
        """Send one stream frame, dropping a block first when it is due."""
        config = self._config
        if config.drop_every and self._frames_since_drop == config.drop_every:
            self._sample_number += config.block_samples
            self._pending_dropped += 1
            self._dropped_blocks += 1
            self._frames_since_drop = 0
        first = self._sample_number
        payload = StreamPayload(
            first_index=first % INDEX_MODULO,
            dropped=self._pending_dropped,
            words=tuple(
                self._sample_word(first + offset) for offset in range(config.block_samples)
            ),
        )
        self._pending_dropped = 0
        self._sample_number += config.block_samples
        self._frames_since_drop += 1
        self._send(
            FrameType.STREAM,
            self._next_sequence(FrameType.STREAM),
            encode_stream_payload(payload),
        )

    def _sample_word(self, number: int) -> int:
        """Return the sample word of the synthetic waveform at a sample number."""
        config = self._config
        if self._range_lock is None:
            dwell, position = divmod(number, config.range_dwell)
            range_index = dwell % RANGE_COUNT
            invalid = dwell > 0 and position < config.settle_samples
        else:
            range_index = self._range_lock
            invalid = False
        phase = number % config.waveform_period
        distance = min(phase, config.waveform_period - phase)
        span = config.adc_high - config.adc_low
        adc = config.adc_low + span * distance // (config.waveform_period // 2)
        logic = (number >> _LOGIC_SHIFT) & SAMPLE_LOGIC_MASK
        return pack_sample(Sample(adc=adc, range_index=range_index, invalid=invalid, logic=logic))

    # --- Command handlers ----------------------------------------------------

    def _on_get_info(self, arguments: bytes) -> _Reply:
        commands.parse_no_arguments(arguments, "GET_INFO")
        info = DeviceInfo(
            protocol_version=PROTOCOL_VERSION,
            hardware_revision=self._config.hardware_revision,
            firmware_version=self._config.firmware_version,
        )
        return Status.OK, commands.encode_device_info(info)

    def _on_get_status(self, arguments: bytes) -> _Reply:
        commands.parse_no_arguments(arguments, "GET_STATUS")
        status = DeviceStatus(
            state=self._state, faults=self._faults, dropped_blocks=self._dropped_blocks
        )
        return Status.OK, commands.encode_device_status(status)

    def _on_set_mode(self, arguments: bytes) -> _Reply:
        mode = commands.parse_set_mode(arguments)
        if self._state is not DeviceState.IDLE:
            return _WRONG_STATE
        self._mode = mode
        return _OK

    def _on_set_voltage(self, arguments: bytes) -> _Reply:
        millivolts = commands.parse_set_voltage(arguments)
        if self._mode is not Mode.SOURCE_METER:
            return _WRONG_STATE
        if not self._config.min_voltage_mv <= millivolts <= self._config.max_voltage_mv:
            return _BAD_ARGUMENT
        self._voltage_mv = millivolts
        return _OK

    def _on_dut_power(self, arguments: bytes) -> _Reply:
        on = commands.parse_dut_power(arguments)
        if on:
            if self._state is DeviceState.IDLE:
                self._enter(DeviceState.ARMED)
            return _OK
        if self._state is DeviceState.STREAMING:
            return _WRONG_STATE
        if self._state is DeviceState.ARMED:
            self._enter(DeviceState.IDLE)
        return _OK

    def _on_set_range(self, arguments: bytes) -> _Reply:
        self._range_lock = commands.parse_set_range(arguments)
        return _OK

    def _on_set_down_n(self, arguments: bytes) -> _Reply:
        samples = commands.parse_set_down_n(arguments)
        if samples < 1:
            return _BAD_ARGUMENT
        self._down_n = samples
        return _OK

    def _on_start(self, arguments: bytes) -> _Reply:
        commands.parse_no_arguments(arguments, "START")
        if self._state is not DeviceState.ARMED:
            return _WRONG_STATE
        self._sample_number = 0
        self._frames_since_drop = 0
        self._pending_dropped = 0
        self._enter(DeviceState.STREAMING)
        return _OK

    def _on_stop(self, arguments: bytes) -> _Reply:
        commands.parse_no_arguments(arguments, "STOP")
        if self._state is not DeviceState.STREAMING:
            return _WRONG_STATE
        self._enter(DeviceState.ARMED)
        return _OK

    def _on_cal_zero(self, arguments: bytes) -> _Reply:
        commands.parse_no_arguments(arguments, "CAL_ZERO")
        if self._state is not DeviceState.IDLE:
            return _WRONG_STATE
        return _OK

    def _on_cal_write(self, arguments: bytes) -> _Reply:
        values = commands.parse_cal_write(arguments)
        if self._state is DeviceState.STREAMING:
            return _WRONG_STATE
        self._calibration[values.target] = values
        return _OK

    def _on_clear_fault(self, arguments: bytes) -> _Reply:
        commands.parse_no_arguments(arguments, "CLEAR_FAULT")
        if self._state is DeviceState.FAULT:
            self._faults = Fault(0)
            self._enter(DeviceState.IDLE)
        return _OK
