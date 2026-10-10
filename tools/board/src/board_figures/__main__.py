"""Run the command-line interface with ``python -m board_figures``."""

from __future__ import annotations

import sys

from board_figures.cli import main

if __name__ == "__main__":
    sys.exit(main())
