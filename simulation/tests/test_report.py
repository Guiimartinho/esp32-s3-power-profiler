from __future__ import annotations

import dataclasses
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from circuit_sim.bench import Figure
from circuit_sim.errors import BenchError
from circuit_sim.report import (
    ERROR,
    OK,
    RECORD_FORMAT,
    Record,
    as_stored,
    block_page,
    dump_record,
    figure_table,
    format_quantity,
    load_record,
    merge_cross_check,
    read_records,
    summary_table,
)

MICRO = "µ"
OHM = "Ω"
DEGREE = "°"
ROOT = "√"

FIGURES = (
    Figure(
        "shunt_r1",
        "R1: shunt seen by the amplifier",
        31.96,
        "ohm",
        expected=31.95,
        low=31.918,
        high=31.982,
        source="sections 4.3 and 8",
    ),
    Figure("burden_r3", "R3: burden at 1 A", 0.1085, "V", high=0.107, source="section 4.3"),
    Figure("burden_r2", "R2: burden at 100 mA", 0.1023, "V"),
    Figure("corner", "Corner | of the filter", 15.9e3, "Hz", low=10e3),
)

LONG_NOTE = (
    "The multiplexer is the behavioral model with 250 ohm per channel; its resistance "
    "carries no current here and does not enter these figures."
)


@pytest.fixture
def record() -> Record:
    return Record(
        block="ladder",
        block_title="Shunt Ladder",
        bench="ranges",
        title="The four ranges at rest",
        covers="section 4.3, section 8",
        summary="Each range is held and the load current is stepped.",
        status=OK,
        tier="open",
        engine="ngspice-45.2 shared library",
        library_sha256="ab" * 32,
        figures=FIGURES,
        graphs=(("map", "What each range gives", "ranges.map.png"),),
        notes=("The supply node is an ideal source.", LONG_NOTE),
        models=(
            ("Q12", "IRLML0030", "written here"),
            ("Q13", "IRLML0030", "written here"),
            ("U24", "MUX509", "written here"),
            ("U26", "OPA197_TI", "vendor"),
        ),
        decks=("ranges.r0-5v.cir", "ranges.r1-5v.cir"),
    )


@pytest.fixture
def broken() -> Record:
    return Record(
        block="ladder",
        block_title="Shunt Ladder",
        bench="broken",
        title="A bench that broke",
        covers="",
        summary="What it would have done.",
        status=ERROR,
        error="U99 (LM9999) has no model in the model map",
    )


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (0.09085, "V", "90.85 mV"),
        (1.0, "V", "1 V"),
        (5.0, "V", "5 V"),
        (-0.0035, "A", "-3.5 mA"),
        (1000.0, "ohm", f"1 k{OHM}"),
        (31.95, "ohm", f"31.95 {OHM}"),
        (0.999, "ohm", f"999 m{OHM}"),
        (2.2e6, "ohm", f"2.2 M{OHM}"),
        (1e9, "Hz", "1 GHz"),
        (1e-6, "s", f"1 {MICRO}s"),
        (2.5e-9, "A", "2.5 nA"),
        (1e-12, "F", "1 pF"),
        (3e-15, "C", "3 fC"),
        (4.07e-9, f"V/{ROOT}Hz", f"4.07 nV/{ROOT}Hz"),
        (15e-6, "H", f"15 {MICRO}H"),
        (0.25, "W", "250 mW"),
        (1.2e-3, "J", "1.2 mJ"),
    ],
)
def test_a_quantity_takes_the_prefix_that_leaves_one_to_three_digits_before_the_point(
    value: float, unit: str, text: str
) -> None:
    assert format_quantity(value, unit) == text


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        # Rounded to four digits these are 1 of the next prefix, not 1000 of this one.
        (0.99996, "V", "1 V"),
        (999.96e-6, "A", "1 mA"),
        (0.9994, "V", "999.4 mV"),
        # Beyond the prefixes the nearest one is kept.
        (5e12, "Hz", "5000 GHz"),
        (1e-18, "A", "0.001 fA"),
        (0.0, "V", "0 V"),
        (0.0, "ohm", f"0 {OHM}"),
    ],
)
def test_a_quantity_at_the_edge_of_a_prefix(value: float, unit: str, text: str) -> None:
    assert format_quantity(value, unit) == text


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (45.0, "deg", f"45 {DEGREE}"),
        (3.0, "%", "3 %"),
        (-3.01, "dB", "-3.01 dB"),
        (0.001, "dB", "0.001 dB"),
        (1500.0, "%", "1500 %"),
        (12.5, "", "12.5"),
        (2000.0, "ppm", "2000 ppm"),
    ],
)
def test_a_unit_that_takes_no_prefix_keeps_its_number(value: float, unit: str, text: str) -> None:
    assert format_quantity(value, unit) == text


