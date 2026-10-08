from __future__ import annotations

import struct
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from s3_power_profiler.errors import PayloadError
from s3_power_profiler.protocol._defs import (
    RANGE_COUNT,
    SAMPLE_ADC_MASK,
    SAMPLE_LOGIC_MASK,
    SAMPLE_RANGE_MASK,
    SAMPLE_RESERVED_MASK,
    SAMPLE_RESERVED_SHIFT,
)
from s3_power_profiler.protocol.sample import (
    SAMPLE_WORD_SIZE,
    Sample,
    SampleColumns,
    pack_sample,
    pack_words,
    split_words,
    unpack_sample,
    unpack_words,
)

WORD_MAX = (1 << (8 * SAMPLE_WORD_SIZE)) - 1

samples = st.builds(
    Sample,
    adc=st.integers(min_value=0, max_value=SAMPLE_ADC_MASK),
    range_index=st.integers(min_value=0, max_value=SAMPLE_RANGE_MASK),
    invalid=st.booleans(),
    fault=st.booleans(),
    logic=st.integers(min_value=0, max_value=SAMPLE_LOGIC_MASK),
)
words = st.integers(min_value=0, max_value=WORD_MAX)


def sample_of(vector: dict[str, Any]) -> Sample:
    return Sample(
        adc=vector["adc"],
        range_index=vector["range"],
        invalid=bool(vector["invalid"]),
        fault=bool(vector["fault"]),
        logic=vector["logic"],
    )


def test_pack_reproduces_shared_vector(sample_vector: dict[str, Any]) -> None:
    assert pack_sample(sample_of(sample_vector)) == sample_vector["word"]


def test_unpack_reproduces_shared_vector(sample_vector: dict[str, Any]) -> None:
    assert unpack_sample(sample_vector["word"]) == sample_of(sample_vector)


def test_range_field_holds_every_range_of_the_protocol() -> None:
    assert SAMPLE_RANGE_MASK + 1 == RANGE_COUNT


def test_word_is_four_bytes() -> None:
    assert SAMPLE_WORD_SIZE == 4


@given(sample=samples)
def test_pack_then_unpack_returns_the_sample(sample: Sample) -> None:
    assert unpack_sample(pack_sample(sample)) == sample


@given(sample=samples)
def test_pack_leaves_the_reserved_bits_at_zero(sample: Sample) -> None:
    assert (pack_sample(sample) >> SAMPLE_RESERVED_SHIFT) & SAMPLE_RESERVED_MASK == 0


@given(sample=samples, reserved=st.integers(min_value=1, max_value=SAMPLE_RESERVED_MASK))
def test_unpack_ignores_the_reserved_bits(sample: Sample, reserved: int) -> None:
    word = pack_sample(sample) | (reserved << SAMPLE_RESERVED_SHIFT)

    assert unpack_sample(word) == sample


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adc", -1),
        ("adc", SAMPLE_ADC_MASK + 1),
        ("range_index", -1),
        ("range_index", SAMPLE_RANGE_MASK + 1),
        ("logic", -1),
        ("logic", SAMPLE_LOGIC_MASK + 1),
    ],
)
def test_sample_rejects_a_field_that_does_not_fit(field: str, value: int) -> None:
    fields: dict[str, Any] = {"adc": 0, "range_index": 0, "logic": 0, field: value}

    with pytest.raises(ValueError, match=field):
        Sample(**fields)


def test_sample_flags_default_to_false() -> None:
    sample = Sample(adc=1, range_index=2)

    assert (sample.invalid, sample.fault, sample.logic) == (False, False, 0)


@pytest.mark.parametrize("word", [-1, WORD_MAX + 1])
def test_unpack_rejects_a_word_outside_32_bits(word: int) -> None:
    with pytest.raises(ValueError, match="32 bits"):
        unpack_sample(word)


@given(block=st.lists(words, max_size=64))
def test_pack_words_then_unpack_words_returns_the_block(block: list[int]) -> None:
    data = pack_words(block)

    assert len(data) == SAMPLE_WORD_SIZE * len(block)
    assert unpack_words(data) == tuple(block)


def test_words_are_little_endian() -> None:
    assert pack_words([0xA5021234]) == bytes.fromhex("341202a5")
    assert unpack_words(bytes.fromhex("341202a5ffff0f00")) == (0xA5021234, 0x000FFFFF)


def test_unpack_words_starts_at_the_offset() -> None:
    data = b"\xee" * 3 + struct.pack("<2I", 7, 9)

    assert unpack_words(data, offset=3) == (7, 9)


def test_unpack_words_of_nothing_is_empty() -> None:
    assert unpack_words(b"") == ()
    assert unpack_words(b"\x01\x02", offset=2) == ()


@pytest.mark.parametrize(("size", "offset"), [(1, 0), (5, 0), (8, 1), (4, 5)])
def test_unpack_words_rejects_a_partial_word(size: int, offset: int) -> None:
    with pytest.raises(PayloadError, match="whole number"):
        unpack_words(bytes(size), offset=offset)


@pytest.mark.parametrize("word", [-1, WORD_MAX + 1])
def test_pack_words_rejects_a_word_outside_32_bits(word: int) -> None:
    with pytest.raises(ValueError, match="32 bits"):
        pack_words([0, word])


def test_unpack_words_accepts_bytearray_and_memoryview() -> None:
    data = pack_words([1, 2, 3])

    assert unpack_words(bytearray(data)) == (1, 2, 3)
    assert unpack_words(memoryview(data)) == (1, 2, 3)


@given(block=st.lists(samples, max_size=48))
def test_split_words_gives_one_column_per_field(block: list[Sample]) -> None:
    columns = split_words([pack_sample(sample) for sample in block])

    assert columns == SampleColumns(
        adc=tuple(sample.adc for sample in block),
        range_index=tuple(sample.range_index for sample in block),
        invalid=tuple(sample.invalid for sample in block),
        fault=tuple(sample.fault for sample in block),
        logic=tuple(sample.logic for sample in block),
    )
    assert len(columns) == len(block)
