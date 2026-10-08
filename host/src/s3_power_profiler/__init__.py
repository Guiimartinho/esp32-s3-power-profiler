"""Host software for the Open Power Profiler.

The package is built in layers, and each layer depends only on the ones below it:

* ``protocol``: the wire protocol as pure functions and value objects, without I/O.
* ``transport``: the byte-stream port and its adapters (serial port, memory).
* ``device``: the client that talks to one instrument through a transport.
* ``capture``: sample blocks, gap detection, calibration and statistics.
* ``sim``: a deterministic fake instrument for tests and offline work.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
