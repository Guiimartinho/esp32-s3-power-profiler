"""The netlist of the schematic, as the simulations read it.

The circuits that are simulated are taken from the schematic, not typed
again: KiCad exports the netlist as XML, and :func:`snapshot_from_kicad_xml`
turns that export into a small, sorted document without the machine path
and the time of the export. The snapshot is kept in the repository
(``netlist/carrier.json``); :func:`load_snapshot` turns it into the value
objects below. Comparing the stored snapshot with a new export shows whether
the schematic changed since the simulations ran.
"""

from __future__ import annotations

import json
import pathlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from circuit_sim.errors import NetlistError

SNAPSHOT_FORMAT = 1
"""Version of the snapshot document."""

_REF = re.compile(r"^([A-Za-z]+)(\d+)$")


@dataclass(frozen=True, slots=True)
class Pin:
    """One pin of a part.

    Attributes:
        number: Pin number as the symbol gives it (a string: ``1``, ``A9``, ``SH``).
        net: Name of the net the pin is on.
        function: Pin name of the symbol (``G``, ``OUT``, ``+``), empty for
            a part without pin names.
    """

    number: str
    net: str
    function: str


@dataclass(frozen=True, slots=True)
class Component:
    """One part of the schematic.

    Attributes:
        ref: Reference designator.
        value: Value field as the schematic writes it.
        mpn: Manufacturer part number, empty when the part has none.
        sheet: Name of the sheet the part is drawn on (``/Shunt Ladder/``).
        pins: The connected pins, in the order of their numbers.
    """

    ref: str
    value: str
    mpn: str
    sheet: str
    pins: tuple[Pin, ...]

    @property
    def prefix(self) -> str:
        """The letters of the reference designator (``R``, ``U``, ``FB``)."""
        match = _REF.match(self.ref)
        return match.group(1) if match else self.ref

    def net_of(self, pin: str) -> str:
        """The net of a pin, by pin number or, failing that, by pin name.

        Raises:
            NetlistError: When the part has no such pin, or the name fits
                pins on different nets.
        """
        for candidate in self.pins:
            if candidate.number == pin:
                return candidate.net
        nets = {candidate.net for candidate in self.pins if candidate.function == pin}
        if len(nets) == 1:
            return next(iter(nets))
        if not nets:
            raise NetlistError(f"{self.ref} has no pin {pin!r}")
        raise NetlistError(f"{self.ref}: pins named {pin!r} are on different nets")


@dataclass(frozen=True)
class Netlist:
    """The whole schematic: parts by reference designator.

    Attributes:
        title: Title of the schematic.
        revision: Revision of the schematic.
        components: Every part, by reference designator.
    """

    title: str
    revision: str
    components: Mapping[str, Component]

    def component(self, ref: str) -> Component:
        """One part.

        Raises:
            NetlistError: When the schematic has no part of that designator.
        """
        try:
            return self.components[ref]
        except KeyError:
            raise NetlistError(f"the schematic has no part {ref}") from None

    def on_sheet(self, sheet: str) -> tuple[str, ...]:
        """The designators of the parts drawn on a sheet, in natural order."""
        return tuple(ref for ref, part in self.components.items() if part.sheet == sheet)

    def nets(self) -> dict[str, tuple[tuple[str, str], ...]]:
        """Every net with its pins as (designator, pin number)."""
        found: dict[str, list[tuple[str, str]]] = {}
        for part in self.components.values():
            for pin in part.pins:
                found.setdefault(pin.net, []).append((part.ref, pin.number))
        return {net: tuple(pins) for net, pins in sorted(found.items())}


def natural_key(ref: str) -> tuple[str, int, str]:
    """Sort key that puts R2 before R10."""
    match = _REF.match(ref)
    return (match.group(1), int(match.group(2)), "") if match else (ref, 0, ref)


def _pin_function(raw: str, number: str) -> str:
    """The pin name without the pin number that the export appends to it."""
    suffix = f"_{number}"
    return raw[: -len(suffix)] if raw.endswith(suffix) else raw


def snapshot_from_kicad_xml(text: str) -> dict[str, Any]:
    """The snapshot document of a netlist that KiCad exported as XML.

    The result holds what a simulation needs and nothing that changes from
    one export of the same schematic to the next: no path of the machine, no
    date. Parts and pins are sorted, so that two exports of one schematic
    give the same document.

    Raises:
        NetlistError: When the text is not such an export.
    """
    try:
        # The text is the export of the local KiCad, not foreign data.
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise NetlistError(f"the netlist export is not XML: {error}") from error
    components = root.find("components")
    nets = root.find("nets")
    if root.tag != "export" or components is None or nets is None:
        raise NetlistError("the file is not a KiCad netlist export (no components or nets)")
    pins: dict[str, list[dict[str, str]]] = {}
    for net in nets:
        name = net.get("name", "")
        for node in net:
            number = node.get("pin", "")
            pins.setdefault(node.get("ref", ""), []).append(
                {
                    "pin": number,
                    "net": name,
                    "function": _pin_function(node.get("pinfunction", ""), number),
                }
            )
    parts: list[dict[str, Any]] = []
    for comp in components:
        ref = comp.get("ref", "")
        fields = {field.get("name", ""): (field.text or "") for field in comp.iter("field")}
        sheet = comp.find("sheetpath")
        parts.append(
            {
                "ref": ref,
                "value": comp.findtext("value") or "",
                "mpn": fields.get("MPN", ""),
                "sheet": sheet.get("names", "") if sheet is not None else "",
                "pins": sorted(pins.get(ref, []), key=lambda pin: (len(pin["pin"]), pin["pin"])),
            }
        )
    parts.sort(key=lambda part: natural_key(part["ref"]))
    title_block = root.find("design/sheet/title_block")
    return {
        "format": SNAPSHOT_FORMAT,
        "title": (title_block.findtext("title") or "") if title_block is not None else "",
        "revision": (title_block.findtext("rev") or "") if title_block is not None else "",
        "components": parts,
    }


def netlist_from_snapshot(document: Mapping[str, Any]) -> Netlist:
    """The value objects of a snapshot document.

    Raises:
        NetlistError: When the document is not a snapshot of a known format.
    """
    if document.get("format") != SNAPSHOT_FORMAT or "components" not in document:
        raise NetlistError("the document is not a netlist snapshot of a format this package reads")
    components: dict[str, Component] = {}
    try:
        for part in document["components"]:
            components[part["ref"]] = Component(
                ref=part["ref"],
                value=part["value"],
                mpn=part["mpn"],
                sheet=part["sheet"],
                pins=tuple(
                    Pin(number=pin["pin"], net=pin["net"], function=pin["function"])
                    for pin in part["pins"]
                ),
            )
    except (KeyError, TypeError) as error:
        raise NetlistError(f"the netlist snapshot is malformed: {error!r}") from error
    return Netlist(
        title=str(document.get("title", "")),
        revision=str(document.get("revision", "")),
        components=components,
    )


def load_snapshot(path: pathlib.Path) -> Netlist:
    """Read the snapshot file of the repository.

    Raises:
        NetlistError: When the file is missing or is not a snapshot.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise NetlistError(f"cannot read the netlist snapshot {path}: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise NetlistError(f"the netlist snapshot {path} is not JSON: {error}") from error
    if not isinstance(document, dict):
        raise NetlistError(f"the netlist snapshot {path} is not a snapshot document")
    return netlist_from_snapshot(document)


def dump_snapshot(document: Mapping[str, Any]) -> str:
    """The text of a snapshot document as it is stored: stable and readable."""
    return json.dumps(document, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
