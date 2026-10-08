from __future__ import annotations

import itertools
import struct
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from s3_power_profiler.protocol._defs import (
    FRAME_CRC_SIZE,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    FRAME_MAX_PAYLOAD,
    PROTOCOL_VERSION,
    FrameType,
)
from s3_power_profiler.protocol.frame import SEQUENCE_MODULO, Frame, FrameDecoder, encode_frame

MAGIC = struct.pack("<H", FRAME_MAGIC)
OVERHEAD = FRAME_HEADER_SIZE + FRAME_CRC_SIZE
UNKNOWN_TYPE = max(FrameType) + 1

frames = st.builds(
    Frame,
    frame_type=st.sampled_from(FrameType),
    sequence=st.integers(min_value=0, max_value=SEQUENCE_MODULO - 1),
    payload=st.binary(max_size=96),
    flags=st.integers(min_value=0, max_value=0xFF),
)


def header(type_id: int, length: int, sequence: int = 0, flags: int = 0) -> bytes:
    """Build a raw header, valid or not."""
    return struct.pack("<HBBHH", FRAME_MAGIC, type_id, flags, length, sequence)


def split(data: bytes, cuts: list[int]) -> list[bytes]:
    """Cut ``data`` at the given positions, in order."""
    edges = [0, *sorted(cut % (len(data) + 1) for cut in cuts), len(data)]
    return [data[start:end] for start, end in itertools.pairwise(edges)]


def frame_of(vector: dict[str, Any]) -> Frame:
    return Frame(FrameType(vector["type"]), vector["sequence"], bytes.fromhex(vector["payload"]))


# --- Shared vectors ---------------------------------------------------------


def test_vectors_were_generated_for_this_protocol_version(vectors: dict[str, Any]) -> None:
    assert vectors["protocol_version"] == PROTOCOL_VERSION


def test_encode_reproduces_shared_vector(frame_vector: dict[str, Any]) -> None:
    assert encode_frame(frame_of(frame_vector)).hex() == frame_vector["frame"]


def test_decode_reproduces_shared_vector(frame_vector: dict[str, Any]) -> None:
    decoder = FrameDecoder()

    decoded = decoder.feed(bytes.fromhex(frame_vector["frame"]))

    assert decoded == [frame_of(frame_vector)]
    assert decoder.frames_decoded == 1
    assert decoder.discarded_bytes == 0
    assert decoder.crc_errors == 0
    assert decoder.pending_bytes == 0


def test_decode_all_shared_vectors_as_one_stream(vectors: dict[str, Any]) -> None:
    stream = b"".join(bytes.fromhex(vector["frame"]) for vector in vectors["frames"])

    decoded = FrameDecoder().feed(stream)

    assert decoded == [frame_of(vector) for vector in vectors["frames"]]


# --- Layout -----------------------------------------------------------------


def test_empty_frame_is_header_plus_crc() -> None:
    encoded = encode_frame(Frame(FrameType.COMMAND, 0))

    assert len(encoded) == OVERHEAD
    assert encoded.startswith(MAGIC)


def test_fields_are_little_endian() -> None:
    encoded = encode_frame(Frame(FrameType.EVENT, 0x1234, b"\xaa\xbb\xcc", flags=0x80))

    magic, type_id, flags, length, sequence = struct.unpack_from("<HBBHH", encoded)
    assert (magic, type_id, flags, length, sequence) == (
        FRAME_MAGIC,
        FrameType.EVENT,
        0x80,
        3,
        0x1234,
    )
    assert encoded[FRAME_HEADER_SIZE:-FRAME_CRC_SIZE] == b"\xaa\xbb\xcc"


def test_largest_payload_round_trips() -> None:
    frame = Frame(FrameType.STREAM, SEQUENCE_MODULO - 1, bytes(FRAME_MAX_PAYLOAD))

    assert FrameDecoder().feed(encode_frame(frame)) == [frame]


# --- Frame validation -------------------------------------------------------


@pytest.mark.parametrize("sequence", [-1, SEQUENCE_MODULO])
def test_frame_rejects_sequence_outside_16_bits(sequence: int) -> None:
    with pytest.raises(ValueError, match="sequence"):
        Frame(FrameType.COMMAND, sequence)


@pytest.mark.parametrize("flags", [-1, 0x100])
def test_frame_rejects_flags_outside_8_bits(flags: int) -> None:
    with pytest.raises(ValueError, match="flags"):
        Frame(FrameType.COMMAND, 0, flags=flags)


