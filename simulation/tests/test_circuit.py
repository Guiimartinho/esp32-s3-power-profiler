from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from circuit_sim.circuit import (
    GROUND_NETS,
    Circuit,
    ModelMap,
    PartModel,
    build_circuit,
    load_model_map,
    node_name,
)
from circuit_sim.errors import ModelError, NetlistError, ValueFormatError
from circuit_sim.netlist import Component, Netlist, Pin, load_snapshot, netlist_from_snapshot

CARRIER = Path(__file__).resolve().parents[1] / "netlist" / "carrier.json"
NO_MODELS = ModelMap()


def one_part(ref: str, value: str, *pins: tuple[str, str], mpn: str = "") -> Netlist:
    """A schematic of one part, its pins as (number, net)."""
    part = Component(ref, value, mpn, "/", tuple(Pin(number, net, "") for number, net in pins))
    return Netlist("One Part", "T1", {ref: part})


def write_map(folder: Path, text: str, name: str = "models.toml") -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("net", "node"),
    [
        ("GND", "0"),
        ("VREF", "vref"),
        ("+12V_A", "p12v_a"),
        ("-4V_A", "m4v_a"),
        ("+3V3_A", "p3v3_a"),
        ("+BATT", "pbatt"),
        ("/Shunt Ladder/INP", "shunt_ladder_inp"),
        ("/Output Stage/VOUT_S", "output_stage_vout_s"),
        ("Net-(Q12-G)", "n_q12_g"),
        ("Net-(Q14-S-Pad1)", "n_q14_s_pad1"),
        ("Net-(RN1-R4.1)", "n_rn1_r4_1"),
        ("unconnected-(U1-ADC_VREF-Pad35)", "nc_u1_adc_vref_pad35"),
        ("", "unnamed"),
        ("/", "unnamed"),
    ],
)
def test_a_net_becomes_a_node_that_spice_can_read(net: str, node: str) -> None:
    assert node_name(net) == node


@pytest.mark.parametrize(
    ("plus", "minus", "nodes"),
    [
        ("+12V_A", "-12V_A", ("p12v_a", "m12v_a")),
        ("Net-(U29-+)", "Net-(U29--)", ("n_u29_p", "n_u29_n")),
        ("Net-(U14A-+)", "Net-(U14A--)", ("n_u14a_p", "n_u14a_n")),
        ("Net-(U11-C+)", "Net-(U11-C-)", ("n_u11_c_p", "n_u11_c_n")),
        ("Net-(U5-IN+)", "Net-(U5-IN-)", ("n_u5_in_p", "n_u5_in_n")),
    ],
)
def test_two_nets_that_differ_in_a_sign_stay_apart(
    plus: str, minus: str, nodes: tuple[str, str]
) -> None:
    assert (node_name(plus), node_name(minus)) == nodes


def test_an_alias_names_a_net_and_ground_stays_node_zero() -> None:
    aliases = {"/Shunt Ladder/INP": "inp", "GND": "ground", "VREF": "Reference"}

    assert node_name("/Shunt Ladder/INP", aliases) == "inp"
    assert node_name("/Shunt Ladder/INN", aliases) == "shunt_ladder_inn"
    assert node_name("VREF", aliases) == "Reference"
    assert node_name("GND", aliases) == "0"
    assert frozenset({"GND"}) == GROUND_NETS


def test_every_net_of_the_carrier_board_has_a_node_of_its_own() -> None:
    nets = load_snapshot(CARRIER).nets()
    nodes: dict[str, list[str]] = {}
    for net in nets:
        nodes.setdefault(node_name(net), []).append(net)

    assert {node: both for node, both in nodes.items() if len(both) > 1} == {}
    assert len(nets) > 200