def test_a_quantity_can_show_more_or_fewer_digits() -> None:
    assert format_quantity(0.0908512, "V", digits=6) == "90.8512 mV"
    assert format_quantity(1234.5678, "Hz", digits=2) == "1.2 kHz"
    assert format_quantity(1234.5678, "Hz") == "1.235 kHz"


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (None, "V", ""),
        (float("nan"), "V", "nan V"),
        (float("inf"), "ohm", f"inf {OHM}"),
        (float("-inf"), "dB", "-inf dB"),
        (float("nan"), "", "nan"),
    ],
)
def test_a_missing_value_is_empty_and_one_that_is_no_number_says_so(
    value: float | None, unit: str, text: str
) -> None:
    assert format_quantity(value, unit) == text


def test_a_record_counts_its_verdicts(record: Record, broken: Record) -> None:
    assert record.counts() == (2, 1, 1)
    assert broken.counts() == (0, 0, 0)


def test_a_record_comes_back_from_its_text_as_it_was(record: Record, broken: Record) -> None:
    assert load_record(dump_record(record)) == record
    assert load_record(dump_record(broken)) == broken


def test_the_text_of_a_record_is_stable_json(record: Record) -> None:
    text = dump_record(record)
    document = json.loads(text)

    assert text == dump_record(record)
    assert text.startswith('{\n "block": "ladder",\n')
    assert text.endswith("\n}\n")
    assert document["format"] == RECORD_FORMAT
    assert list(document) == [
        "block",
        "block_title",
        "bench",
        "title",
        "covers",
        "summary",
        "status",
        "error",
        "tier",
        "engine",
        "library_sha256",
        "figures",
        "graphs",
        "notes",
        "models",
        "decks",
        "format",
    ]
    assert document["figures"][0] == {
        "key": "shunt_r1",
        "label": "R1: shunt seen by the amplifier",
        "value": 31.96,
        "unit": "ohm",
        "expected": 31.95,
        "low": 31.918,
        "high": 31.982,
        "source": "sections 4.3 and 8",
        "verdict": "pass",
    }
    assert [entry["verdict"] for entry in document["figures"]] == ["pass", "fail", "info", "pass"]
    assert document["figures"][2]["low"] is None
    assert document["graphs"] == [["map", "What each range gives", "ranges.map.png"]]
    assert document["decks"] == ["ranges.r0-5v.cir", "ranges.r1-5v.cir"]


def test_the_models_of_a_record_are_stored_in_order(record: Record) -> None:
    shuffled = dataclasses.replace(record, models=tuple(reversed(record.models)))

    assert dump_record(shuffled) == dump_record(record)
    assert json.loads(dump_record(shuffled))["models"][0] == ["Q12", "IRLML0030", "written here"]


def test_the_numbers_of_a_record_are_stored_to_seven_digits(record: Record) -> None:
    third = Figure(
        "third", "A third", 1.0 / 3.0, "V", expected=2e-9 / 3.0, low=-1e9 / 7.0, high=1e-30
    )
    stored = json.loads(dump_record(dataclasses.replace(record, figures=(third,))))["figures"][0]

    assert stored["value"] == 0.3333333
    assert stored["expected"] == 6.666667e-10
    assert stored["low"] == -142857100.0
    assert stored["high"] == 1e-30


