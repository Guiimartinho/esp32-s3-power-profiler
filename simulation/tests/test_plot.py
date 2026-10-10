from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure as Canvas
from matplotlib.text import Annotation
from PIL import Image

from circuit_sim.bench import Graph, Panel, Trace
from circuit_sim.errors import BenchError
from circuit_sim.plot import compact_png, render

TIME = np.linspace(0.0, 1.0, 50)


def png_chunks(path: Path) -> list[tuple[bytes, bytes]]:
    """The chunks of a PNG file as (kind, content), in the order of the file."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks = []
    place = 8
    while place < len(data):
        (length,) = struct.unpack(">I", data[place : place + 4])
        chunks.append((data[place + 4 : place + 8], data[place + 8 : place + 8 + length]))
        place += 12 + length
    return chunks


def png_size(path: Path) -> tuple[int, int]:
    """The width and the height of a PNG file in pixels, from its header."""
    kind, header = png_chunks(path)[0]
    assert kind == b"IHDR"
    width, height = struct.unpack(">II", header[:8])
    return width, height


def notes_of(axis: Axes) -> list[Annotation]:
    """The labels that were written into a panel beside its lines."""
    return [text for text in axis.texts if isinstance(text, Annotation)]


def step(panels: int = 1, **options: Any) -> Graph:
    """A graph with one labeled curve in each panel."""
    return Graph(
        name="step",
        title="A step and its answer",
        xlabel="Time (s)",
        panels=tuple(Panel(f"Panel {number} (V)") for number in range(panels)),
        traces=tuple(
            Trace(TIME, TIME * (number + 1), f"curve {number}", number) for number in range(panels)
        ),
        **options,
    )


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[Canvas]:
    """The figures that the module draws, kept so that a test can look at them."""
    figures: list[Canvas] = []

    class Kept(Canvas):
        def __init__(self, *arguments: Any, **options: Any) -> None:
            super().__init__(*arguments, **options)
            figures.append(self)

    monkeypatch.setattr("circuit_sim.plot.Canvas", Kept)
    return figures


@pytest.mark.parametrize(("panels", "height"), [(1, 396), (2, 693), (4, 1287)])
def test_a_graph_is_a_png_file_of_a_fixed_width_that_grows_with_its_panels(
    tmp_path: Path, panels: int, height: int
) -> None:
    path = tmp_path / "step.png"

    render(step(panels), path)

    assert png_size(path) == (990, height)


def test_the_folder_of_the_file_is_made(tmp_path: Path) -> None:
    path = tmp_path / "results" / "ladder" / "change.step.png"

    render(step(), path)

    assert path.is_file()


def test_the_same_graph_gives_the_same_file(tmp_path: Path) -> None:
    graph = step(2, logx=False, xmarks=((0.5, "event"),))

    render(graph, tmp_path / "first.png")
    render(graph, tmp_path / "second.png")
    first = (tmp_path / "first.png").read_bytes()

    assert first == (tmp_path / "second.png").read_bytes()
    # The file holds the picture and its resolution: no chunk of text that
    # names the program that wrote it, and no chunk with the time of writing.
    kinds = [kind for kind, _ in png_chunks(tmp_path / "first.png")]
    assert kinds[0] == b"IHDR"
    assert kinds[-1] == b"IEND"
    assert set(kinds) <= {b"IHDR", b"PLTE", b"pHYs", b"sBIT", b"IDAT", b"IEND"}


def test_a_graph_is_filed_with_a_palette_and_keeps_its_size(tmp_path: Path) -> None:
    graph = step(2, logx=False)
    render(graph, tmp_path / "graph.png")

    kinds = [kind for kind, _ in png_chunks(tmp_path / "graph.png")]

    assert b"PLTE" in kinds


def test_packing_a_picture_keeps_its_dimensions_and_makes_it_smaller() -> None:
    picture = Image.new("RGB", (320, 200), "white")
    for x in range(320):
        picture.putpixel((x, 100 + (x % 40) - 20), (31, 119, 180))
    plain = io.BytesIO()
    picture.save(plain, format="PNG")

    packed = compact_png(plain.getvalue())

    with Image.open(io.BytesIO(packed)) as reduced:
        assert reduced.size == (320, 200)
        assert reduced.mode == "P"
    assert len(packed) < len(plain.getvalue())
    assert compact_png(plain.getvalue()) == packed


def test_a_graph_without_a_panel_is_refused(tmp_path: Path) -> None:
    empty = Graph("empty", "Nothing", "Time (s)", (), ())

    with pytest.raises(BenchError, match="the graph empty has no panel"):
        render(empty, tmp_path / "empty.png")

    assert not (tmp_path / "empty.png").exists()


@pytest.mark.parametrize("panel", [1, 2, -1])
def test_a_curve_on_a_panel_that_the_graph_does_not_have_is_refused(
    tmp_path: Path, panel: int
) -> None:
    graph = Graph(
        "step",
        "A step",
        "Time (s)",
        (Panel("Voltage (V)"),),
        (Trace(TIME, TIME, "in"), Trace(TIME, TIME, "out", panel)),
    )

    with pytest.raises(BenchError, match=f"the graph step has no panel {panel}"):
        render(graph, tmp_path / "step.png")

    assert not (tmp_path / "step.png").exists()


def test_the_panels_share_one_axis_and_carry_their_labels(
    tmp_path: Path, drawn: list[Canvas]
) -> None:
    render(step(3), tmp_path / "step.png")

    (figure,) = drawn
    top, middle, bottom = figure.axes
    assert [axis.get_ylabel() for axis in figure.axes] == [
        "Panel 0 (V)",
        "Panel 1 (V)",
        "Panel 2 (V)",
    ]
    assert (top.get_title(), middle.get_title(), bottom.get_title()) == (
        "A step and its answer",
        "",
        "",
    )
    assert (top.get_xlabel(), middle.get_xlabel(), bottom.get_xlabel()) == ("", "", "Time (s)")
    assert top.get_shared_x_axes().joined(top, bottom)
    assert [axis.get_yscale() for axis in figure.axes] == ["linear"] * 3
    assert [axis.get_xscale() for axis in figure.axes] == ["linear"] * 3
    assert figure.get_dpi() == 110
    assert tuple(figure.get_size_inches()) == pytest.approx((9.0, 0.9 + 3 * 2.7))


def test_the_curves_take_the_colors_in_turn_in_each_panel(
    tmp_path: Path, drawn: list[Canvas]
) -> None:
    traces = [Trace(TIME, TIME + number, f"curve {number}", 0) for number in range(11)]
    traces += [Trace(TIME, -TIME, "dashed", 1, "--"), Trace(TIME, TIME, "dotted", 1, ":")]
    graph = Graph(
        "many", "Many curves", "Time (s)", (Panel("First (V)"), Panel("Second (V)")), tuple(traces)
    )

    render(graph, tmp_path / "many.png")

    first, second = drawn[0].axes
    colors = [line.get_color() for line in first.lines]
    assert len(first.lines) == 11
    assert len(set(colors[:10])) == 10
    # The eleventh curve starts the colors again, and so does the next panel.
    assert colors[10] == colors[0] == "#1f77b4"
    assert [line.get_color() for line in second.lines] == colors[:2]
    assert [line.get_linestyle() for line in second.lines] == ["--", ":"]
    assert [line.get_linestyle() for line in first.lines] == ["-"] * 11
    assert np.array_equal(first.lines[3].get_ydata(), TIME + 3)
    assert np.array_equal(first.lines[3].get_xdata(), TIME)


def test_a_panel_has_a_legend_when_one_of_its_curves_has_a_label(
    tmp_path: Path, drawn: list[Canvas]
) -> None:
    graph = Graph(
        "legend",
        "Legends",
        "Time (s)",
        (Panel("Named (V)"), Panel("Not named (V)"), Panel("Empty (V)")),
        (
            Trace(TIME, TIME, "sense", 0),
            Trace(TIME, 2 * TIME, "", 0),
            Trace(TIME, 3 * TIME, "burden", 0),
            Trace(TIME, TIME, "", 1),
        ),
    )

    render(graph, tmp_path / "legend.png")

    named, unnamed, empty = drawn[0].axes
    legend = named.get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == ["sense", "burden"]
    assert unnamed.get_legend() is None
    assert empty.get_legend() is None
    assert len(empty.lines) == 0


def test_the_axes_can_be_logarithmic(tmp_path: Path, drawn: list[Canvas]) -> None:
    frequency = np.logspace(1, 6, 60)
    graph = Graph(
        "bode",
        "A response",
        "Frequency (Hz)",
        (Panel("Magnitude", log=True), Panel("Phase (deg)")),
        (
            Trace(frequency, 1.0 / np.hypot(1.0, frequency / 1e3), "magnitude", 0),
            Trace(frequency, -np.degrees(np.arctan(frequency / 1e3)), "phase", 1),
        ),
        logx=True,
    )

    render(graph, tmp_path / "bode.png")

    magnitude, phase = drawn[0].axes
    assert (magnitude.get_yscale(), phase.get_yscale()) == ("log", "linear")
    assert (magnitude.get_xscale(), phase.get_xscale()) == ("log", "log")
    assert png_size(tmp_path / "bode.png") == (990, 693)


def test_the_levels_of_a_panel_are_lines_with_their_labels_at_alternating_ends(
    tmp_path: Path, drawn: list[Canvas]
) -> None:
    marks = ((0.9, "upper limit"), (0.1, "lower limit"), (0.5, "expected"))
    graph = Graph(
        "limits",
        "Limits",
        "Time (s)",
        (Panel("Marked (V)", marks=marks), Panel("Plain (V)")),
        (Trace(TIME, TIME, "ramp", 0), Trace(TIME, TIME, "ramp", 1)),
    )

    render(graph, tmp_path / "limits.png")

    marked, plain = drawn[0].axes
    levels = [line for line in marked.lines if line.get_linestyle() == "--"]
    labels = notes_of(marked)
    assert [float(np.asarray(line.get_ydata())[0]) for line in levels] == [0.9, 0.1, 0.5]
    assert [label.get_text() for label in labels] == ["upper limit", "lower limit", "expected"]
    assert [label.get_horizontalalignment() for label in labels] == ["right", "left", "right"]
    assert [label.xy for label in labels] == [(1.0, 0.9), (0.0, 0.1), (1.0, 0.5)]
    assert len(plain.lines) == 1
    assert notes_of(plain) == []


def test_the_events_of_a_graph_are_lines_through_every_panel_named_on_the_first(
    tmp_path: Path, drawn: list[Canvas]
) -> None:
    graph = step(3, xmarks=((0.25, "step up"), (0.75, "step down")))

    render(graph, tmp_path / "events.png")

    for axis in drawn[0].axes:
        events = [line for line in axis.lines if line.get_linestyle() == ":"]
        assert [float(np.asarray(line.get_xdata())[0]) for line in events] == [0.25, 0.75]
    top, middle, bottom = drawn[0].axes
    assert [(label.get_text(), label.xy) for label in notes_of(top)] == [
        ("step up", (0.25, 1.0)),
        ("step down", (0.75, 1.0)),
    ]
    assert notes_of(middle) == []
    assert notes_of(bottom) == []


def test_a_graph_without_a_curve_is_still_drawn(tmp_path: Path, drawn: list[Canvas]) -> None:
    graph = Graph("bare", "No curve yet", "Time (s)", (Panel("Voltage (V)"),), ())

    render(graph, tmp_path / "bare.png")

    assert png_size(tmp_path / "bare.png") == (990, 396)
    assert drawn[0].axes[0].get_legend() is None
