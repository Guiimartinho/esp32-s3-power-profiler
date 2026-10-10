from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from circuit_sim.errors import NetlistError
from circuit_sim.netlist import (
    SNAPSHOT_FORMAT,
    Component,
    Netlist,
    Pin,
    dump_snapshot,
    load_snapshot,
    natural_key,
    netlist_from_snapshot,
    snapshot_from_kicad_xml,
)

CARRIER = Path(__file__).resolve().parents[1] / "netlist" / "carrier.json"

# A netlist as KiCad 10 exports it, cut down to what the snapshot reads and a
# little of what it does not. KiCad appends the pin number to every pin name.
EXPORT = r"""<?xml version="1.0" encoding="UTF-8"?>
<export version="E">
  <design>
    <source>C:\work\board\front-end.kicad_sch</source>
    <date>2026-10-10T12:25:54</date>
    <tool>Eeschema 10.0.0</tool>
    <sheet number="1" name="/" tstamps="/">
      <title_block>
        <title>Small Front End</title>
        <company/>
        <rev>T1</rev>
        <date>2026-10-09</date>
        <source>front-end.kicad_sch</source>
      </title_block>
    </sheet>
    <sheet number="2" name="/Ladder/" tstamps="/19103e86/">
      <title_block>
        <title>Shunt ladder</title>
        <rev>T0</rev>
      </title_block>
    </sheet>
  </design>
  <components>
    <comp ref="R10">
      <value>1k 0.1% 25ppm</value>
      <footprint>Resistor_SMD:R_0603_1608Metric</footprint>
      <fields>
        <field name="Manufacturer">Yageo</field>
        <field name="MPN">RT0603BRD071KL</field>
        <field name="Datasheet"/>
      </fields>
      <libsource lib="Device" part="R" description="Resistor"/>
      <property name="Sheetname" value="Ladder"/>
      <sheetpath names="/Ladder/" tstamps="/19103e86/"/>
      <tstamps>fece0c02</tstamps>
    </comp>
    <comp ref="U1">
      <value>OPA365AIDBV</value>
      <fields>
        <field name="MPN">OPA365AIDBVR</field>
      </fields>
      <sheetpath names="/Chain/" tstamps="/2f/"/>
    </comp>
    <comp ref="R2">
      <value>33R 1%</value>
      <fields>
        <field name="MPN"/>
      </fields>
      <sheetpath names="/Ladder/" tstamps="/19103e86/"/>
    </comp>
    <comp ref="J1">
      <value>Conn_01x10</value>
      <sheetpath names="/Chain/" tstamps="/2f/"/>
    </comp>
    <comp ref="FID1">
      <value/>
    </comp>
  </components>
  <libparts>
    <libpart lib="Device" part="R">
      <fields>
        <field name="Reference">R</field>
      </fields>
    </libpart>
  </libparts>
  <nets>
    <net code="1" name="/Ladder/SUPPLY" class="Default">
      <node ref="U1" pin="3" pinfunction="+_3" pintype="input"/>
      <node ref="R10" pin="1" pintype="passive"/>
      <node ref="J1" pin="10" pinfunction="Pin_10_10" pintype="passive"/>
    </net>
    <net code="2" name="GND" class="Default">
      <node ref="R2" pin="2" pintype="passive"/>
      <node ref="U1" pin="2" pinfunction="V-_2" pintype="power_in"/>
      <node ref="J1" pin="2" pinfunction="Pin_2_2" pintype="passive"/>
      <node ref="J1" pin="A1" pinfunction="SHIELD" pintype="passive"/>
    </net>
    <net code="3" name="Net-(U1--)" class="Default">
      <node ref="R10" pin="2" pintype="passive"/>
      <node ref="R2" pin="1" pintype="passive"/>
      <node ref="U1" pin="4" pinfunction="-_4" pintype="input"/>
      <node ref="U1" pin="1" pintype="output"/>
      <node ref="J1" pin="1" pinfunction="Pin_1_1" pintype="passive"/>
    </net>
  </nets>
</export>
"""


def part(ref: str, *pins: tuple[str, str, str]) -> Component:
    """A part with its pins as (number, name, net)."""
    return Component(
        ref, "1k", "", "/Ladder/", tuple(Pin(number, net, name) for number, name, net in pins)
    )


def test_a_part_knows_the_letters_of_its_designator() -> None:
    assert part("R107").prefix == "R"
    assert part("RN5").prefix == "RN"
    assert part("FID1").prefix == "FID"
    # A designator that is not letters and a number is taken whole.
    assert part("U14A").prefix == "U14A"
    assert part("#PWR01").prefix == "#PWR01"