def test_a_figure_as_a_record_stores_it_has_seven_digits_in_every_number() -> None:
    third = Figure(
        "third", "A third", 1.0 / 3.0, "V", expected=2e-9 / 3.0, low=-1e9 / 7.0, source="4.3"
    )

    stored = as_stored(third)

    assert stored == Figure(
        "third", "A third", 0.3333333, "V", expected=6.666667e-10, low=-142857100.0, source="4.3"
    )
    assert stored.high is None
    # Rounding again changes nothing, and the record on file holds the same numbers.
    assert as_stored(stored) == stored
    assert as_stored(Figure("exact", "Exact", 2.5, "V", 2.5, 2.4, 2.6)) == Figure(
        "exact", "Exact", 2.5, "V", 2.5, 2.4, 2.6
    )


def test_a_figure_is_judged_on_the_digits_that_are_stored(record: Record) -> None:
    # 40 parts in a thousand million below the limit: a fail as it was
    # calculated, and 0.999 against 0.999 once it is on file.
    close = Figure("gain", "Gain of the chain", 0.99899996, "", low=0.999)
    above = Figure("ripple", "Ripple", 1.00000004e-3, "V", high=1e-3)

    stored = (as_stored(close), as_stored(above))
    text = dump_record(dataclasses.replace(record, figures=stored))

    assert (close.verdict, above.verdict) == ("fail", "fail")
    assert [(figure.value, figure.verdict) for figure in stored] == [
        (0.999, "pass"),
        (1e-3, "pass"),
    ]
    assert [entry["verdict"] for entry in json.loads(text)["figures"]] == ["pass", "pass"]
    assert load_record(text).figures == stored


def test_a_value_that_is_no_number_stays_what_it_is_when_it_is_stored() -> None:
    lost = as_stored(Figure("lost", "A margin that was not found", math.nan, "deg", low=math.inf))
    numpy_value = as_stored(Figure("tap", "Tap", np.float64(1.0) / 3.0, "V", high=np.float64(2.0)))

    assert math.isnan(lost.value)
    assert lost.low == math.inf
    assert type(numpy_value.value) is float
    assert type(numpy_value.high) is float
    assert (numpy_value.value, numpy_value.high) == (0.3333333, 2.0)


def test_text_outside_ascii_is_stored_as_it_is(record: Record) -> None:
    label = f"Noise in 10 {MICRO}s at 4.7 k{OHM}"
    text = dump_record(dataclasses.replace(record, figures=(Figure("noise", label, 1e-6, "V"),)))

    assert f'"label": "{label}"' in text
    assert load_record(text).figures[0].label == label


def test_the_values_of_the_vendor_tier_are_not_stored_with_a_record(record: Record) -> None:
    checked = dataclasses.replace(record, cross_check={"shunt_r1": 31.94})

    assert dump_record(checked) == dump_record(record)
    assert "cross_check" not in json.loads(dump_record(checked))
    assert load_record(dump_record(checked)).cross_check == {}