def test_a_model_for_one_designator_wins_over_every_other(netlist: Netlist) -> None:
    by_ref = PartModel("subckt", name="FOR_U1")
    vendor = PartModel("subckt", name="OF_THE_MAKER", origin="vendor")
    by_number = PartModel("subckt", name="BY_PART_NUMBER")
    by_value = PartModel("subckt", name="BY_VALUE")
    amplifier = netlist.component("U1")
    part_number, value = amplifier.mpn, amplifier.value

    everything = ModelMap(
        {"U1": by_ref}, {part_number: by_number, value: by_value}, {part_number: vendor}
    )
    without_ref = ModelMap({}, {part_number: by_number, value: by_value}, {part_number: vendor})
    without_number = ModelMap({}, {value: by_value}, {})

    assert everything.model_of(amplifier) is by_ref
    assert everything.model_of(amplifier, "vendor") is by_ref
    assert without_ref.model_of(amplifier, "vendor") is vendor
    assert without_ref.model_of(amplifier) is by_number
    assert without_ref.model_of(amplifier, "open") is by_number
    assert without_number.model_of(amplifier) is by_value
    assert without_number.model_of(amplifier, "vendor") is by_value


@pytest.mark.parametrize(
    ("ref", "kind", "origin"),
    [
        ("R1", "resistor", "ideal"),
        ("C1", "capacitor", "ideal"),
        ("L1", "inductor", "ideal"),
        ("RN1", "network", "ideal"),
        ("TP1", "skip", ""),
        ("H1", "skip", ""),
        ("FID1", "skip", ""),
    ],
)
def test_a_part_without_an_entry_is_what_its_designator_says(
    netlist: Netlist, ref: str, kind: str, origin: str
) -> None:
    assert NO_MODELS.model_of(netlist.component(ref)) == PartModel(kind=kind, origin=origin)


def test_a_part_without_a_model_is_an_error(netlist: Netlist) -> None:
    with pytest.raises(ModelError, match=r"U1 \(OPA365AIDBVR\) has no model in the model map"):
        NO_MODELS.model_of(netlist.component("U1"))
    with pytest.raises(ModelError, match=r"J1 \(Conn_01x02\) has no model in the model map"):
        NO_MODELS.model_of(netlist.component("J1"))


def test_the_passive_parts_take_their_values_and_nets_from_the_schematic(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["R1", "R2", "C1", "C2", "C3", "L1"])

    assert circuit.lines == (
        "C1 ladder_supply 0 1e-07",
        "C2 ladder_vout_s 0 1e-06",
        "C3 p12v_a 0 1e-05",
        "L1 p5v n_l1_pad2 1e-05",
        "R1 ladder_supply ladder_vout_s 1000",
        "R2 n_q1_s ladder_vout_s 33",
    )
    assert circuit.libraries == ()
    assert circuit.origins == ()
    assert circuit.text() == "\n".join(circuit.lines) + "\n"


def test_the_parts_come_once_each_in_a_fixed_order(netlist: Netlist, models: ModelMap) -> None:
    refs = ["RN1", "R2", "C1", "R1", "R2", "JP1", "C1"]

    forward = build_circuit(netlist, models, refs)
    backward = build_circuit(netlist, models, (ref for ref in reversed(refs)))

    assert [line.split()[0] for line in forward.lines] == [
        "C1",
        "R1",
        "R2",
        "RJP1",
        "RRN1_1",
        "RRN1_2",
        "RRN1_3",
    ]
    assert backward == forward


def test_a_part_that_the_schematic_does_not_have_is_an_error(
    netlist: Netlist, models: ModelMap
) -> None:
    with pytest.raises(NetlistError, match="the schematic has no part R99"):
        build_circuit(netlist, models, ["R1", "R99"])


def test_a_zero_ohm_link_stays_a_branch(netlist: Netlist, models: ModelMap) -> None:
    circuit = build_circuit(netlist, models, ["R4"])

    assert circuit.lines == ("R4 n_q1_g ladder_gate_r1 0.001",)


def test_a_capacitor_of_no_value_is_not_given_a_resistance() -> None:
    circuit = build_circuit(one_part("C9", "0", ("1", "a"), ("2", "b")), NO_MODELS, ["C9"])

    assert circuit.lines == ("C9 a b 0",)


def test_a_value_that_is_no_number_stops_the_circuit() -> None:
    schematic = one_part("R9", "DNP", ("1", "a"), ("2", "b"))

    with pytest.raises(ValueFormatError, match="cannot read 'DNP' as a component value"):
        build_circuit(schematic, NO_MODELS, ["R9"])


