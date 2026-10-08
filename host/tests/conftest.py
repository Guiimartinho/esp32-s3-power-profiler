"""Fixtures shared by the test modules.

The protocol test vectors are generated at the root of the repository and are
shared with the firmware tests. A test that takes ``crc_vector``,
``frame_vector`` or ``sample_vector`` runs once per vector of that kind.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings

VECTORS_PATH = Path(__file__).resolve().parents[2] / "protocol" / "vectors.json"

_VECTOR_ARGUMENTS = {"crc_vector": "crc", "frame_vector": "frames", "sample_vector": "samples"}

# Repeatable runs: the same examples every time, and no time limit per example.
settings.register_profile("repeatable", deadline=None, derandomize=True)
settings.load_profile("repeatable")


@functools.lru_cache(maxsize=1)
def _load_vectors() -> dict[str, Any]:
    with VECTORS_PATH.open(encoding="utf-8") as handle:
        vectors: dict[str, Any] = json.load(handle)
    return vectors


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    vectors = _load_vectors()
    for argument, group in _VECTOR_ARGUMENTS.items():
        if argument in metafunc.fixturenames:
            entries = vectors[group]
            metafunc.parametrize(argument, entries, ids=[entry["name"] for entry in entries])


@pytest.fixture(scope="session")
def vectors() -> dict[str, Any]:
    """All shared protocol vectors."""
    return _load_vectors()


@pytest.fixture(scope="session")
def frame_named(vectors: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    """Look up one frame vector by its name."""

    def lookup(name: str) -> dict[str, Any]:
        entry: dict[str, Any] = next(item for item in vectors["frames"] if item["name"] == name)
        return entry

    return lookup