def test_a_value_that_is_no_number_is_stored_as_a_word(record: Record) -> None:
    def refuse(token: str) -> float:
        raise AssertionError(f"the text holds {token}, which is not JSON")

    figures = (
        Figure("lost", "A margin that was not found", math.nan, "deg", low=45.0),
        Figure("open", "Resistance of an open branch", math.inf, "ohm", expected=math.inf),
        Figure("floor", "A level in decibels", -math.inf, "dB", high=-math.inf, low=-math.inf),
        Figure("bare", "No number and no limit", math.nan, "V", expected=math.nan),
    )
    text = dump_record(dataclasses.replace(record, figures=figures))

    stored = json.loads(text, parse_constant=refuse)["figures"]
    loaded = load_record(text).figures

    assert [entry["value"] for entry in stored] == ["nan", "inf", "-inf", "nan"]
    assert (stored[1]["expected"], stored[2]["high"], stored[3]["expected"]) == (
        "inf",
        "-inf",
        "nan",
    )
    assert [entry["verdict"] for entry in stored] == ["fail", "info", "fail", "info"]
    assert math.isnan(loaded[0].value)
    assert loaded[0].low == 45.0
    assert (loaded[1].value, loaded[1].expected) == (math.inf, math.inf)
    assert (loaded[2].value, loaded[2].low, loaded[2].high) == (-math.inf, -math.inf, -math.inf)
    assert loaded[3].expected is not None
    assert math.isnan(loaded[3].expected)
    assert [figure.verdict for figure in loaded] == ["fail", "info", "fail", "info"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda document: document.pop("figures"), "KeyError"),
        (lambda document: document.pop("library_sha256"), "KeyError"),
        (lambda document: document["figures"][0].pop("unit"), "KeyError"),
        (lambda document: document["figures"][0].update(value=None), "TypeError"),
        (lambda document: document["figures"][0].update(value="about 3"), "ValueError"),
        (lambda document: document["figures"][0].update(low="none"), "ValueError"),
        (lambda document: document.update(figures=7), "TypeError"),
        (lambda document: document.update(graphs=[["map", "A graph"]]), "ValueError"),
        (lambda document: document.update(models=[["Q1", "X", "ideal", "more"]]), "ValueError"),
        (lambda document: document.update(notes=None), "TypeError"),
    ],
)
def test_a_result_file_with_a_broken_entry_is_refused(
    record: Record, change: Any, reason: str
) -> None:
    document = json.loads(dump_record(record))
    change(document)

    with pytest.raises(BenchError, match=f"the result file is malformed: {reason}"):
        load_record(json.dumps(document))


@pytest.mark.parametrize("text", ["", "{not json", "[]", '"a record"', "7", "null"])
def test_a_result_file_that_holds_no_record_is_refused(text: str) -> None:
    with pytest.raises(BenchError, match="the result file is malformed"):
        load_record(text)


@pytest.mark.parametrize("version", [0, 2, "1", None])
def test_a_result_file_of_another_format_is_refused(record: Record, version: object) -> None:
    document = json.loads(dump_record(record))
    document["format"] = version

    with pytest.raises(BenchError, match="the result file has a format this package does not read"):
        load_record(json.dumps(document))
    del document["format"]
    with pytest.raises(BenchError, match="the result file has a format this package does not read"):
        load_record(json.dumps(document))


def test_the_figures_of_a_bench_as_a_table(record: Record) -> None:
    assert figure_table(record) == [
        "| Figure | Simulated | Specification | Limits | Verdict | Source |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| R1: shunt seen by the amplifier | 31.96 {OHM} | 31.95 {OHM} (+0.03 %) "
        f"| 31.92 {OHM} to 31.98 {OHM} | pass | sections 4.3 and 8 |",
        "| R3: burden at 1 A | 108.5 mV | | at most 107 mV | **FAIL** | section 4.3 |",
        "| R2: burden at 100 mA | 102.3 mV | | | | |",
        "| Corner \\| of the filter | 15.9 kHz | | at least 10 kHz | pass | |",
    ]


def test_the_values_of_the_vendor_tier_stand_beside_the_simulated_ones(record: Record) -> None:
    checked = dataclasses.replace(record, cross_check={"shunt_r1": 31.94, "burden_r3": 0.1101})

    assert figure_table(checked) == [
        "| Figure | Simulated | Vendor models | Specification | Limits | Verdict | Source |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        f"| R1: shunt seen by the amplifier | 31.96 {OHM} | 31.94 {OHM} | 31.95 {OHM} (+0.03 %) "
        f"| 31.92 {OHM} to 31.98 {OHM} | pass | sections 4.3 and 8 |",
        "| R3: burden at 1 A | 108.5 mV | 110.1 mV | | at most 107 mV | **FAIL** | section 4.3 |",
        "| R2: burden at 100 mA | 102.3 mV | | | | | |",
        "| Corner \\| of the filter | 15.9 kHz | | | at least 10 kHz | pass | |",
    ]