def test_a_scale_moves_the_value_of_a_passive_part(netlist: Netlist, models: ModelMap) -> None:
    scales = {"R1": 1.001, "C1": 0.9, "L1": 1.2, "RN1": 1.05, "R3": 0.9975, "R4": 2.0, "Q1": 3.0}

    circuit = build_circuit(
        netlist, models, ["R1", "C1", "L1", "RN1", "R3", "R4", "Q1"], scales=scales
    )

    assert circuit.lines == (
        "C1 ladder_supply 0 9e-08",
        "L1 p5v n_l1_pad2 1.2e-05",
        "MQ1 ladder_supply n_q1_g n_q1_s IRLML0030",
        "R1 ladder_supply ladder_vout_s 1001",
        "R3 n_q2_s ladder_vout_s 0.09975",
        "RR3_SA n_q2_s n_u1_p 0.001",
        "RR3_SB ladder_vout_s n_u1_n 0.001",
        "R4 n_q1_g ladder_gate_r1 0.001",
        "RRN1_1 chain_cmd_a 0 10500",
        "RRN1_2 chain_cmd_b 0 10500",
        "RRN1_3 n_rn1_r3_1 0 10500",
    )


def test_the_text_of_a_model_is_appended_to_the_element(netlist: Netlist, models: ModelMap) -> None:
    overrides = {
        "R1": PartModel("resistor", params="tc1=25e-6"),
        "C1": PartModel("capacitor", params="ic=5"),
        "L1": PartModel("inductor", params="ic=0.1"),
        "R3": PartModel("kelvin", ports=("1", "2", "3", "4"), params="tc1=50e-6"),
        "U1": PartModel("subckt", name="OPA", ports=("3", "4", "1"), params="gbw=50meg"),
        "Q1": PartModel(
            "device", name="NMOS", letter="M", ports=("3", "1", "2", "2"), params="m=2"
        ),
    }

    circuit = build_circuit(netlist, models, list(overrides), overrides=overrides)

    assert circuit.lines == (
        "C1 ladder_supply 0 1e-07 ic=5",
        "L1 p5v n_l1_pad2 1e-05 ic=0.1",
        "MQ1 ladder_supply n_q1_g n_q1_s n_q1_s NMOS m=2",
        "R1 ladder_supply ladder_vout_s 1000 tc1=25e-6",
        "R3 n_q2_s ladder_vout_s 0.1 tc1=50e-6",
        "RR3_SA n_q2_s n_u1_p 0.001",
        "RR3_SB ladder_vout_s n_u1_n 0.001",
        "XU1 n_u1_p n_u1_n chain_amp_out OPA gbw=50meg",
    )


@pytest.mark.parametrize(
    ("ref", "value", "pins", "kind"),
    [
        ("R9", "1R", 4, "resistor"),
        ("R9", "1R", 1, "resistor"),
        ("C9", "1n", 3, "capacitor"),
        ("L9", "1u", 0, "inductor"),
    ],
)
def test_a_part_with_other_than_two_pins_needs_its_pins_named(
    ref: str, value: str, pins: int, kind: str
) -> None:
    schematic = one_part(ref, value, *[(str(number + 1), f"net{number}") for number in range(pins)])

    assert NO_MODELS.model_of(schematic.component(ref)).kind == kind
    with pytest.raises(
        ModelError,
        match=f"{ref} has {pins} connected pins: the model map has to say which of them",
    ):
        build_circuit(schematic, NO_MODELS, [ref])


def test_a_four_terminal_resistor_can_be_one_resistor_between_two_named_pins(
    netlist: Netlist,
) -> None:
    overrides = {"R3": PartModel("resistor", ports=("1", "4"))}

    circuit = build_circuit(netlist, NO_MODELS, ["R3"], overrides=overrides)

    assert circuit.lines == ("R3 n_q2_s ladder_vout_s 0.1",)
    assert set(circuit.nodes) == {"Net-(Q2-S)", "/Ladder/VOUT_S"}


