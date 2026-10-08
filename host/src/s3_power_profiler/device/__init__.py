"""The client that talks to one instrument through a transport."""

from __future__ import annotations

from s3_power_profiler.device.client import DeviceClient, LinkStatistics

__all__ = ["DeviceClient", "LinkStatistics"]
