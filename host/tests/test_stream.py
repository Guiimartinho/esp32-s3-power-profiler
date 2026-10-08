from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from s3_power_profiler.errors import PayloadError
from s3_power_profiler.protocol._defs import BLOCK_SAMPLES, FRAME_MAX_PAYLOAD
from s3_power_profiler.protocol.sample import SAMPLE_WORD_SIZE, pack_words
from s3_power_profiler.protocol.stream import (
    INDEX_MODULO,
    MAX_STREAM_SAMPLES,
    STREAM_HEADER_SIZE,
    StreamPayload,
    decode_stream_payload,
    encode_stream_payload,
)

payloads = st.builds(
    StreamPayload,
    first_index=st.integers(min_value=0, max_value=INDEX_MODULO - 1),
    dropped=st.integers(min_value=0, max_value=0xFFFF),
    words=st.lists(st.integers(min_value=0, max_value=0xFFFFFFFF), max_size=32).map(tuple),
)


def test_decode_reproduces_shared_vector(
    frame_named: Callable[[str], dict[str, Any]],
) -> None:
    data = bytes.fromhex(frame_named("stream_two_samples")["payload"])

    payload = decode_stream_payload(data)

    assert payload == StreamPayload(
        first_index=0x00012345, dropped=0, words=(0xA5021234, 0x000FFFFF)
    )
    assert payload.count == 2


def test_encode_reproduces_shared_vector(
    frame_named: Callable[[str], dict[str, Any]],
) -> None:
    payload = StreamPayload(first_index=0x00012345, dropped=0, words=(0xA5021234, 0x000FFFFF))

    assert encode_stream_payload(payload).hex() == frame_named("stream_two_samples")["payload"]


def test_header_is_eight_bytes_before_the_words() -> None:
    encoded = encode_stream_payload(StreamPayload(first_index=1, dropped=2, words=(3,)))

    assert STREAM_HEADER_SIZE == 8
    assert encoded == bytes.fromhex("0100000002000100") + pack_words([3])


def test_a_normal_block_fits_in_a_frame() -> None:
    assert BLOCK_SAMPLES <= MAX_STREAM_SAMPLES
    assert STREAM_HEADER_SIZE + SAMPLE_WORD_SIZE * MAX_STREAM_SAMPLES <= FRAME_MAX_PAYLOAD


@given(payload=payloads)
def test_encode_then_decode_returns_the_payload(payload: StreamPayload) -> None:
    assert decode_stream_payload(encode_stream_payload(payload)) == payload


def test_full_frame_round_trips() -> None:
    payload = StreamPayload(
        first_index=INDEX_MODULO - 1, dropped=0xFFFF, words=tuple(range(MAX_STREAM_SAMPLES))
    )

    encoded = encode_stream_payload(payload)

    assert len(encoded) <= FRAME_MAX_PAYLOAD
    assert decode_stream_payload(encoded) == payload


def test_payload_without_samples_round_trips() -> None:
    payload = StreamPayload(first_index=10, dropped=1)

    assert payload.count == 0
    assert decode_stream_payload(encode_stream_payload(payload)) == payload


def test_words_are_stored_as_a_tuple() -> None:
    payload = StreamPayload(first_index=0, dropped=0, words=[1, 2])  # type: ignore[arg-type]

    assert payload.words == (1, 2)


def test_decode_accepts_bytearray_and_memoryview() -> None:
    payload = StreamPayload(first_index=5, dropped=0, words=(1, 2, 3))
    encoded = encode_stream_payload(payload)

    assert decode_stream_payload(bytearray(encoded)) == payload
    assert decode_stream_payload(memoryview(encoded)) == payload


@pytest.mark.parametrize("size", range(STREAM_HEADER_SIZE))
def test_decode_rejects_a_payload_shorter_than_the_header(size: int) -> None:
    with pytest.raises(PayloadError, match="shorter than"):
        decode_stream_payload(bytes(size))


def test_decode_rejects_a_partial_sample_word() -> None:
    encoded = encode_stream_payload(StreamPayload(first_index=0, dropped=0, words=(1,)))

    with pytest.raises(PayloadError, match="whole number"):
        decode_stream_payload(encoded[:-1])


@pytest.mark.parametrize("announced", [0, 1, 3])
def test_decode_rejects_a_count_that_does_not_match_the_length(announced: int) -> None:
    data = bytes.fromhex("000000000000") + announced.to_bytes(2, "little") + pack_words([7, 8])

    with pytest.raises(PayloadError, match=f"announces {announced} samples but carries 2"):
        decode_stream_payload(data)


@pytest.mark.parametrize("first_index", [-1, INDEX_MODULO])
def test_payload_rejects_an_index_outside_32_bits(first_index: int) -> None:
    with pytest.raises(ValueError, match="first_index"):
        StreamPayload(first_index=first_index, dropped=0)


@pytest.mark.parametrize("dropped", [-1, 0x10000])
def test_payload_rejects_a_dropped_count_outside_16_bits(dropped: int) -> None:
    with pytest.raises(ValueError, match="dropped"):
        StreamPayload(first_index=0, dropped=dropped)


def test_payload_rejects_more_samples_than_a_frame_holds() -> None:
    with pytest.raises(ValueError, match="exceed the limit"):
        StreamPayload(first_index=0, dropped=0, words=(0,) * (MAX_STREAM_SAMPLES + 1))


def test_encode_rejects_a_word_outside_32_bits() -> None:
    with pytest.raises(ValueError, match="32 bits"):
        encode_stream_payload(StreamPayload(first_index=0, dropped=0, words=(1 << 32,)))