@pytest.mark.parametrize("kind", ["resistor", "capacitor", "inductor", "short"])
@pytest.mark.parametrize("ports", [("1",), ("1", "2", "3")])
def test_an_element_with_two_terminals_takes_two_pins(
    netlist: Netlist, kind: str, ports: tuple[str, ...]
) -> None:
    overrides = {"R3": PartModel(kind, ports=ports)}

    with pytest.raises(
        ModelError, match=f"R3: a {kind} is between two pins, and its model names {len(ports)}"
    ):
        build_circuit(netlist, NO_MODELS, ["R3"], overrides=overrides)


def test_a_four_terminal_resistor_keeps_its_sense_pads_apart_from_its_ends(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["R3"])

    # Force, sense, sense, force: the current flows between the outer pads,
    # and each sense pad hangs on the end beside it.
    assert circuit.lines == (
        "R3 n_q2_s ladder_vout_s 0.1",
        "RR3_SA n_q2_s n_u1_p 0.001",
        "RR3_SB ladder_vout_s n_u1_n 0.001",
    )
    assert circuit.origins == ()


@pytest.mark.parametrize("ports", [(), ("1", "4"), ("1", "2", "3"), ("1", "2", "3", "4", "4")])
def test_a_four_terminal_resistor_needs_four_pins(netlist: Netlist, ports: tuple[str, ...]) -> None:
    overrides = {"R3": PartModel("kelvin", ports=ports)}

    with pytest.raises(ModelError, match="R3: a kelvin model needs four ports"):
        build_circuit(netlist, NO_MODELS, ["R3"], overrides=overrides)


def test_a_link_is_a_branch_of_a_milliohm(netlist: Netlist, models: ModelMap) -> None:
    by_default = build_circuit(netlist, models, ["JP1"])
    by_name = build_circuit(
        netlist, models, ["JP1"], overrides={"JP1": PartModel("short", ports=("B", "A"))}
    )

    assert by_default.lines == ("RJP1 n_l1_pad2 p12v_a 0.001",)
    assert by_name.lines == ("RJP1 p12v_a n_l1_pad2 0.001",)


def test_a_resistor_network_is_one_resistor_per_pair_of_pins() -> None:
    schematic = one_part(
        "RN9",
        "4.7k",
        ("1", "a1"),
        ("2", "a2"),
        ("3", "a3"),
        ("4", "a4"),
        ("5", "b4"),
        ("6", "b3"),
        ("7", "b2"),
        ("8", "b1"),
    )

    circuit = build_circuit(schematic, NO_MODELS, ["RN9"])

    assert circuit.lines == (
        "RRN9_1 a1 b1 4700",
        "RRN9_2 a2 b2 4700",
        "RRN9_3 a3 b3 4700",
        "RRN9_4 a4 b4 4700",
    )


def test_a_resistor_of_a_network_that_is_not_drawn_is_left_out() -> None:
    # Only the first and the third resistor of the package are on the schematic.
    schematic = one_part("RN9", "4.7k", ("1", "a1"), ("3", "a3"), ("6", "b3"), ("8", "b1"))
    half = one_part("RN9", "4.7k", ("1", "a1"), ("2", "a2"), ("8", "b1"))

    assert build_circuit(schematic, NO_MODELS, ["RN9"]).lines == (
        "RRN9_1 a1 b1 4700",
        "RRN9_3 a3 b3 4700",
    )
    assert build_circuit(half, NO_MODELS, ["RN9"]).lines == ("RRN9_1 a1 b1 4700",)


def test_a_resistor_of_a_network_that_the_schematic_leaves_open_is_left_out(
    netlist: Netlist, models: ModelMap
) -> None:
    # KiCad gives each pin of the unused fourth resistor a net of its own. A
    # resistor between two such nets would float, and the simulator would
    # stop at the singular matrix.
    circuit = build_circuit(netlist, models, ["RN1"])

    assert circuit.lines == (
        "RRN1_1 chain_cmd_a 0 10000",
        "RRN1_2 chain_cmd_b 0 10000",
        "RRN1_3 n_rn1_r3_1 0 10000",
    )
    assert "unconnected-(RN1-R4.1-Pad4)" not in circuit.nodes


def test_a_resistor_of_a_network_with_one_end_open_stays_in_the_circuit() -> None:
    schematic = one_part(
        "RN9", "4.7k", ("1", "a1"), ("8", "unconnected-(RN9-R1.2-Pad8)"), ("2", "a2"), ("7", "b2")
    )

    assert build_circuit(schematic, NO_MODELS, ["RN9"]).lines == (
        "RRN9_1 a1 nc_rn9_r1_2_pad8 4700",
        "RRN9_2 a2 b2 4700",
    )


