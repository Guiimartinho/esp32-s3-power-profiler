from __future__ import annotations

import pytest

from circuit_sim.errors import (
    BenchError,
    EngineError,
    MeasureError,
    ModelError,
    NetlistError,
    SimulationError,
    ValueFormatError,
)


@pytest.mark.parametrize(
    "error", [BenchError, EngineError, MeasureError, ModelError, NetlistError, ValueFormatError]
)
def test_every_error_derives_from_one_base(error: type[Exception]) -> None:
    assert issubclass(error, SimulationError)

    with pytest.raises(SimulationError, match="what went wrong"):
        raise error("what went wrong")


def test_the_base_is_not_an_error_of_the_interpreter() -> None:
    # A caller tells a bad input or a failed run from a defect of the program
    # by this base alone: it must not be caught along with a ValueError.
    assert SimulationError.__bases__ == (Exception,)