def test_frame_rejects_payload_over_the_limit() -> None:
    with pytest.raises(ValueError, match="payload"):
        Frame(FrameType.COMMAND, 0, bytes(FRAME_MAX_PAYLOAD + 1))


def test_frame_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="FrameType"):
        Frame(UNKNOWN_TYPE, 0)  # type: ignore[arg-type]


def test_frame_stores_type_as_enum_and_payload_as_bytes() -> None:
    frame = Frame(int(FrameType.RESPONSE), 5, bytearray(b"\x01\x02"))  # type: ignore[arg-type]

    assert frame.frame_type is FrameType.RESPONSE
    assert isinstance(frame.payload, bytes)
    assert frame == Frame(FrameType.RESPONSE, 5, b"\x01\x02")


# --- Properties -------------------------------------------------------------


@given(frame=frames)
def test_encode_then_decode_returns_the_frame(frame: Frame) -> None:
    decoder = FrameDecoder()

    assert decoder.feed(encode_frame(frame)) == [frame]
    assert decoder.discarded_bytes == 0
    assert decoder.pending_bytes == 0


@given(sent=st.lists(frames, max_size=6), cuts=st.lists(st.integers(min_value=0), max_size=12))
def test_chunk_boundaries_do_not_change_the_result(sent: list[Frame], cuts: list[int]) -> None:
    stream = b"".join(encode_frame(frame) for frame in sent)
    decoder = FrameDecoder()

    received = [frame for chunk in split(stream, cuts) for frame in decoder.feed(chunk)]

    assert received == sent
    assert decoder.discarded_bytes == 0
    assert decoder.crc_errors == 0
    assert decoder.pending_bytes == 0


@given(noise=st.binary(max_size=64), sent=st.lists(frames, min_size=1, max_size=4))
def test_resynchronizes_after_noise_without_a_magic_byte(noise: bytes, sent: list[Frame]) -> None:
    noise = noise.replace(MAGIC[:1], b"\x00")
    decoder = FrameDecoder()

    received = decoder.feed(noise + b"".join(encode_frame(frame) for frame in sent))

    assert received == sent
    assert decoder.discarded_bytes == len(noise)
    assert decoder.crc_errors == 0


@given(
    damaged=frames,
    position=st.integers(min_value=0),
    bit=st.integers(min_value=0, max_value=7),
    sent=st.lists(frames, min_size=1, max_size=3),
)
def test_resynchronizes_after_a_corrupted_frame(
    damaged: Frame, position: int, bit: int, sent: list[Frame]
) -> None:
    # Damage the payload or the CRC, so the frame keeps its length, and keep the
    # first magic byte out of the rest of it, so nothing inside looks like a frame.
    corrupted = bytearray(encode_frame(damaged))
    index = FRAME_HEADER_SIZE + position % (len(corrupted) - FRAME_HEADER_SIZE)
    corrupted[index] ^= 1 << bit
    assume(MAGIC[0] not in corrupted[1:])
    decoder = FrameDecoder()

    received = decoder.feed(bytes(corrupted) + b"".join(encode_frame(frame) for frame in sent))

    assert received == sent
    assert decoder.crc_errors == 1
    assert decoder.discarded_bytes == len(corrupted)


@given(
    pieces=st.lists(st.one_of(st.binary(max_size=40), frames.map(encode_frame)), max_size=8),
    cuts=st.lists(st.integers(min_value=0), max_size=8),
)
def test_every_byte_is_delivered_discarded_or_pending(pieces: list[bytes], cuts: list[int]) -> None:
    stream = b"".join(pieces)
    decoder = FrameDecoder()

    received = [frame for chunk in split(stream, cuts) for frame in decoder.feed(chunk)]

    delivered = sum(len(encode_frame(frame)) for frame in received)
    assert delivered + decoder.discarded_bytes + decoder.pending_bytes == len(stream)
    assert decoder.frames_decoded == len(received)
    assert all(encode_frame(frame) in stream for frame in received)


# --- Decoder details --------------------------------------------------------


def test_feed_without_a_complete_frame_returns_nothing() -> None:
    encoded = encode_frame(Frame(FrameType.COMMAND, 1, b"\x01"))
    decoder = FrameDecoder()

    assert decoder.feed(encoded[:-1]) == []
    assert decoder.pending_bytes == len(encoded) - 1
    assert decoder.feed(encoded[-1:]) == [Frame(FrameType.COMMAND, 1, b"\x01")]


