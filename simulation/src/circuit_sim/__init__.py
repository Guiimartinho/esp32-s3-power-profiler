"""Circuit simulations of the carrier board.

The package builds SPICE decks from the netlist of the schematic, runs them
in the ngspice shared library, takes figures from the waveforms and compares
them with the limits of the specification. Everything it reports is a
simulation result: nothing here is measured on hardware.
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