def test_a_transistor_is_a_device_with_its_pins_in_the_order_of_spice(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["Q1", "Q2"])

    assert circuit.lines == (
        "MQ1 ladder_supply n_q1_g n_q1_s IRLML0030",
        "MQ2 ladder_supply ladder_gate_r2 n_q2_s IRLML0030",
    )
    assert circuit.libraries == ("mosfets.lib",)
    assert circuit.origins == (
        ("Q1", "IRLML0030", "written here"),
        ("Q2", "IRLML0030", "written here"),
    )


def test_a_package_with_several_units_gives_one_element_per_unit(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["D1", "U2"])

    assert circuit.lines == (
        "DD1_1 0 n_u1_p BAV199",
        "DD1_2 n_u1_p p3v3_a BAV199",
        "XU2_1 chain_cmd_a ladder_gate_r1 p12v_a 0 TC4427CH",
        "XU2_2 chain_cmd_b ladder_gate_r2 p12v_a 0 TC4427CH",
    )
    assert circuit.libraries == ("diodes.lib", "logic.lib")
    # The package is named once, whatever the number of its units.
    assert circuit.origins == (("D1", "BAV199", "written here"), ("U2", "TC4427CH", "written here"))
    # The two pins that the package leaves open are not in the circuit.
    assert not any(net.startswith("unconnected") for net in circuit.nodes)


def test_the_units_of_a_model_win_over_its_ports(netlist: Netlist, models: ModelMap) -> None:
    both = PartModel("subckt", name="HALF", ports=("1", "2"), units=(("2", "7"), ("4", "5")))

    circuit = build_circuit(netlist, models, ["U2"], overrides={"U2": both})

    assert circuit.lines == (
        "XU2_1 chain_cmd_a ladder_gate_r1 HALF",
        "XU2_2 chain_cmd_b ladder_gate_r2 HALF",
    )


def test_a_subcircuit_takes_its_pins_by_number_or_by_name(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["U1"])

    assert circuit.lines == ("XU1 n_u1_p n_u1_n p12v_a m4v_a chain_amp_out OPA365",)
    assert circuit.libraries == ("opamps.lib",)
    assert circuit.origins == (("U1", "OPA365", "written here"),)


def test_the_vendor_tier_takes_the_model_of_the_manufacturer(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["U1", "Q1"], tier="vendor")

    assert circuit.lines == (
        "MQ1 ladder_supply n_q1_g n_q1_s IRLML0030",
        "XU1 n_u1_p n_u1_n p12v_a m4v_a chain_amp_out OPA365_TI",
    )
    assert circuit.libraries == ("mosfets.lib", "vendor/ti-opa365.lib")
    assert circuit.origins == (("Q1", "IRLML0030", "written here"), ("U1", "OPA365_TI", "vendor"))


@pytest.mark.parametrize(
    "model",
    [
        PartModel("subckt", ports=("3", "4", "1")),
        PartModel("subckt", name="OPA"),
        PartModel("subckt"),
        PartModel("device", letter="Q", ports=("3", "4", "1")),
        PartModel("device", name="NPN", letter="Q"),
    ],
)
def test_a_model_needs_a_name_and_its_ports(netlist: Netlist, model: PartModel) -> None:
    with pytest.raises(ModelError, match=f"U1: a {model.kind} model needs a name and its ports"):
        build_circuit(netlist, NO_MODELS, ["U1"], overrides={"U1": model})


def test_a_device_needs_the_letter_of_its_element(netlist: Netlist) -> None:
    model = PartModel("device", name="NMOS", ports=("3", "1", "2"))

    with pytest.raises(ModelError, match="Q1: a device model needs the letter of its element"):
        build_circuit(netlist, NO_MODELS, ["Q1"], overrides={"Q1": model})