def test_the_net_of_a_pin_is_found_by_number_and_then_by_name() -> None:
    switch = part("Q1", ("1", "G", "gate"), ("2", "S", "source"), ("3", "D", "drain"))
    # Pin 2 is named "1": the number wins over the name.
    odd = part("X1", ("1", "A", "first"), ("2", "1", "second"))

    assert switch.net_of("3") == "drain"
    assert switch.net_of("G") == "gate"
    assert odd.net_of("1") == "first"


def test_a_name_that_several_pins_share_gives_their_net_when_it_is_one_net() -> None:
    regulator = part("U3", ("1", "IN", "vin"), ("2", "GND", "ground"), ("5", "GND", "ground"))

    assert regulator.net_of("GND") == "ground"


def test_a_pin_that_the_part_does_not_have_is_an_error() -> None:
    switch = part("Q1", ("1", "G", "gate"))

    with pytest.raises(NetlistError, match="Q1 has no pin 'B'"):
        switch.net_of("B")


def test_a_name_on_pins_of_different_nets_is_an_error() -> None:
    connector = part("J5", ("1", "Pin", "first"), ("2", "Pin", "second"))

    with pytest.raises(NetlistError, match="J5: pins named 'Pin' are on different nets"):
        connector.net_of("Pin")


def test_designators_sort_by_their_number_not_by_their_text() -> None:
    refs = ["R10", "R2", "C3", "RN1", "R1", "U14A", "TP1", "#PWR01", "C12"]

    assert sorted(refs, key=natural_key) == [
        "#PWR01",
        "C3",
        "C12",
        "R1",
        "R2",
        "R10",
        "RN1",
        "TP1",
        "U14A",
    ]


def test_a_netlist_finds_a_part_by_its_designator(netlist: Netlist) -> None:
    assert netlist.component("R3").value == "0.1R 0.25% 50ppm"
    assert netlist.component("R3").mpn == "LVK12R100CER"

    with pytest.raises(NetlistError, match="the schematic has no part R99"):
        netlist.component("R99")


def test_a_netlist_lists_the_parts_of_a_sheet_in_natural_order(netlist: Netlist) -> None:
    assert netlist.on_sheet("/Ladder/") == (
        "C1",
        "C2",
        "D1",
        "J1",
        "Q1",
        "Q2",
        "R1",
        "R2",
        "R3",
        "R4",
        "TP1",
    )
    assert netlist.on_sheet("/Chain/") == ("C3", "JP1", "L1", "RN1", "U1", "U2")
    assert netlist.on_sheet("/Nowhere/") == ()


def test_a_netlist_gives_every_net_with_its_pins(netlist: Netlist) -> None:
    nets = netlist.nets()

    assert list(nets) == sorted(nets)
    assert nets["/Ladder/SUPPLY"] == (("C1", "1"), ("Q1", "3"), ("Q2", "3"), ("R1", "1"))
    assert nets["Net-(U1--)"] == (("R3", "3"), ("U1", "4"))
    assert nets["unconnected-(U2-NC-Pad1)"] == (("U2", "1"),)
    assert sum(len(pins) for pins in nets.values()) == sum(
        len(component.pins) for component in netlist.components.values()
    )


def test_a_snapshot_holds_the_parts_of_an_export_in_natural_order() -> None:
    document = snapshot_from_kicad_xml(EXPORT)

    assert document["format"] == SNAPSHOT_FORMAT
    assert document["title"] == "Small Front End"
    assert document["revision"] == "T1"
    assert [entry["ref"] for entry in document["components"]] == ["FID1", "J1", "R2", "R10", "U1"]
    assert document["components"][3] == {
        "ref": "R10",
        "value": "1k 0.1% 25ppm",
        "mpn": "RT0603BRD071KL",
        "sheet": "/Ladder/",
        "pins": [
            {"pin": "1", "net": "/Ladder/SUPPLY", "function": ""},
            {"pin": "2", "net": "Net-(U1--)", "function": ""},
        ],
    }


