"""SPICE circuits built from the netlist of the schematic.

A bench does not type its circuit: it names the parts of the schematic that
take part, and :func:`build_circuit` writes one SPICE element for each of
them, with the values and the connections of the schematic. What a part is in
SPICE comes from the model map: a resistor is a resistor, an integrated
circuit is a subcircuit of a model library with its pins in the order that
the library wants, a test point is nothing. So the simulated circuit is the
drawn one, and a value changed in the schematic changes the simulation with
the next snapshot.
"""

from __future__ import annotations

import pathlib
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from circuit_sim.errors import ModelError, NetlistError
from circuit_sim.netlist import Component, Netlist
from circuit_sim.values import parse_value

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

GROUND_NETS = frozenset({"GND"})
"""Nets of the schematic that are node 0 of every circuit."""

_KINDS = frozenset(
    {
        "resistor",
        "capacitor",
        "inductor",
        "network",
        "kelvin",
        "subckt",
        "device",
        "short",
        "skip",
    }
)
_ORIGINS = frozenset({"vendor", "written here", "ideal", ""})

# What a part is when the model map says nothing about it, by the letters of
# its reference designator.
_DEFAULT_KIND = {
    "R": "resistor",
    "C": "capacitor",
    "L": "inductor",
    "RN": "network",
    "TP": "skip",
    "FID": "skip",
    "H": "skip",
    "MP": "skip",
    "SH": "skip",
}

# Pin pairs of the resistors of a four-resistor network in a 1206 array.
_NETWORK_PAIRS = (("1", "8"), ("2", "7"), ("3", "6"), ("4", "5"))

_UNCONNECTED = "unconnected-("
"""Start of the net that KiCad gives to a pin that goes nowhere."""

_ZERO_OHM = 1e-3
"""Resistance that stands for a zero-ohm link, so that it stays a branch."""

_SENSE_OHM = 1e-3
"""Resistance between a force pad and the sense pad of the same end."""


@dataclass(frozen=True, slots=True)
class PartModel:
    """What one part of the schematic is in a SPICE circuit.

    Attributes:
        kind: ``resistor``, ``capacitor``, ``inductor``, ``network`` (four
            resistors in one package), ``kelvin`` (a resistor with two force
            and two sense pads), ``subckt``, ``device`` (a diode or
            transistor with a ``.model``), ``short`` or ``skip``.
        name: Name of the subcircuit or of the device model.
        ports: Pins of the schematic part in the order of the SPICE element,
            each by pin number or by pin name. For ``kelvin``: force, sense,
            sense, force.
        units: For a package with several units of one model, the pins of
            each unit, in place of ``ports``.
        letter: First letter of the element for a ``device`` (``D``, ``Q``, ``M``).
        library: Model file to include, relative to the models folder.
        origin: Where the model comes from: ``vendor``, ``written here`` or
            ``ideal``. Reported with every result.
        params: Text appended to the element line.
    """

    kind: str
    name: str = ""
    ports: tuple[str, ...] = ()
    units: tuple[tuple[str, ...], ...] = ()
    letter: str = ""
    library: str = ""
    origin: str = ""
    params: str = ""


@dataclass(frozen=True)
class ModelMap:
    """Which model each part of the schematic takes.

    Attributes:
        by_ref: Models given for single reference designators; they win.
        by_part: Models by manufacturer part number or, failing that, by value.
        vendor: Models of the manufacturers, by part number. They take the
            place of the ones in ``by_part`` in the vendor tier. Their files
            are not part of the repository.
    """

    by_ref: Mapping[str, PartModel] = field(default_factory=dict)
    by_part: Mapping[str, PartModel] = field(default_factory=dict)
    vendor: Mapping[str, PartModel] = field(default_factory=dict)

    def model_of(self, part: Component, tier: str = "open") -> PartModel:
        """The model of a part.

        Args:
            part: The part of the schematic.
            tier: ``vendor`` to take the model of the manufacturer where the
                map names one; anything else for the models of the repository.

        Raises:
            ModelError: When the map has no model for the part and its
                designator has no default.
        """
        if part.ref in self.by_ref:
            return self.by_ref[part.ref]
        if tier == "vendor" and part.mpn in self.vendor:
            return self.vendor[part.mpn]
        if part.mpn in self.by_part:
            return self.by_part[part.mpn]
        if part.value in self.by_part:
            return self.by_part[part.value]
        default = _DEFAULT_KIND.get(part.prefix)
        if default is None:
            raise ModelError(f"{part.ref} ({part.mpn or part.value}) has no model in the model map")
        return PartModel(kind=default, origin="ideal" if default != "skip" else "")