@pytest.mark.parametrize(
    ("ref", "model", "message"),
    [
        (
            "U1",
            PartModel("subckt", name="OPA", ports=("3", "9")),
            "U1: the model OPA asks U1 has no pin '9'",
        ),
        (
            "R1",
            PartModel("resistor", ports=("A", "B")),
            "R1: the model resistor asks R1 has no pin 'A'",
        ),
        ("TP1", PartModel("short"), "TP1: the model short asks TP1 has no pin '2'"),
        (
            "U2",
            PartModel("subckt", name="DRV", units=(("2", "7"), ("NC", "3"))),
            "U2: the model DRV asks U2: pins named 'NC' are on different nets",
        ),
        (
            "R3",
            PartModel("kelvin", ports=("1", "2", "3", "5")),
            "R3: the model kelvin asks R3 has no pin '5'",
        ),
    ],
)
def test_a_model_that_asks_for_a_pin_the_part_does_not_have_is_an_error(
    netlist: Netlist, ref: str, model: PartModel, message: str
) -> None:
    with pytest.raises(ModelError, match=message):
        build_circuit(netlist, NO_MODELS, [ref], overrides={ref: model})


def test_a_kind_that_the_builder_does_not_know_is_an_error(netlist: Netlist) -> None:
    with pytest.raises(ModelError, match="R1: unknown model kind 'transformer'"):
        build_circuit(netlist, NO_MODELS, ["R1"], overrides={"R1": PartModel("transformer")})


def test_parts_that_are_nothing_in_spice_leave_no_trace(netlist: Netlist, models: ModelMap) -> None:
    circuit = build_circuit(netlist, models, ["TP1", "H1", "FID1"])
    skipped = build_circuit(
        netlist, models, ["U1", "R1"], overrides={"U1": PartModel("skip", library="opamps.lib")}
    )

    assert circuit == Circuit(lines=(), libraries=(), nodes={}, ports=(), origins=())
    assert circuit.text() == "\n"
    assert skipped.lines == ("R1 ladder_supply ladder_vout_s 1000",)
    assert skipped.libraries == ()
    assert "/Chain/AMP_OUT" not in skipped.nodes


def test_an_override_takes_the_place_of_the_model_map(netlist: Netlist, models: ModelMap) -> None:
    ideal = PartModel("subckt", name="IDEAL_OPAMP", ports=("3", "4", "1"), origin="ideal")

    circuit = build_circuit(netlist, models, ["U1", "Q1"], overrides={"U1": ideal}, tier="vendor")

    assert circuit.lines == (
        "MQ1 ladder_supply n_q1_g n_q1_s IRLML0030",
        "XU1 n_u1_p n_u1_n chain_amp_out IDEAL_OPAMP",
    )
    assert circuit.libraries == ("mosfets.lib",)
    assert circuit.origins == (("Q1", "IRLML0030", "written here"), ("U1", "IDEAL_OPAMP", "ideal"))


def test_a_model_file_is_named_once_in_the_order_of_first_use(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["U2", "U1", "Q2", "Q1", "D1", "R1"])

    assert circuit.libraries == ("diodes.lib", "mosfets.lib", "opamps.lib", "logic.lib")
    assert [ref for ref, _, _ in circuit.origins] == ["D1", "Q1", "Q2", "U1", "U2"]


def test_a_circuit_knows_the_node_of_every_net_it_touches(
    netlist: Netlist, models: ModelMap
) -> None:
    aliases = {"/Ladder/SUPPLY": "supply", "/Ladder/VOUT_S": "vout_s", "/Chain/AMP_OUT": "unused"}

    circuit = build_circuit(netlist, models, ["R1", "R2", "C1", "Q1"], aliases)

    assert circuit.nodes == {
        "/Ladder/SUPPLY": "supply",
        "/Ladder/VOUT_S": "vout_s",
        "GND": "0",
        "Net-(Q1-S)": "n_q1_s",
        "Net-(Q1-G)": "n_q1_g",
    }
    assert circuit.lines[0] == "C1 supply 0 1e-07"
    assert circuit.node("/Ladder/SUPPLY") == "supply"
    assert circuit.node("GND") == "0"
    with pytest.raises(NetlistError, match="the circuit does not touch the net '/Chain/AMP_OUT'"):
        circuit.node("/Chain/AMP_OUT")