def test_a_snapshot_takes_the_pin_names_without_the_pin_numbers_that_kicad_appends() -> None:
    parts = {entry["ref"]: entry for entry in snapshot_from_kicad_xml(EXPORT)["components"]}

    assert [(pin["pin"], pin["function"]) for pin in parts["U1"]["pins"]] == [
        ("1", ""),
        ("2", "V-"),
        ("3", "+"),
        ("4", "-"),
    ]
    # Pins sort by their number, and a name without the appended number stays.
    assert [(pin["pin"], pin["function"]) for pin in parts["J1"]["pins"]] == [
        ("1", "Pin_1"),
        ("2", "Pin_2"),
        ("10", "Pin_10"),
        ("A1", "SHIELD"),
    ]


def test_a_snapshot_fills_in_what_an_export_leaves_out() -> None:
    parts = {entry["ref"]: entry for entry in snapshot_from_kicad_xml(EXPORT)["components"]}

    assert parts["FID1"] == {"ref": "FID1", "value": "", "mpn": "", "sheet": "", "pins": []}
    assert parts["R2"]["mpn"] == ""
    assert parts["J1"]["mpn"] == ""


def test_a_snapshot_holds_nothing_that_changes_between_two_exports() -> None:
    # The same schematic exported on another machine on another day, with
    # the nets and their pins in another order.
    again = EXPORT.replace(r"C:\work\board", "/home/someone/board").replace(
        "2026-10-10T12:25:54", "2027-01-02T03:04:05"
    )
    supply = again[again.index('    <net code="1"') : again.index('    <net code="2"')]
    again = again.replace(supply, "").replace("  </nets>", supply + "  </nets>")
    first = '      <node ref="R10" pin="2" pintype="passive"/>\n'
    second = '      <node ref="R2" pin="1" pintype="passive"/>\n'
    again = again.replace(first + second, second + first)

    document = snapshot_from_kicad_xml(EXPORT)

    assert again != EXPORT
    assert snapshot_from_kicad_xml(again) == document
    assert dump_snapshot(snapshot_from_kicad_xml(again)) == dump_snapshot(document)
    text = dump_snapshot(document)
    assert "work" not in text
    assert "2026" not in text


def test_an_export_without_a_title_block_gives_an_empty_title() -> None:
    bare = EXPORT[: EXPORT.index("  <design>")] + EXPORT[EXPORT.index("  <components>") :]
    empty = EXPORT.replace("<title>Small Front End</title>", "<title/>").replace(
        "<rev>T1</rev>", ""
    )

    assert (snapshot_from_kicad_xml(bare)["title"], snapshot_from_kicad_xml(bare)["revision"]) == (
        "",
        "",
    )
    assert (
        snapshot_from_kicad_xml(empty)["title"],
        snapshot_from_kicad_xml(empty)["revision"],
    ) == (
        "",
        "",
    )


def test_a_file_that_is_not_xml_is_refused() -> None:
    with pytest.raises(NetlistError, match="the netlist export is not XML"):
        snapshot_from_kicad_xml("(export (version E))")


@pytest.mark.parametrize(
    "text",
    [
        "<netlist><components/><nets/></netlist>",
        "<export><nets/></export>",
        "<export><components/></export>",
    ],
)
def test_a_file_that_is_not_a_netlist_export_is_refused(text: str) -> None:
    with pytest.raises(NetlistError, match="the file is not a KiCad netlist export"):
        snapshot_from_kicad_xml(text)


def test_a_snapshot_gives_the_netlist_back() -> None:
    netlist = netlist_from_snapshot(snapshot_from_kicad_xml(EXPORT))

    assert (netlist.title, netlist.revision) == ("Small Front End", "T1")
    assert list(netlist.components) == ["FID1", "J1", "R2", "R10", "U1"]
    assert netlist.component("U1") == Component(
        ref="U1",
        value="OPA365AIDBV",
        mpn="OPA365AIDBVR",
        sheet="/Chain/",
        pins=(
            Pin("1", "Net-(U1--)", ""),
            Pin("2", "GND", "V-"),
            Pin("3", "/Ladder/SUPPLY", "+"),
            Pin("4", "Net-(U1--)", "-"),
        ),
    )
    assert netlist.component("U1").net_of("+") == "/Ladder/SUPPLY"


def test_a_snapshot_without_title_and_revision_is_read(snapshot: dict[str, Any]) -> None:
    del snapshot["title"]
    del snapshot["revision"]

    netlist = netlist_from_snapshot(snapshot)

    assert (netlist.title, netlist.revision) == ("", "")
    assert len(netlist.components) == 19


@pytest.mark.parametrize("version", [0, 2, "1", None])
def test_a_snapshot_of_another_format_is_refused(snapshot: dict[str, Any], version: object) -> None:
    snapshot["format"] = version

    with pytest.raises(NetlistError, match="not a netlist snapshot of a format this package reads"):
        netlist_from_snapshot(snapshot)


