"""Stored results and the pages that show them.

A bench that ran leaves a record: its figures with their verdicts, the names
of its graphs and decks, the models it used and the build of the simulator.
The records are JSON files beside the graphs; the pages of the report are
written from them, so that a page never shows a number that is not on file.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from circuit_sim.bench import FAIL, INFO, PASS, Figure
from circuit_sim.errors import BenchError

RECORD_FORMAT = 1
"""Version of the record document."""

OK = "ok"
ERROR = "error"

_PREFIXES = (
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
)
_SCALED_UNITS = frozenset({"V", "A", "s", "Hz", "ohm", "F", "H", "W", "C", "J", "V/√Hz", "A/√Hz"})
_UNIT_TEXT = {"ohm": "Ω", "deg": "°"}
_WIDTH = 80

# The blanks in front of a word that must not be the first of a line: the
# number or the sign of a list, a row of dashes, equals signs, stars or
# underscores, the hashes of a heading, the angle bracket of a quotation.
# What stands in their place while the text is wrapped is a character of the
# private use area, which no text holds and at which no line is broken.
_MARK = re.compile(
    r"[\t\n\x0b\x0c\r ]+"
    r"(?=(?:\d{1,9}[.)]|[-=*]+|\+|_{3,}|#{1,6})(?:[\t\n\x0b\x0c\r ]|$)|>)"
)
_GLUE = chr(0xE000)

# The characters that Markdown reads as marks inside a line of text.
_MARKDOWN = re.compile(r"[\\`*_\[\]<>&~$]")

# The marks that end a line of text like a sentence.
_SENTENCE_ENDS = (".", ",", ";", ":", "!", "?")


@dataclass(frozen=True, slots=True)
class Record:
    """The stored result of one bench.

    Attributes:
        block: Block of the bench.
        block_title: Title of the block.
        bench: Name of the bench inside the block.
        title: What is simulated.
        covers: The sections, requirements and decisions it answers.
        summary: What the bench does.
        status: ``ok`` when the bench ran, ``error`` when it could not.
        error: The message of the failure, empty when the bench ran.
        tier: ``open`` or ``vendor``.
        engine: Version line of the simulator.
        library_sha256: Checksum of the simulator library.
        figures: The figures.
        graphs: The graphs as (name, title, file name).
        notes: What the reader has to know to weigh the result.
        models: The models used, as (designator, model, origin).
        decks: File names of the decks kept with the result.
        cross_check: Values of the same figures from the vendor tier, by key.
            Not stored: it is read from the result file of that tier.
    """

    block: str
    block_title: str
    bench: str
    title: str
    covers: str
    summary: str
    status: str
    error: str = ""
    tier: str = "open"
    engine: str = ""
    library_sha256: str = ""
    figures: tuple[Figure, ...] = ()
    graphs: tuple[tuple[str, str, str], ...] = ()
    notes: tuple[str, ...] = ()
    models: tuple[tuple[str, str, str], ...] = ()
    decks: tuple[str, ...] = ()
    cross_check: dict[str, float] = field(default_factory=dict)

    def counts(self) -> tuple[int, int, int]:
        """How many figures pass, fail and carry no limit."""
        verdicts = [figure.verdict for figure in self.figures]
        return verdicts.count(PASS), verdicts.count(FAIL), verdicts.count(INFO)


def _rounded(value: float) -> float:
    """A number with the digits that a record keeps of it: seven."""
    return float(f"{value:.7g}") if math.isfinite(value) else float(value)


def _kept(value: float | None) -> float | None:
    """The same for a number that may be missing."""
    return None if value is None else _rounded(value)


def _number(value: float | None) -> float | str | None:
    """A value as JSON holds it: a number, null, or a word for what is no number."""
    if value is None:
        return None
    if math.isfinite(value):
        return _rounded(value)
    return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")


def _value(stored: Any) -> float | None:
    """The reverse of :func:`_number`."""
    if stored is None:
        return None
    return float(stored)


def as_stored(figure: Figure) -> Figure:
    """A figure with its numbers as a record stores them.

    A record keeps seven digits of every number, so that two runs with the
    same result leave the same file. A figure that is rounded like that
    before it is judged has one verdict: the one that a run prints is the one
    that the result file and the page show.
    """
    return replace(
        figure,
        value=_rounded(figure.value),
        expected=_kept(figure.expected),
        low=_kept(figure.low),
        high=_kept(figure.high),
    )


def dump_record(record: Record) -> str:
    """The JSON text of a record, stable between runs with the same numbers."""
    document: dict[str, Any] = asdict(record)
    document["format"] = RECORD_FORMAT
    document.pop("cross_check")
    document["figures"] = [
        {
            "key": figure.key,
            "label": figure.label,
            "value": _number(figure.value),
            "unit": figure.unit,
            "expected": _number(figure.expected),
            "low": _number(figure.low),
            "high": _number(figure.high),
            "source": figure.source,
            "verdict": figure.verdict,
        }
        for figure in record.figures
    ]
    document["models"] = sorted(list(model) for model in record.models)
    return json.dumps(document, indent=1, ensure_ascii=False) + "\n"


def load_record(text: str) -> Record:
    """A record from its JSON text.

    Raises:
        BenchError: When the text is not a record of a format this package reads.
    """
    try:
        document = json.loads(text)
        if document.get("format") != RECORD_FORMAT:
            raise BenchError("the result file has a format this package does not read")
        figures = tuple(
            Figure(
                key=item["key"],
                label=item["label"],
                value=float(item["value"]),
                unit=item["unit"],
                expected=_value(item["expected"]),
                low=_value(item["low"]),
                high=_value(item["high"]),
                source=item["source"],
            )
            for item in document["figures"]
        )
        return Record(
            block=document["block"],
            block_title=document["block_title"],
            bench=document["bench"],
            title=document["title"],
            covers=document["covers"],
            summary=document["summary"],
            status=document["status"],
            error=document["error"],
            tier=document["tier"],
            engine=document["engine"],
            library_sha256=document["library_sha256"],
            figures=figures,
            graphs=tuple((name, title, file) for name, title, file in document["graphs"]),
            notes=tuple(document["notes"]),
            models=tuple((ref, model, origin) for ref, model, origin in document["models"]),
            decks=tuple(document["decks"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as error:
        raise BenchError(f"the result file is malformed: {error!r}") from error


def format_quantity(value: float | None, unit: str, digits: int = 4) -> str:
    """A value with its unit, with an SI prefix where the unit takes one.

    ``format_quantity(0.09085, "V")`` gives ``90.85 mV``. A missing value
    gives an empty string.
    """
    if value is None:
        return ""
    shown = _UNIT_TEXT.get(unit, unit)
    if not math.isfinite(value):
        return f"{value} {shown}".strip()
    if unit in _SCALED_UNITS and value != 0.0:
        magnitude = abs(value)
        for scale, prefix in _PREFIXES:
            if magnitude >= scale * 0.9995:
                return f"{value / scale:.{digits}g} {prefix}{shown}"
        scale, prefix = _PREFIXES[-1]
        return f"{value / scale:.{digits}g} {prefix}{shown}"
    return f"{value:.{digits}g} {shown}".strip()


def _wrapped(text: str, indent: str = "") -> list[str]:
    """Prose wrapped to the width that the documents of the repository keep.

    A word that Markdown reads as the start of a list, a quotation or a
    heading when a line begins with it (``1.``, ``-``, ``>``, ``#``) is kept
    on the line of the word before it.
    """
    lines = textwrap.wrap(
        _MARK.sub(_GLUE, text),
        width=_WIDTH,
        initial_indent=indent,
        subsequent_indent=" " * len(indent),
        break_long_words=False,
        break_on_hyphens=False,
    )
    return [line.replace(_GLUE, " ") for line in lines]


def _limits(figure: Figure) -> str:
    """The limits of a figure as text."""
    low = format_quantity(figure.low, figure.unit)
    high = format_quantity(figure.high, figure.unit)
    if low and high:
        return f"{low} to {high}"
    if low:
        return f"at least {low}"
    if high:
        return f"at most {high}"
    return ""


def _expected(figure: Figure) -> str:
    """The expected value of a figure with the distance of the simulation from it."""
    if figure.expected is None:
        return ""
    text = format_quantity(figure.expected, figure.unit)
    deviation = figure.deviation
    if deviation is not None and math.isfinite(deviation):
        percent = 100.0 * deviation
        text += f" ({0.0 if abs(percent) < 0.005 else percent:+.2f} %)"
    return text


def _cell(text: str) -> str:
    """Text that is safe inside a table cell."""
    return text.replace("|", "\\|")


def _plain(text: str) -> str:
    """Text that no person wrote, shown as it is.

    A message of the simulator or of the system holds stars, underscores and
    angle brackets that Markdown would read as emphasis or as a tag: each of
    its marks gets a backslash in front. Its lines become one paragraph, with
    one blank between the words.
    """
    return _MARKDOWN.sub(r"\\\g<0>", " ".join(text.split()))


def _row(cells: Iterable[str]) -> str:
    """One row of a table; a cell without text is one blank between its pipes."""
    return "|" + "".join(f" {cell} |" if cell else " |" for cell in cells)


def _lead(title: str) -> str:
    """The title of a bench as the first line under its heading.

    It stands in bold and ends like a sentence: a paragraph of one line that
    is all in bold and ends without a mark is a heading in disguise for the
    Markdown lint of the repository.
    """
    text = title.strip()
    return f"**{text}**" if text.endswith(_SENTENCE_ENDS) else f"**{text}.**"


def figure_table(record: Record) -> list[str]:
    """The table of the figures of a bench, as Markdown lines."""
    vendor = bool(record.cross_check)
    head = ["Figure", "Simulated"]
    if vendor:
        head.append("Vendor models")
    head += ["Specification", "Limits", "Verdict", "Source"]
    lines = [_row(head), _row("---" for _ in head)]
    for figure in record.figures:
        row = [figure.label, format_quantity(figure.value, figure.unit)]
        if vendor:
            row.append(format_quantity(record.cross_check.get(figure.key), figure.unit))
        verdict = {PASS: "pass", FAIL: "**FAIL**", INFO: ""}[figure.verdict]
        row += [_expected(figure), _limits(figure), verdict, figure.source]
        lines.append(_row(_cell(cell) for cell in row))
    return lines


def block_page(block: str, title: str, records: Sequence[Record]) -> str:
    """The page of one block: every bench with its figures and graphs."""
    lines = [f"# Simulation Results: {title}", ""]
    lines += _wrapped(
        "Everything on this page is a simulation result. Nothing here is "
        "measured on hardware. The page is written by `circuit-sim report` "
        "from the result files beside it; do not edit it by hand."
    )
    for record in records:
        # The heading is the name of the bench, which is always short: a
        # title can be longer than the line of a heading may be.
        lines += ["", f"## `{record.block}/{record.bench}`"]
        if record.title.strip():
            lines += ["", *_wrapped(_lead(record.title))]
        if record.summary.strip():
            lines += ["", *_wrapped(record.summary)]
        if record.covers:
            lines += ["", *_wrapped(f"Answers: {record.covers}.")]
        if record.status != OK:
            lines += ["", *_wrapped(f"**The bench did not run:** {_plain(record.error)}")]
            continue
        lines += ["", *figure_table(record)]
        for _name, graph_title, file in record.graphs:
            lines += ["", f"![{graph_title}]({file})"]
        if record.notes:
            lines += ["", "Notes:", ""]
            for note in record.notes:
                lines += _wrapped(note, indent="- ")
        if record.models:
            by_origin: dict[str, set[str]] = {}
            for _ref, model, origin in record.models:
                by_origin.setdefault(origin or "unnamed", set()).add(model)
            parts = [
                f"{origin}: {', '.join(sorted(models))}"
                for origin, models in sorted(by_origin.items())
            ]
            lines += ["", *_wrapped("Models. " + "; ".join(parts) + ".")]
        if record.decks:
            decks = ", ".join(f"[{name}]({name})" for name in record.decks)
            lines += ["", *_wrapped(f"Decks: {decks}.")]
    return "\n".join(lines) + "\n"


def summary_table(records: Iterable[Record]) -> list[str]:
    """One line per bench: how many figures pass, fail and have no limit."""
    lines = [
        "| Block | Bench | What is simulated | Pass | Fail | No limit |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        cells = [record.block, f"[{record.bench}]({record.block}/README.md)", _cell(record.title)]
        if record.status != OK:
            lines.append(_row([*cells, "did not run", "", ""]))
            continue
        passed, failed, plain = record.counts()
        lines.append(_row([*cells, str(passed), f"**{failed}**" if failed else "0", str(plain)]))
    return lines


def merge_cross_check(record: Record, vendor: Record | None) -> Record:
    """A record with the values of its vendor-tier run beside its own."""
    if vendor is None or vendor.status != OK:
        return record
    values = {figure.key: figure.value for figure in vendor.figures}
    return replace(record, cross_check=values)


def read_records(results: pathlib.Path) -> list[Record]:
    """Every record under a results folder, open tier, with its cross-check.

    Raises:
        BenchError: When a result file is malformed.
    """
    records = []
    for path in sorted(results.glob("*/*.json")):
        if path.name.endswith(".vendor.json"):
            continue
        record = load_record(path.read_text(encoding="utf-8"))
        vendor_path = path.with_name(path.stem + ".vendor.json")
        vendor = (
            load_record(vendor_path.read_text(encoding="utf-8")) if vendor_path.is_file() else None
        )
        records.append(merge_cross_check(record, vendor))
    return records