@pytest.mark.parametrize(
    ("value", "expected", "text"),
    [
        (2.5, 2.5, "2.5 V (+0.00 %)"),
        (2.49999, 2.5, "2.5 V (+0.00 %)"),
        (2.4, 2.5, "2.5 V (-4.00 %)"),
        (-2.6, -2.5, "-2.5 V (-4.00 %)"),
        (5.0, 2.5, "2.5 V (+100.00 %)"),
        (0.1, 0.0, "0 V"),
        (math.nan, 2.5, "2.5 V"),
        (2.5, math.inf, "inf V"),
    ],
)
def test_the_expected_value_comes_with_the_distance_of_the_simulation_from_it(
    record: Record, value: float, expected: float, text: str
) -> None:
    one = dataclasses.replace(
        record, figures=(Figure("tap", "Tap", value, "V", expected=expected),)
    )

    assert figure_table(one)[2].split(" | ")[2] == text


def test_a_table_never_holds_a_cell_of_two_blanks(record: Record, broken: Record) -> None:
    # The Markdown lint of the repository wants one blank beside a pipe.
    lines = [*figure_table(record), *summary_table([record, broken])]

    assert not [line for line in lines if "  " in line]
    assert all(line.startswith("| ") and line.endswith(" |") for line in lines)


def test_the_page_of_a_block(record: Record, broken: Record) -> None:
    page = block_page("ladder", "Shunt Ladder", [record, broken])

    assert page == "\n".join(
        [
            "# Simulation Results: Shunt Ladder",
            "",
            "Everything on this page is a simulation result. Nothing here is measured on",
            "hardware. The page is written by `circuit-sim report` from the result files",
            "beside it; do not edit it by hand.",
            "",
            "## `ladder/ranges`",
            "",
            "**The four ranges at rest.**",
            "",
            "Each range is held and the load current is stepped.",
            "",
            "Answers: section 4.3, section 8.",
            "",
            *figure_table(record),
            "",
            "![What each range gives](ranges.map.png)",
            "",
            "Notes:",
            "",
            "- The supply node is an ideal source.",
            "- The multiplexer is the behavioral model with 250 ohm per channel; its",
            "  resistance carries no current here and does not enter these figures.",
            "",
            "Models. vendor: OPA197_TI; written here: IRLML0030, MUX509.",
            "",
            "Decks: [ranges.r0-5v.cir](ranges.r0-5v.cir),",
            "[ranges.r1-5v.cir](ranges.r1-5v.cir).",
            "",
            "## `ladder/broken`",
            "",
            "**A bench that broke.**",
            "",
            "What it would have done.",
            "",
            "**The bench did not run:** U99 (LM9999) has no model in the model map",
            "",
        ]
    )


def test_a_page_leaves_out_what_a_bench_does_not_have(record: Record) -> None:
    bare = dataclasses.replace(
        record, covers="", summary="", graphs=(), notes=(), models=(), decks=(), figures=()
    )
    untitled = dataclasses.replace(bare, title="", summary="What the bench does.")

    assert block_page("ladder", "Shunt Ladder", [bare]).split("\n")[6:] == [
        "## `ladder/ranges`",
        "",
        "**The four ranges at rest.**",
        "",
        "| Figure | Simulated | Specification | Limits | Verdict | Source |",
        "| --- | --- | --- | --- | --- | --- |",
        "",
    ]
    assert block_page("ladder", "Shunt Ladder", [untitled]).split("\n")[6:10] == [
        "## `ladder/ranges`",
        "",
        "What the bench does.",
        "",
    ]
    assert block_page("empty", "Nothing Yet", []).split("\n")[:2] == [
        "# Simulation Results: Nothing Yet",
        "",
    ]


