"""Exceptions raised by the package.

Every exception derives from :class:`BoardFiguresError`, so a caller can catch
one type. The command line turns each of them into a message and the exit
status 1.

This module imports nothing from the package, so every layer can use it.
"""

from __future__ import annotations


class BoardFiguresError(Exception):
    """Base class of every error raised by this package."""


class DumpError(BoardFiguresError):
    """A board dump does not have the form that the dump adapter writes."""


class DefinitionError(BoardFiguresError):
    """A board definition file misses a field or holds a value of the wrong kind."""


class BoardError(BoardFiguresError):
    """A calculation was asked about something the board does not have.

    Examples are a pad that does not exist, a pad on another net than the one
    named, and a net without copper on the layers of the calculation.
    """