def test_a_document_without_parts_is_refused(snapshot: dict[str, Any]) -> None:
    del snapshot["components"]

    with pytest.raises(NetlistError, match="not a netlist snapshot of a format this package reads"):
        netlist_from_snapshot(snapshot)
    with pytest.raises(NetlistError, match="not a netlist snapshot"):
        netlist_from_snapshot({})


@pytest.mark.parametrize("key", ["ref", "value", "mpn", "sheet", "pins"])
def test_a_part_with_a_missing_field_is_refused(snapshot: dict[str, Any], key: str) -> None:
    del snapshot["components"][4][key]

    with pytest.raises(
        NetlistError, match=f"the netlist snapshot is malformed: KeyError\\('{key}'"
    ):
        netlist_from_snapshot(snapshot)


@pytest.mark.parametrize("key", ["pin", "net", "function"])
def test_a_pin_with_a_missing_field_is_refused(snapshot: dict[str, Any], key: str) -> None:
    del snapshot["components"][0]["pins"][1][key]

    with pytest.raises(
        NetlistError, match=f"the netlist snapshot is malformed: KeyError\\('{key}'"
    ):
        netlist_from_snapshot(snapshot)


@pytest.mark.parametrize("components", [7, ["R1"], [{"ref": "R1", "pins": 3}], [None]])
def test_parts_of_the_wrong_kind_are_refused(snapshot: dict[str, Any], components: object) -> None:
    broken = copy.deepcopy(snapshot)
    broken["components"] = components
    if isinstance(components, list) and isinstance(components[0], dict):
        broken["components"] = [{**snapshot["components"][0], **components[0]}]

    with pytest.raises(NetlistError, match="the netlist snapshot is malformed"):
        netlist_from_snapshot(broken)


def test_a_snapshot_is_stored_as_stable_text(snapshot: dict[str, Any]) -> None:
    snapshot["title"] = "Front end, 10 \u00b5A to 1 A"
    text = dump_snapshot(snapshot)
    shuffled = {key: snapshot[key] for key in reversed(list(snapshot))}

    assert text.endswith("\n}\n")
    assert json.loads(text) == snapshot
    assert dump_snapshot(shuffled) == text
    assert text.splitlines()[:2] == ["{", ' "components": [']
    # Text outside ASCII is kept readable, not escaped.
    assert ' "title": "Front end, 10 \u00b5A to 1 A"' in text


def test_a_snapshot_is_read_from_its_file(tmp_path: Path, snapshot: dict[str, Any]) -> None:
    path = tmp_path / "carrier.json"
    path.write_text(dump_snapshot(snapshot), encoding="utf-8", newline="\n")

    netlist = load_snapshot(path)

    assert netlist == netlist_from_snapshot(snapshot)
    assert netlist.title == "Small Front End"


def test_a_snapshot_file_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NetlistError, match=r"cannot read the netlist snapshot .*missing\.json"):
        load_snapshot(tmp_path / "missing.json")


def test_a_snapshot_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "carrier.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(NetlistError, match=r"the netlist snapshot .*carrier\.json is not JSON"):
        load_snapshot(path)


def test_a_snapshot_file_in_another_encoding_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "carrier.json"
    path.write_bytes('{"title": "10 \u00b5A"}'.encode("latin-1"))

    with pytest.raises(NetlistError, match=r"the netlist snapshot .*carrier\.json is not JSON"):
        load_snapshot(path)


@pytest.mark.parametrize("text", ["[]", '"snapshot"', "7", "null"])
def test_a_snapshot_file_that_holds_no_document_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "carrier.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(NetlistError, match=r"carrier\.json is not a snapshot document"):
        load_snapshot(path)


def test_the_snapshot_of_the_carrier_board_loads() -> None:
    netlist = load_snapshot(CARRIER)

    assert netlist.title == "Open Power Profiler - Carrier Board"
    assert len(netlist.components) == 428
    assert list(netlist.components) == sorted(netlist.components, key=natural_key)
    assert all(
        [pin.number for pin in component.pins]
        == sorted((pin.number for pin in component.pins), key=lambda number: (len(number), number))
        for component in netlist.components.values()
    )


def test_the_snapshot_of_the_carrier_board_is_stored_as_the_package_writes_it() -> None:
    text = CARRIER.read_text(encoding="utf-8")

    assert dump_snapshot(json.loads(text)) == text