@pytest.mark.parametrize(
    ("title", "shown"),
    [
        ("The four ranges at rest", "**The four ranges at rest.**"),
        ("Burden at 1 A (range 3)", "**Burden at 1 A (range 3).**"),
        ("The four ranges at rest.", "**The four ranges at rest.**"),
        ("Does the ladder clamp hold?", "**Does the ladder clamp hold?**"),
        ("Requirement R-07:", "**Requirement R-07:**"),
        ("  The four ranges at rest  ", "**The four ranges at rest.**"),
    ],
)
def test_the_title_of_a_bench_is_a_line_of_its_own_that_ends_like_a_sentence(
    record: Record, title: str, shown: str
) -> None:
    # A whole paragraph in bold without a mark at its end is taken for a
    # heading by the Markdown lint of the repository.
    lines = block_page("ladder", "Shunt Ladder", [dataclasses.replace(record, title=title)])

    assert lines.split("\n")[6:10] == ["## `ladder/ranges`", "", shown, ""]


def test_a_long_title_is_wrapped_and_the_heading_stays_short(record: Record) -> None:
    title = (
        "The output terminal under abuse: reversed source, live source on the open output, "
        "charged capacitor on a lower output"
    )
    long = dataclasses.replace(record, bench="terminal-under-abuse", title=title)

    lines = block_page("output_stage", "Output Stage", [long]).split("\n")

    assert lines[6:11] == [
        "## `ladder/terminal-under-abuse`",
        "",
        "**The output terminal under abuse: reversed source, live source on the open",
        "output, charged capacitor on a lower output.**",
        "",
    ]
    assert max(len(line) for line in lines if not line.startswith(("|", "!["))) <= 80
    # The summary table, which may be as wide as it likes, keeps the title.
    assert summary_table([long])[2] == (
        f"| ladder | [terminal-under-abuse](ladder/README.md) | {title} | 2 | **1** | 1 |"
    )


def test_the_message_of_a_bench_that_did_not_run_is_shown_as_the_simulator_wrote_it(
    broken: Record,
) -> None:
    # What ngspice and the system print is no Markdown: a star, an angle
    # bracket or an underscore in it must not turn into emphasis or a tag.
    message = (
        "power-up.min: the run failed: Error: -1.87e+190, -1.87e+190 out of range for *; "
        "Error on line 3 : x1 a b <model> `tick` [1] in C:\\work\\deck_1.cir, "
        "__init__ & more ~ at $x$ > 2 * 3"
    )
    failed = dataclasses.replace(broken, error=message)

    lines = block_page("ladder", "Shunt Ladder", [failed]).split("\n")
    shown = " ".join(lines[lines.index("What it would have done.") + 2 : -1])

    head = "**The bench did not run:** "
    assert shown.startswith(head + "power-up.min: the run failed: ")
    # Every mark has a backslash in front of it, and without those the text is the message.
    assert not re.findall(r"(?<!\\)[*_`<>\[\]&~$]", shown.removeprefix(head))
    assert re.sub(r"\\(.)", r"\1", shown) == head + message
    assert r"out of range for \*; Error on line 3 : x1 a b \<model\> \`tick\` \[1\]" in shown
    assert r"C:\\work\\deck\_1.cir, \_\_init\_\_ \& more \~ at \$x\$ \> 2 \* 3" in shown


def test_a_message_of_several_lines_is_shown_as_one_paragraph(broken: Record) -> None:
    message = (
        "step: the simulator process died (exit 1): Traceback (most recent call last):\n"
        '  File "<frozen runpy>", line 198, in _run_module_as_main\n\n'
        "OSError: cannot load the library\r\n"
    )

    lines = block_page("ladder", "S", [dataclasses.replace(broken, error=message)]).split("\n")

    assert lines[-5:] == [
        "",
        "**The bench did not run:** step: the simulator process died (exit 1): Traceback",
        r'(most recent call last): File "\<frozen runpy\>", line 198, in',
        r"\_run\_module\_as\_main OSError: cannot load the library",
        "",
    ]