def test_the_ports_are_the_nets_that_go_on_outside_the_circuit(
    netlist: Netlist, models: ModelMap
) -> None:
    circuit = build_circuit(netlist, models, ["R1", "R2", "Q1", "C1"])
    with_test_point = build_circuit(
        netlist, models, ["R1", "R2", "R3", "C2", "TP1", "J1"], overrides={"J1": PartModel("skip")}
    )

    # The source of Q1 ends on R2 and ground is no port; the other nets go on
    # to the second range, the output capacitor and the gate resistor.
    assert circuit.ports == ("/Ladder/SUPPLY", "/Ladder/VOUT_S", "Net-(Q1-G)")
    # A part that is nothing in SPICE still counts as inside when it is named.
    assert "/Ladder/VOUT_S" not in with_test_point.ports
    assert with_test_point.ports == (
        "/Ladder/SUPPLY",
        "Net-(Q1-S)",
        "Net-(Q2-S)",
        "Net-(U1-+)",
        "Net-(U1--)",
    )


def test_two_nets_that_end_on_one_node_are_an_error(netlist: Netlist, models: ModelMap) -> None:
    aliases = {"/Ladder/SUPPLY": "node", "/Ladder/VOUT_S": "node"}

    with pytest.raises(
        NetlistError,
        match="the nets '/Ladder/SUPPLY' and '/Ladder/VOUT_S' both become the node 'node'",
    ):
        build_circuit(netlist, models, ["R1"], aliases)
    with pytest.raises(
        NetlistError, match="the nets '/Ladder/SUPPLY' and 'GND' both become the node '0'"
    ):
        build_circuit(netlist, models, ["C1", "C2"], {"/Ladder/SUPPLY": "0"})


def test_the_model_map_is_read_from_a_file(models: ModelMap) -> None:
    assert list(models.by_part) == [
        "IRLML0030TRPBF",
        "BAV199-7-F",
        "OPA365AIDBVR",
        "TC4427EOA713",
    ]
    assert list(models.by_ref) == ["R3", "JP1"]
    assert list(models.vendor) == ["OPA365AIDBVR"]
    assert models.by_part["IRLML0030TRPBF"] == PartModel(
        kind="device",
        name="IRLML0030",
        ports=("3", "1", "2"),
        letter="M",
        library="mosfets.lib",
        origin="written here",
    )
    assert models.by_part["TC4427EOA713"].units == (("2", "7", "6", "3"), ("4", "5", "6", "3"))
    assert models.by_ref["JP1"] == PartModel(kind="short")
    assert models.vendor["OPA365AIDBVR"].origin == "vendor"


def test_the_model_map_can_be_a_folder_of_files_read_together(tmp_path: Path) -> None:
    write_map(
        tmp_path,
        '[part."BC847B"]\nkind = "device"\nletter = "Q"\nname = "BC847B"\nports = [1, 2, 3]\n',
        "b.toml",
    )
    write_map(
        tmp_path,
        '[ref.R7]\nkind = "kelvin"\nports = ["1", "2", "3", "4"]\nparams = "tc1=1e-5"\n',
        "a.toml",
    )
    write_map(
        tmp_path,
        '[vendor."BC847B"]\nkind = "subckt"\nname = "BC847B_NXP"\n'
        'ports = ["1", "2", "3"]\norigin = "vendor"\n',
        "c.toml",
    )
    write_map(tmp_path, ".model BC847B NPN\n", "transistors.lib")
    (tmp_path / "vendor").mkdir()
    write_map(tmp_path / "vendor", "[this is not a model map\n", "skipped.toml")

    models = load_model_map(tmp_path)

    assert models.by_ref == {
        "R7": PartModel("kelvin", ports=("1", "2", "3", "4"), params="tc1=1e-5")
    }
    # Pin numbers written as numbers are read as the text they stand for.
    assert models.by_part == {
        "BC847B": PartModel("device", name="BC847B", ports=("1", "2", "3"), letter="Q")
    }
    assert models.vendor["BC847B"].name == "BC847B_NXP"


def test_a_folder_without_a_model_map_is_refused(tmp_path: Path) -> None:
    write_map(tmp_path, ".model BC847B NPN\n", "transistors.lib")

    with pytest.raises(ModelError, match="holds no model map"):
        load_model_map(tmp_path)