def test_magic_split_between_two_chunks_is_found() -> None:
    encoded = encode_frame(Frame(FrameType.EVENT, 2, b"\x03\x05"))
    decoder = FrameDecoder()

    assert decoder.feed(b"\x00\x11" + encoded[:1]) == []
    assert decoder.pending_bytes == 1
    assert decoder.discarded_bytes == 2
    assert decoder.feed(encoded[1:]) == [Frame(FrameType.EVENT, 2, b"\x03\x05")]


def test_first_magic_byte_followed_by_other_data_is_discarded() -> None:
    decoder = FrameDecoder()

    assert decoder.feed(MAGIC[:1]) == []
    assert decoder.feed(b"\x00\x00") == []
    assert decoder.pending_bytes == 0
    assert decoder.discarded_bytes == 3


def test_header_with_unknown_type_is_skipped_at_once() -> None:
    good = Frame(FrameType.RESPONSE, 9, b"\x20\x00")
    decoder = FrameDecoder()

    received = decoder.feed(header(UNKNOWN_TYPE, 1) + encode_frame(good))

    assert received == [good]
    assert decoder.crc_errors == 0
    assert decoder.discarded_bytes == FRAME_HEADER_SIZE


def test_header_announcing_too_much_payload_is_skipped_at_once() -> None:
    good = Frame(FrameType.RESPONSE, 9, b"\x20\x00")
    decoder = FrameDecoder()

    received = decoder.feed(header(FrameType.STREAM, FRAME_MAX_PAYLOAD + 1) + encode_frame(good))

    assert received == [good]
    assert decoder.crc_errors == 0
    assert decoder.discarded_bytes == FRAME_HEADER_SIZE


def test_decoder_can_accept_less_than_the_protocol_limit() -> None:
    small = Frame(FrameType.COMMAND, 1, bytes(4))
    large = Frame(FrameType.COMMAND, 2, bytes(5))
    decoder = FrameDecoder(max_payload=4)

    assert decoder.feed(encode_frame(large) + encode_frame(small)) == [small]
    assert decoder.discarded_bytes == len(encode_frame(large))


@pytest.mark.parametrize("max_payload", [-1, FRAME_MAX_PAYLOAD + 1])
def test_decoder_rejects_a_limit_outside_the_protocol(max_payload: int) -> None:
    with pytest.raises(ValueError, match="max_payload"):
        FrameDecoder(max_payload=max_payload)


def test_false_header_holds_frames_back_until_its_payload_arrived() -> None:
    # The header has no checksum of its own. A false one that passes the checks
    # delays what follows until the payload it announces is there to be checked.
    announced = 40
    good = Frame(FrameType.RESPONSE, 3, b"\x20\x00")
    false_start = header(FrameType.STREAM, announced)
    decoder = FrameDecoder()

    assert decoder.feed(false_start + encode_frame(good)) == []
    assert decoder.pending_bytes == len(false_start) + len(encode_frame(good))

    received = decoder.feed(bytes(announced + FRAME_CRC_SIZE))

    assert received == [good]
    assert decoder.crc_errors == 1


def test_flags_are_passed_through() -> None:
    frame = Frame(FrameType.EVENT, 0, b"\x01", flags=0x5A)

    assert FrameDecoder().feed(encode_frame(frame)) == [frame]


def test_reset_forgets_pending_bytes_and_counters() -> None:
    encoded = encode_frame(Frame(FrameType.COMMAND, 1, b"\x01"))
    decoder = FrameDecoder()
    decoder.feed(b"\x00" + encoded + encoded[:4])

    decoder.reset()

    assert decoder.pending_bytes == 0
    assert decoder.frames_decoded == 0
    assert decoder.discarded_bytes == 0
    assert decoder.crc_errors == 0
    assert decoder.feed(encoded) == [Frame(FrameType.COMMAND, 1, b"\x01")]


def test_accepts_bytearray_and_memoryview() -> None:
    frame = Frame(FrameType.COMMAND, 7, b"\x01")
    encoded = encode_frame(frame)
    decoder = FrameDecoder()

    assert decoder.feed(bytearray(encoded)) == [frame]
    assert decoder.feed(memoryview(encoded)) == [frame]
