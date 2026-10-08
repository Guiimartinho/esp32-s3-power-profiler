"""Client for one instrument.

The client sends commands, waits for their responses and collects the stream
frames and the events that arrive in between. It is synchronous and meant to be
driven from one thread. It depends on the ``Transport`` interface and on the
protocol package, never on a concrete transport.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType

from s3_power_profiler.errors import (
    CommandError,
    PayloadError,
    ProtocolError,
    ResponseTimeoutError,
)
from s3_power_profiler.protocol import (
    SEQUENCE_MODULO,
    CommandMessage,
    DeviceInfo,
    DeviceStatus,
    EventMessage,
    Frame,
    FrameDecoder,
    FrameType,
    Mode,
    ResponseMessage,
    StreamPayload,
    commands,
    decode_event,
    decode_response,
    decode_stream_payload,
    encode_command,
    encode_frame,
)
from s3_power_profiler.transport.base import Transport

DEFAULT_RESPONSE_TIMEOUT = 1.0
"""Seconds to wait for the answer to a command."""

DEFAULT_READ_SIZE = 4096
"""Largest number of bytes requested from the transport in one read."""

DEFAULT_STREAM_QUEUE = 1024
"""Stream frames kept while the caller is not reading them."""


@dataclass(frozen=True, slots=True)
class LinkStatistics:
    """Counters of what a client received.

    Attributes:
        frames: Valid frames received.
        discarded_bytes: Received bytes that were not part of a valid frame.
        crc_errors: Frames rejected because their CRC did not match.
        malformed_payloads: Valid frames whose payload could not be parsed.
        unexpected_frames: Frames of a type the instrument should not send.
        stale_responses: Responses that matched no pending command.
        stream_overflows: Stream frames lost because the queue was full.
    """

    frames: int
    discarded_bytes: int
    crc_errors: int
    malformed_payloads: int
    unexpected_frames: int
    stale_responses: int
    stream_overflows: int


class DeviceClient:
    """Synchronous client for one instrument.

    Args:
        transport: The byte stream to the instrument.
        response_timeout: Default time to wait for a response, in seconds.
        read_size: Largest number of bytes to request in one read.
        stream_queue: Stream frames to keep while the caller is not reading
            them. When the queue is full the oldest frame is lost and counted.
        clock: Monotonic clock in seconds, replaceable in tests.

    Raises:
        ValueError: If a numeric argument is not positive.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT,
        read_size: int = DEFAULT_READ_SIZE,
        stream_queue: int = DEFAULT_STREAM_QUEUE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if response_timeout <= 0:
            raise ValueError("response_timeout must be positive")
        if read_size <= 0:
            raise ValueError("read_size must be positive")
        if stream_queue <= 0:
            raise ValueError("stream_queue must be positive")
        self._transport = transport
        self._response_timeout = response_timeout
        self._read_size = read_size
        self._clock = clock
        self._decoder = FrameDecoder()
        self._next_sequence = 0
        self._responses: deque[tuple[int, ResponseMessage]] = deque()
        self._streams: deque[StreamPayload] = deque(maxlen=stream_queue)
        self._events: deque[EventMessage] = deque()
        self._malformed_payloads = 0
        self._unexpected_frames = 0
        self._stale_responses = 0
        self._stream_overflows = 0

    def __enter__(self) -> DeviceClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def statistics(self) -> LinkStatistics:
        """Counters of what was received so far."""
        return LinkStatistics(
            frames=self._decoder.frames_decoded,
            discarded_bytes=self._decoder.discarded_bytes,
            crc_errors=self._decoder.crc_errors,
            malformed_payloads=self._malformed_payloads,
            unexpected_frames=self._unexpected_frames,
            stale_responses=self._stale_responses,
            stream_overflows=self._stream_overflows,
        )

    def close(self) -> None:
        """Close the transport."""
        self._transport.close()

    # --- Commands ------------------------------------------------------------

    def request(self, message: CommandMessage, *, timeout: float | None = None) -> ResponseMessage:
        """Send a command and wait for its response.

        The response is matched by sequence number. Stream frames and events
        that arrive while waiting are kept for :meth:`read_stream` and
        :meth:`take_events`.

        Args:
            message: The command to send.
            timeout: Seconds to wait, or None for the default of the client.

        Returns:
            The response, whose status is OK.

        Raises:
            ResponseTimeoutError: If no response arrived in time.
            CommandError: If the instrument answered with a status other than OK.
            ProtocolError: If the response names a different command.
            TransportError: If the transport failed.
        """
        sequence = self._next_sequence
        self._next_sequence = (sequence + 1) % SEQUENCE_MODULO
        frame = Frame(FrameType.COMMAND, sequence, encode_command(message))
        self._transport.write(encode_frame(frame))

        name = commands.describe_command(message.command_id)
        limit = self._response_timeout if timeout is None else timeout
        deadline = self._clock() + limit
        while (response := self._take_response(sequence)) is None:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise ResponseTimeoutError(
                    message.command_id, limit, f"no response to {name} within {limit:g} s"
                )
            self._receive(remaining)

        if response.command_id != message.command_id:
            raise ProtocolError(
                f"response to {name} names {commands.describe_command(response.command_id)}"
            )
        if not response.ok:
            raise CommandError(
                response.command_id,
                response.status_code,
                f"{name} failed: {commands.describe_status(response.status_code)}",
            )
        return response

    def get_info(self) -> DeviceInfo:
        """Return the identity of the instrument."""
        return commands.decode_device_info(self.request(commands.build_get_info()).data)

    def get_status(self) -> DeviceStatus:
        """Return the state, the latched faults and the dropped-block count."""
        return commands.decode_device_status(self.request(commands.build_get_status()).data)

    def set_mode(self, mode: Mode) -> None:
        """Select source meter or ampere meter mode."""
        self.request(commands.build_set_mode(mode))

    def set_voltage(self, millivolts: int) -> None:
        """Set the output voltage of the source meter, in millivolts."""
        self.request(commands.build_set_voltage(millivolts))

    def set_dut_power(self, on: bool) -> None:
        """Close or open the output switch."""
        self.request(commands.build_dut_power(on))

    def set_range(self, range_index: int | None) -> None:
        """Lock a range, or pass None for automatic ranging."""
        self.request(commands.build_set_range(range_index))

    def set_down_n(self, samples: int) -> None:
        """Set the number of samples of the step-down rule."""
        self.request(commands.build_set_down_n(samples))

    def start(self) -> None:
        """Start the sample stream.

        Stream frames still queued from an earlier run are discarded first.
        """
        self._streams.clear()
        self.request(commands.build_start())

    def stop(self) -> None:
        """Stop the sample stream."""
        self.request(commands.build_stop())

    def calibrate_zero(self) -> None:
        """Run the zero calibration."""
        self.request(commands.build_cal_zero())

    def write_calibration(self, target: int, gain: float, offset: float) -> None:
        """Store the gain and the offset of a range or of the DAC."""
        self.request(commands.build_cal_write(target, gain, offset))

    def clear_fault(self) -> None:
        """Reset the fault latch."""
        self.request(commands.build_clear_fault())

    # --- Stream and events ---------------------------------------------------

    def read_stream(self, *, timeout: float | None = None) -> StreamPayload | None:
        """Return the next stream payload.

        Args:
            timeout: Seconds to wait, or None for the default of the client.

        Returns:
            The oldest payload not yet returned, or None if none arrived in time.

        Raises:
            TransportError: If the transport failed.
        """
        limit = self._response_timeout if timeout is None else timeout
        deadline = self._clock() + limit
        while not self._streams:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return None
            self._receive(remaining)
        return self._streams.popleft()

    def take_events(self) -> list[EventMessage]:
        """Return the events received so far, oldest first, and forget them."""
        events = list(self._events)
        self._events.clear()
        return events

    def poll(self, timeout: float = 0.0) -> None:
        """Process what the instrument sent, waiting at most ``timeout`` seconds.

        Raises:
            TransportError: If the transport failed.
        """
        self._receive(timeout)

    # --- Internals -----------------------------------------------------------

    def _take_response(self, sequence: int) -> ResponseMessage | None:
        """Return the queued response to ``sequence``, dropping older ones."""
        while self._responses:
            received_sequence, response = self._responses.popleft()
            if received_sequence == sequence:
                return response
            self._stale_responses += 1
        return None

    def _receive(self, timeout: float) -> None:
        """Read once from the transport and sort the frames that completed."""
        data = self._transport.read(self._read_size, timeout)
        for frame in self._decoder.feed(data):
            self._dispatch(frame)

    def _dispatch(self, frame: Frame) -> None:
        """Queue one received frame according to its type."""
        try:
            if frame.frame_type is FrameType.STREAM:
                self._queue_stream(decode_stream_payload(frame.payload))
            elif frame.frame_type is FrameType.EVENT:
                self._events.append(decode_event(frame.payload))
            elif frame.frame_type is FrameType.RESPONSE:
                self._responses.append((frame.sequence, decode_response(frame.payload)))
            else:
                self._unexpected_frames += 1
        except PayloadError:
            self._malformed_payloads += 1

    def _queue_stream(self, payload: StreamPayload) -> None:
        if len(self._streams) == self._streams.maxlen:
            self._stream_overflows += 1
        self._streams.append(payload)
