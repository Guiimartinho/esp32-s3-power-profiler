from __future__ import annotations

from s3_power_profiler.device import DeviceClient
from s3_power_profiler.protocol import BLOCK_SAMPLES, DeviceState
from s3_power_profiler.sim import Simulator, SimulatorConfig, connect_simulator
from s3_power_profiler.transport import MemoryTransport


def test_returns_a_host_transport_and_a_booted_simulator() -> None:
    transport, simulator = connect_simulator()

    assert isinstance(transport, MemoryTransport)
    assert isinstance(simulator, Simulator)
    assert simulator.state is DeviceState.IDLE


def test_boot_can_be_left_to_the_caller() -> None:
    _transport, simulator = connect_simulator(boot=False)

    assert simulator.state is DeviceState.BOOT


def test_configuration_reaches_the_simulator() -> None:
    transport, _simulator = connect_simulator(SimulatorConfig(hardware_revision=3))

    with DeviceClient(transport) as client:
        assert client.get_info().hardware_revision == 3


def test_client_and_simulator_take_turns_in_one_thread() -> None:
    transport, simulator = connect_simulator()

    with DeviceClient(transport) as client:
        client.set_dut_power(True)
        client.start()
        first = client.read_stream()
        second = client.read_stream()
        client.stop()

    assert first is not None
    assert second is not None
    assert (first.first_index, second.first_index) == (0, BLOCK_SAMPLES)
    assert simulator.state is DeviceState.ARMED
