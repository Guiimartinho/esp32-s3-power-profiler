"""Graphs of the waveforms, as PNG files.

The graphs are drawn without a display and without the state machine of
pyplot, so that benches can be rendered from several threads and the files
do not depend on the machine: fixed size, fixed colors, no time stamp.
"""

from __future__ import annotations

import io
import pathlib

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure as Canvas
from PIL import Image

from circuit_sim.bench import Graph
from circuit_sim.errors import BenchError

_COLORS = (
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#ff7f0e",
    "#9467bd",
    "#8c564b",
    "#17becf",
    "#7f7f7f",
    "#bcbd22",
    "#e377c2",
)
_WIDTH = 9.0
_PANEL_HEIGHT = 2.7
_DPI = 110


_PALETTE = 128
"""Colors a filed graph keeps: lines, grid and text need no more."""


def compact_png(data: bytes) -> bytes:
    """Encode a PNG again with a palette, a third to a quarter of its size.

    The graphs are lines on white. A palette of 128 colors keeps the lines
    and the smooth edges of the text, and the results of a hundred benches
    stay small enough to be filed.
    """
    with Image.open(io.BytesIO(data)) as image:
        reduced = image.convert("RGB").quantize(
            colors=_PALETTE, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
        packed = io.BytesIO()
        reduced.save(packed, format="PNG", optimize=True)
    return packed.getvalue()


def render(graph: Graph, path: pathlib.Path) -> None:
    """Draw a graph and write it to a file.

    Args:
        graph: The panels and the curves.
        path: The PNG file to write.

    Raises:
        BenchError: When the graph has no panel, or a curve names a panel
            that does not exist.
    """
    count = len(graph.panels)
    if count == 0:
        raise BenchError(f"the graph {graph.name} has no panel")
    for trace in graph.traces:
        if not 0 <= trace.panel < count:
            raise BenchError(f"the graph {graph.name} has no panel {trace.panel}")
    canvas = Canvas(figsize=(_WIDTH, 0.9 + _PANEL_HEIGHT * count), dpi=_DPI)
    FigureCanvasAgg(canvas)
    axes = canvas.subplots(count, 1, sharex=True, squeeze=False)[:, 0]
    used = [0] * count
    for trace in graph.traces:
        axis = axes[trace.panel]
        color = _COLORS[used[trace.panel] % len(_COLORS)]
        used[trace.panel] += 1
        axis.plot(
            trace.x, trace.y, trace.style, color=color, linewidth=1.3, label=trace.label or None
        )
    for index, panel in enumerate(graph.panels):
        axis = axes[index]
        axis.set_ylabel(panel.ylabel)
        if panel.log:
            axis.set_yscale("log")
        if graph.logx:
            axis.set_xscale("log")
        for position, (level, label) in enumerate(panel.marks):
            # Labels alternate between the two ends so that neighbors stay apart.
            right = position % 2 == 0
            axis.axhline(level, color="#444444", linewidth=0.8, linestyle="--")
            axis.annotate(
                label,
                xy=(1.0 if right else 0.0, level),
                xycoords=("axes fraction", "data"),
                xytext=(-4 if right else 4, 3),
                textcoords="offset points",
                ha="right" if right else "left",
                fontsize=7.5,
                color="#444444",
            )
        for instant, label in graph.xmarks:
            axis.axvline(instant, color="#888888", linewidth=0.8, linestyle=":")
            if index == 0:
                axis.annotate(
                    label,
                    xy=(instant, 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(3, -10),
                    textcoords="offset points",
                    fontsize=7.5,
                    color="#555555",
                )
        axis.grid(True, which="both", linewidth=0.4, color="#cccccc")
        if any(trace.label for trace in graph.traces if trace.panel == index):
            axis.legend(loc="best", fontsize=8, framealpha=0.85)
    axes[-1].set_xlabel(graph.xlabel)
    axes[0].set_title(graph.title, fontsize=11)
    canvas.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    drawn = io.BytesIO()
    canvas.savefig(drawn, format="png", dpi=_DPI, metadata={"Software": None})
    path.write_bytes(compact_png(drawn.getvalue()))
