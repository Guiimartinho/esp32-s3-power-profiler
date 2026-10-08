"""Run the command-line interface with ``python -m s3_power_profiler``."""

from __future__ import annotations

import sys

from s3_power_profiler.cli import main

if __name__ == "__main__":
    sys.exit(main())