def test_a_model_without_an_origin_is_listed_as_unnamed(record: Record) -> None:
    mixed = dataclasses.replace(
        record,
        models=(("U1", "OPA365", ""), ("U2", "IDEAL_SWITCH", "ideal"), ("D1", "BAV199", "")),
    )

    assert "Models. ideal: IDEAL_SWITCH; unnamed: BAV199, OPA365." in block_page(
        "ladder", "Shunt Ladder", [mixed]
    ).split("\n")


def test_the_prose_of_a_page_keeps_to_eighty_columns(record: Record, broken: Record) -> None:
    wordy = dataclasses.replace(
        record,
        summary=" ".join(f"word{number}" for number in range(60)),
        covers=", ".join(f"section {number}.{number}" for number in range(40)),
        notes=(LONG_NOTE * 3, "A deck name-that-is-not-broken at a hyphen " * 5),
        decks=tuple(f"ranges.r{number}-5v.cir" for number in range(8)),
    )
    failed = dataclasses.replace(broken, error="the run failed: " + "singular matrix; " * 20)

    lines = block_page("ladder", "Shunt Ladder", [wordy, failed]).split("\n")
    prose = [line for line in lines if not line.startswith(("|", "!["))]

    assert max(len(line) for line in prose) <= 80
    assert not [line for line in prose if line != line.rstrip()]
    # Nothing is lost or cut: the words of the summary are all there, in order.
    text = " ".join(prose)
    assert " ".join(f"word{number}" for number in range(60)) in " ".join(text.split())
    assert "name-that-is-not-broken" in text
    # The lines of a note after its first stand under its text.
    start = prose.index("Notes:") + 2
    assert prose[start].startswith("- The multiplexer")
    assert prose[start + 1].startswith("  ")


@pytest.mark.parametrize(
    "marker", ["1.", "12)", "-", "+", "*", ">", ">=", "#", "##", "---", "===", "***", "___"]
)
def test_a_line_of_prose_never_starts_with_what_markdown_reads_as_a_mark(
    record: Record, marker: str
) -> None:
    # "... in range 1. The model ..." must not break in front of the "1.":
    # the rest of the paragraph would become a list. A line of dashes alone
    # would make a heading of the lines above it.
    meant = {"# Simulation Results: Shunt Ladder", "## `ladder/ranges`"}
    for filler in range(1, 30):
        summary = f"{'x' * filler} " + f"The ladder carries 2 mA in range {marker} The model. " * 6
        note = "A note of some length that " + f"goes on {marker} and on " * 12
        covers = f"section 4.3 and rule {marker} " * 8
        title = f"{'y' * filler} " + f"a title about range {marker} and more " * 4
        wordy = dataclasses.replace(
            record, title=title, summary=summary, notes=(note,), covers=covers.strip()
        )

        lines = block_page("ladder", "Shunt Ladder", [wordy]).split("\n")

        marked = [
            line
            for line in lines
            if re.match(r"\s*(?:(?:\d+[.)]|[-=*]+|\+|_{3,}|#+)(?: |$)|>)", line)
            and line not in meant
            and not line.startswith("- A note of some length")
        ]
        assert marked == []
        assert max(len(line) for line in lines if not line.startswith(("|", "!["))) <= 80
        # The words are all still there, a blank between them.
        assert " ".join(note.split()) in " ".join(" ".join(lines).split())


