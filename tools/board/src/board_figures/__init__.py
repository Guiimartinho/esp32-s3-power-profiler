"""Figures of a board layout, calculated from the drawn copper.

The package reads a dump of a KiCad board and calculates the figures that the
documents of the carrier board quote: the resistance of the 1 A path in
squares, whether a loop closes on one layer, the lengths of the Kelvin pairs
and the surface leakage into the measured node. Nothing here is measured on
hardware.
"""

__version__ = "0.1.0.dev0"