@dataclass(frozen=True)
class Circuit:
    """A piece of the schematic as SPICE lines.

    Attributes:
        lines: One element per line.
        libraries: Model files the elements need, relative to the models folder.
        nodes: The SPICE node of every net the circuit touches.
        ports: Nets that also have pins of parts outside the circuit: the
            places where a bench connects its sources and loads.
        origins: For every part with a model, where the model comes from,
            as (designator, model name, origin).
    """

    lines: tuple[str, ...]
    libraries: tuple[str, ...]
    nodes: Mapping[str, str]
    ports: tuple[str, ...]
    origins: tuple[tuple[str, str, str], ...]

    def node(self, net: str) -> str:
        """The SPICE node of a net of the schematic.

        Raises:
            NetlistError: When the circuit does not touch that net.
        """
        try:
            return self.nodes[net]
        except KeyError:
            raise NetlistError(f"the circuit does not touch the net {net!r}") from None

    def text(self) -> str:
        """The lines as one block of text."""
        return "\n".join(self.lines) + "\n"


def node_name(net: str, aliases: Mapping[str, str] | None = None) -> str:
    """The SPICE node that stands for a net of the schematic.

    Ground is node 0. A net with an alias takes it. Any other net keeps its
    name in lower case with the sheet path, every character that SPICE may
    not like turned into an underscore, and a leading sign spelled out, so
    that ``+12V_A`` and ``-4V_A`` stay apart: ``p12v_a`` and ``m4v_a``.
    """
    if net in GROUND_NETS:
        return "0"
    if aliases and net in aliases:
        return aliases[net]
    text = net.strip("/").lower()
    text = re.sub(r"^\+", "p", text)
    text = re.sub(r"^-(?=\d)", "m", text)
    text = text.replace("net-(", "n_").replace("unconnected-(", "nc_")
    # KiCad names a net after a pin. Two pins whose names differ in a sign at
    # the end must not end on one name: the inputs "+" and "-" of an
    # amplifier, the pins "C+" and "C-" of a charge pump.
    text = re.sub(r"\+\)$", "_p", text)
    text = re.sub(r"-\)$", "_n", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unnamed"


def build_circuit(
    netlist: Netlist,
    models: ModelMap,
    refs: Iterable[str],
    aliases: Mapping[str, str] | None = None,
    overrides: Mapping[str, PartModel] | None = None,
    scales: Mapping[str, float] | None = None,
    *,
    tier: str = "open",
) -> Circuit:
    """Write the SPICE elements of some parts of the schematic.

    Args:
        netlist: The schematic.
        models: The model map.
        refs: Reference designators of the parts that take part.
        aliases: Shorter node names for nets, by net name.
        overrides: Models that replace the model map for single designators
            in this circuit, for example an ideal part in place of a model.
        scales: Factors on the values of single resistors, capacitors and
            inductors, by designator, for tolerance runs.
        tier: ``vendor`` to take the models of the manufacturers where the
            map names them.

    Raises:
        NetlistError: When a designator is not in the schematic, or two nets
            end on one node name.
        ModelError: When a part has no model or its model names a pin that
            the part does not have.
    """
    chosen = sorted(set(refs), key=lambda ref: (len(ref), ref))
    lines: list[str] = []
    libraries: list[str] = []
    origins: list[tuple[str, str, str]] = []
    nodes: dict[str, str] = {}

    def node(net: str) -> str:
        name = node_name(net, aliases)
        for other, used in nodes.items():
            if used == name and other != net:
                raise NetlistError(f"the nets {other!r} and {net!r} both become the node {name!r}")
        nodes[net] = name
        return name

    for ref in chosen:
        part = netlist.component(ref)
        model = (overrides or {}).get(ref) or models.model_of(part, tier)
        if model.kind not in _KINDS:
            raise ModelError(f"{ref}: unknown model kind {model.kind!r}")
        if model.kind == "skip":
            continue
        if model.library and model.library not in libraries:
            libraries.append(model.library)
        if model.kind in ("subckt", "device"):
            origins.append((ref, model.name, model.origin))
        lines.extend(_element(part, model, node, (scales or {}).get(ref, 1.0)))

    inside = set(chosen)
    all_nets = netlist.nets()
    ports = tuple(
        net
        for net in sorted(nodes)
        if net not in GROUND_NETS and any(ref not in inside for ref, _ in all_nets.get(net, ()))
    )
    return Circuit(
        lines=tuple(lines),
        libraries=tuple(libraries),
        nodes=nodes,
        ports=ports,
        origins=tuple(origins),
    )


def _element(
    part: Component, model: PartModel, node: Callable[[str], str], scale: float
) -> list[str]:
    """The SPICE lines of one part."""
    ref = part.ref

    def nodes_of(pins: Iterable[str]) -> list[str]:
        try:
            nets = [part.net_of(pin) for pin in pins]
        except NetlistError as error:
            raise ModelError(f"{ref}: the model {model.name or model.kind} asks {error}") from error
        return [node(net) for net in nets]

    def two_nodes() -> list[str]:
        """The nodes of an element with two terminals: pins 1 and 2 unless the model names two."""
        if model.ports and len(model.ports) != 2:
            raise ModelError(
                f"{ref}: a {model.kind} is between two pins, and its model names {len(model.ports)}"
            )
        return nodes_of(model.ports or ("1", "2"))

    params = f" {model.params}" if model.params else ""
    if model.kind in ("resistor", "capacitor", "inductor"):
        if not model.ports and len(part.pins) != 2:
            raise ModelError(
                f"{ref} has {len(part.pins)} connected pins: the model map has to say "
                "which of them the element is between"
            )
        a, b = two_nodes()
        value = parse_value(part.value) * scale
        if model.kind == "resistor" and value == 0.0:
            value = _ZERO_OHM
        return [f"{ref} {a} {b} {value:.6g}{params}"]
    if model.kind == "short":
        a, b = two_nodes()
        return [f"R{ref} {a} {b} {_ZERO_OHM:.6g}"]
    if model.kind == "network":
        value = parse_value(part.value) * scale
        lines = []
        for index, pair in enumerate(_NETWORK_PAIRS, start=1):
            if not all(any(pin.number == number for pin in part.pins) for number in pair):
                continue  # a resistor of the network that is not on the schematic
            if all(part.net_of(number).startswith(_UNCONNECTED) for number in pair):
                continue  # a resistor that the schematic leaves open: it would float
            a, b = nodes_of(pair)
            lines.append(f"R{ref}_{index} {a} {b} {value:.6g}")
        return lines
    if model.kind == "kelvin":
        if len(model.ports) != 4:
            raise ModelError(f"{ref}: a kelvin model needs four ports")
        force_a, sense_a, sense_b, force_b = nodes_of(model.ports)
        value = parse_value(part.value) * scale
        return [
            f"{ref} {force_a} {force_b} {value:.6g}{params}",
            f"R{ref}_SA {force_a} {sense_a} {_SENSE_OHM:.6g}",
            f"R{ref}_SB {force_b} {sense_b} {_SENSE_OHM:.6g}",
        ]
    units = model.units or ((model.ports,) if model.ports else ())
    if not model.name or not units:
        raise ModelError(f"{ref}: a {model.kind} model needs a name and its ports")
    if model.kind == "device" and not model.letter:
        raise ModelError(f"{ref}: a device model needs the letter of its element")
    letter = "X" if model.kind == "subckt" else model.letter
    lines = []
    for index, ports in enumerate(units, start=1):
        suffix = f"_{index}" if len(units) > 1 else ""
        joined = " ".join(nodes_of(ports))
        lines.append(f"{letter}{ref}{suffix} {joined} {model.name}{params}")
    return lines


def load_model_map(path: pathlib.Path) -> ModelMap:
    """Read the model map of the repository.

    The map is one TOML file, or a folder whose TOML files are read together,
    so that every block can keep the models of its parts in a file of its
    own. A file has three tables: ``[part."<part number or value>"]``,
    ``[ref.<designator>]`` and ``[vendor."<part number>"]``, each entry with
    ``kind`` and, as the kind needs them, ``name``, ``ports`` or ``units``,
    ``letter``, ``library``, ``origin`` and ``params``.

    Raises:
        ModelError: When a file is missing or malformed, or two files give a
            model for the same part.
    """
    files = sorted(path.glob("*.toml")) if path.is_dir() else [path]
    if not files:
        raise ModelError(f"the folder {path} holds no model map")
    tables: dict[str, dict[str, PartModel]] = {"ref": {}, "part": {}, "vendor": {}}
    for file in files:
        try:
            with file.open("rb") as stream:
                document = tomllib.load(stream)
        except OSError as error:
            raise ModelError(f"cannot read the model map {file}: {error}") from error
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise ModelError(f"the model map {file} is not valid TOML: {error}") from error
        unknown = set(document) - set(tables)
        if unknown:
            raise ModelError(f"the model map {file} has unknown tables {sorted(unknown)}")
        for name, table in tables.items():
            found = _models(document.get(name, {}), name)
            twice = sorted(set(found) & set(table))
            if twice:
                raise ModelError(f"the model map {file} repeats {name} {', '.join(twice)}")
            table.update(found)
    return ModelMap(by_ref=tables["ref"], by_part=tables["part"], vendor=tables["vendor"])


def _models(table: object, where: str) -> dict[str, PartModel]:
    """The entries of one table of the model map."""
    if not isinstance(table, dict):
        raise ModelError(f"the model map table [{where}] is not a table")
    models: dict[str, PartModel] = {}
    for key, entry in table.items():
        if not isinstance(entry, dict) or "kind" not in entry:
            raise ModelError(f"model map, {where} {key!r}: an entry needs at least a kind")
        unknown = set(entry) - {
            "kind",
            "name",
            "ports",
            "units",
            "letter",
            "library",
            "origin",
            "params",
        }
        if unknown:
            raise ModelError(f"model map, {where} {key!r}: unknown keys {sorted(unknown)}")
        kind = str(entry["kind"])
        origin = str(entry.get("origin", ""))
        if kind not in _KINDS:
            raise ModelError(f"model map, {where} {key!r}: unknown kind {kind!r}")
        if origin not in _ORIGINS:
            raise ModelError(f"model map, {where} {key!r}: unknown origin {origin!r}")
        ports = entry.get("ports", [])
        units = entry.get("units", [])
        if not (
            isinstance(ports, list)
            and isinstance(units, list)
            and all(isinstance(unit, list) for unit in units)
        ):
            raise ModelError(
                f"model map, {where} {key!r}: "
                "ports is a list of pins and units a list of such lists"
            )
        models[str(key)] = PartModel(
            kind=kind,
            name=str(entry.get("name", "")),
            ports=tuple(str(port) for port in ports),
            units=tuple(tuple(str(port) for port in unit) for unit in units),
            letter=str(entry.get("letter", "")),
            library=str(entry.get("library", "")),
            origin=origin,
            params=str(entry.get("params", "")),
        )
    return models