def test_the_summary_has_one_line_per_bench(record: Record, broken: Record) -> None:
    clean = dataclasses.replace(
        record, bench="change", title="A range | change", figures=FIGURES[2:]
    )

    assert summary_table([record, broken, clean]) == [
        "| Block | Bench | What is simulated | Pass | Fail | No limit |",
        "| --- | --- | --- | --- | --- | --- |",
        "| ladder | [ranges](ladder/README.md) | The four ranges at rest | 2 | **1** | 1 |",
        "| ladder | [broken](ladder/README.md) | A bench that broke | did not run | | |",
        "| ladder | [change](ladder/README.md) | A range \\| change | 1 | 0 | 1 |",
    ]
    assert summary_table([]) == summary_table(iter(()))
    assert len(summary_table([])) == 2


def test_the_values_of_a_vendor_run_are_put_beside_a_record(record: Record) -> None:
    vendor = dataclasses.replace(
        record,
        tier="vendor",
        figures=(
            dataclasses.replace(FIGURES[0], value=31.94),
            dataclasses.replace(FIGURES[1], value=0.1101),
            Figure("only_vendor", "A figure of the vendor run alone", 1.0, "V"),
        ),
    )

    merged = merge_cross_check(record, vendor)

    assert merged.cross_check == {"shunt_r1": 31.94, "burden_r3": 0.1101, "only_vendor": 1.0}
    assert dataclasses.replace(merged, cross_check={}) == record
    assert merged.figures is record.figures
    # The record that was given is not changed.
    assert record.cross_check == {}


def test_a_vendor_run_that_is_missing_or_broken_leaves_a_record_as_it_is(
    record: Record, broken: Record
) -> None:
    assert merge_cross_check(record, None) is record
    assert merge_cross_check(record, dataclasses.replace(broken, tier="vendor")) is record


def test_the_records_of_a_results_folder_are_read_with_their_vendor_runs(
    tmp_path: Path, record: Record, broken: Record
) -> None:
    vendor = dataclasses.replace(
        record, tier="vendor", figures=(dataclasses.replace(FIGURES[0], value=31.94),)
    )
    other = dataclasses.replace(record, block="chain", block_title="Signal Chain", bench="gain")
    for folder in ("ladder", "chain", "empty"):
        (tmp_path / folder).mkdir()
    (tmp_path / "ladder" / "ranges.json").write_text(dump_record(record), encoding="utf-8")
    (tmp_path / "ladder" / "ranges.vendor.json").write_text(dump_record(vendor), encoding="utf-8")
    (tmp_path / "ladder" / "broken.json").write_text(dump_record(broken), encoding="utf-8")
    (tmp_path / "chain" / "gain.json").write_text(dump_record(other), encoding="utf-8")
    # Files that are no records: a page, a graph, a file beside the folders.
    (tmp_path / "ladder" / "README.md").write_text("# A page\n", encoding="utf-8")
    (tmp_path / "ladder" / "ranges.map.png").write_bytes(b"\x89PNG")
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")

    records = read_records(tmp_path)

    assert [(found.block, found.bench) for found in records] == [
        ("chain", "gain"),
        ("ladder", "broken"),
        ("ladder", "ranges"),
    ]
    assert records[0] == other
    assert records[1] == broken
    assert records[2] == dataclasses.replace(record, cross_check={"shunt_r1": 31.94})
    assert read_records(tmp_path / "empty") == []
    assert read_records(tmp_path / "missing") == []


def test_a_results_folder_with_a_broken_file_is_refused(tmp_path: Path, record: Record) -> None:
    (tmp_path / "ladder").mkdir()
    (tmp_path / "ladder" / "ranges.json").write_text(dump_record(record), encoding="utf-8")
    (tmp_path / "ladder" / "ranges.vendor.json").write_text("{}", encoding="utf-8")

    with pytest.raises(BenchError, match="the result file has a format this package does not read"):
        read_records(tmp_path)

    (tmp_path / "ladder" / "ranges.vendor.json").unlink()
    (tmp_path / "ladder" / "change.json").write_text("not a record", encoding="utf-8")

    with pytest.raises(BenchError, match="the result file is malformed"):
        read_records(tmp_path)