def test_a_model_map_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match=r"cannot read the model map .*missing\.toml"):
        load_model_map(tmp_path / "missing.toml")


def test_a_model_map_that_is_not_toml_is_refused(tmp_path: Path) -> None:
    path = write_map(tmp_path, "[part\n")

    with pytest.raises(ModelError, match=r"the model map .*models\.toml is not valid TOML"):
        load_model_map(path)


def test_a_model_map_in_another_encoding_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_bytes('# 10 µA range\n[ref.R1]\nkind = "resistor"\n'.encode("latin-1"))

    with pytest.raises(ModelError, match=r"the model map .*models\.toml is not valid TOML"):
        load_model_map(path)


def test_a_table_that_the_model_map_does_not_have_is_refused(tmp_path: Path) -> None:
    path = write_map(tmp_path, '[parts.X]\nkind = "skip"\n[refs.R1]\nkind = "skip"\n')

    with pytest.raises(ModelError, match=r"has unknown tables \['parts', 'refs'\]"):
        load_model_map(path)


def test_a_part_that_two_files_give_a_model_is_refused(tmp_path: Path) -> None:
    write_map(tmp_path, '[part.A]\nkind = "skip"\n[part.B]\nkind = "skip"\n', "first.toml")
    write_map(tmp_path, '[vendor.A]\nkind = "skip"\n[ref.B]\nkind = "skip"\n', "second.toml")

    # The same name in another table is another thing ...
    assert set(load_model_map(tmp_path).by_part) == {"A", "B"}

    write_map(tmp_path, '[part.B]\nkind = "short"\n[part.A]\nkind = "short"\n', "third.toml")

    # ... and in the same table it is a part with two models.
    with pytest.raises(ModelError, match=r"the model map .*third.toml repeats part A, B"):
        load_model_map(tmp_path)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("part = 5\n", r"the model map table \[part\] is not a table"),
        ('ref = ["R1"]\n', r"the model map table \[ref\] is not a table"),
        ('[part]\nX = "subckt"\n', "model map, part 'X': an entry needs at least a kind"),
        ('[ref.R1]\nname = "OPA"\n', "model map, ref 'R1': an entry needs at least a kind"),
        (
            '[vendor.X]\nkind = "subckt"\nport = ["1"]\nfile = "x.lib"\n',
            r"model map, vendor 'X': unknown keys \['file', 'port'\]",
        ),
        ('[part.X]\nkind = "transformer"\n', "model map, part 'X': unknown kind 'transformer'"),
        (
            '[part.X]\nkind = "subckt"\norigin = "guessed"\n',
            "model map, part 'X': unknown origin 'guessed'",
        ),
    ],
)
def test_a_malformed_entry_is_named(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ModelError, match=message):
        load_model_map(write_map(tmp_path, text))


@pytest.mark.parametrize(
    "pins",
    ['ports = "12"', "ports = 12", "units = 2", 'units = ["1", "2"]', 'units = [["1", "2"], "34"]'],
)
def test_the_pins_of_an_entry_must_be_lists(tmp_path: Path, pins: str) -> None:
    path = write_map(tmp_path, f'[part.X]\nkind = "subckt"\nname = "X"\n{pins}\n')

    with pytest.raises(
        ModelError,
        match="model map, part 'X': ports is a list of pins and units a list of such lists",
    ):
        load_model_map(path)


def test_an_entry_may_leave_out_everything_but_its_kind(tmp_path: Path) -> None:
    models = load_model_map(write_map(tmp_path, '[ref.TP9]\nkind = "skip"\n'))

    assert models.by_ref == {"TP9": PartModel(kind="skip")}
    assert PartModel(kind="skip") == PartModel("skip", "", (), (), "", "", "", "")


def test_a_schematic_read_from_a_snapshot_builds_the_same_circuit(
    snapshot: dict[str, Any], netlist: Netlist, models: ModelMap
) -> None:
    refs = [ref for ref in netlist.components if ref != "J1"]

    again = build_circuit(netlist_from_snapshot(snapshot), models, refs)

    assert again == build_circuit(netlist, models, refs)
    assert len(again.lines) == 21
