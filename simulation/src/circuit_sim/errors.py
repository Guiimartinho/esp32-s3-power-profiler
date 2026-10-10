"""Exceptions of the package.

Every error the package raises on purpose derives from
:class:`SimulationError`, so that a caller can tell a bad input or a failed
run from a defect of the program.
"""

from __future__ import annotations


class SimulationError(Exception):
    """Base class of the errors of the package."""


class ValueFormatError(SimulationError):
    """A component value of the schematic cannot be read as a number."""


class NetlistError(SimulationError):
    """The netlist snapshot is malformed or does not hold what a block asks."""


class ModelError(SimulationError):
    """A part has no model, or a model file is missing or does not match."""


class EngineError(SimulationError):
    """The simulator could not be found or a run failed."""


class BenchError(SimulationError):
    """A bench definition is malformed or names something that does not exist."""


class MeasureError(SimulationError):
    """A figure cannot be taken from the waveforms that a run produced."""
