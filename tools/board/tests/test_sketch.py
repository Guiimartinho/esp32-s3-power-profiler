from __future__ import annotations

from board_figures import sketch
from board_figures.model import DEFAULT_NET_CLASS, Footprint, Polygon


def test_a_rectangle_has_four_corners_in_order() -> None:
    assert sketch.rectangle((1.0, 2.0, 3.0, 5.0)) == (
        (1.0, 2.0),
        (3.0, 2.0),
        (3.0, 5.0),
        (1.0, 5.0),
    )


def test_a_pad_is_drawn_from_its_rectangle() -> None:
    pad = sketch.pad("J4.A3", "OUT", (1.0, 2.0, 3.0, 5.0), layers=("F.Cu", "B.Cu"), drill=0.8)

    assert (pad.ref, pad.number, pad.net) == ("J4", "A3", "OUT")
    assert pad.position == (2.0, 3.5)
    assert pad.size == (2.0, 3.0)
    assert pad.layers == ("F.Cu", "B.Cu")
    assert pad.drill == 0.8
    assert pad.outline == sketch.rectangle((1.0, 2.0, 3.0, 5.0))


def test_items_go_on_the_top_layer_unless_told_otherwise() -> None:
    assert sketch.pad("R1.1", "A", (0.0, 0.0, 1.0, 1.0)).layers == ("F.Cu",)
    assert sketch.track("A", (0.0, 0.0), (1.0, 0.0), 0.2).layer == "F.Cu"
    assert sketch.track("A", (0.0, 0.0), (1.0, 0.0), 0.2, layer="B.Cu").layer == "B.Cu"
    assert sketch.fill("A", (0.0, 0.0, 1.0, 1.0)).layer == "F.Cu"


def test_a_fill_is_one_polygon_with_its_holes() -> None:
    fill = sketch.fill("GND", (0.0, 0.0, 9.0, 9.0), priority=3, holes=((2.0, 2.0, 4.0, 4.0),))

    assert fill.priority == 3
    assert fill.polygons == (
        Polygon(sketch.rectangle((0.0, 0.0, 9.0, 9.0)), (sketch.rectangle((2.0, 2.0, 4.0, 4.0)),)),
    )


def test_a_board_sorts_its_items_and_lists_their_nets() -> None:
    hole = Footprint("H1", (5.0, 5.0))
    pad = sketch.pad("R1.1", "A", (0.0, 0.0, 1.0, 1.0))
    free = sketch.pad("R1.2", "", (2.0, 0.0, 3.0, 1.0))
    track = sketch.track("B", (0.0, 0.0), (1.0, 0.0), 0.2)
    via = sketch.via("C", (1.0, 0.0))
    fill = sketch.fill("D", (0.0, 0.0, 9.0, 9.0))

    board = sketch.board(via, fill, hole, track, pad, free, classes={"B": "Sense", "E": "Guard"})

    assert board.footprints == (hole,)
    assert board.pads == (pad, free)
    assert board.tracks == (track,)
    assert board.vias == (via,)
    assert board.fills == (fill,)
    assert {net.name: net.net_class for net in board.nets} == {
        "B": "Sense",
        "E": "Guard",
        "C": DEFAULT_NET_CLASS,
        "D": DEFAULT_NET_CLASS,
        "A": DEFAULT_NET_CLASS,
    }


def test_a_dump_has_the_sections_that_the_loader_reads() -> None:
    board = sketch.board(
        Footprint("H1", (5.0, 6.0)),
        sketch.pad("R1.1", "A", (0.0, 0.0, 1.0, 2.0)),
        sketch.track("A", (0.0, 0.0), (1.0, 0.0), 0.2),
        sketch.via("A", (1.0, 0.0)),
        sketch.fill("A", (0.0, 0.0, 9.0, 9.0), holes=((2.0, 2.0, 4.0, 4.0),)),
    )

    dump = sketch.to_dump(board)

    assert list(dump) == ["nets", "footprints", "pads", "tracks", "vias", "zones"]
    assert dump["nets"] == {"A": {"class": "Default"}}
    assert dump["footprints"] == [{"ref": "H1", "x": 5.0, "y": 6.0}]
    assert dump["tracks"] == [
        {"net": "A", "layer": "F.Cu", "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.0, "w": 0.2}
    ]
    assert dump["vias"] == [{"net": "A", "x": 1.0, "y": 0.0, "d": 0.6, "drill": 0.3}]
    assert dump["pads"] == [
        {
            "ref": "R1",
            "num": "1",
            "net": "A",
            "x": 0.5,
            "y": 1.0,
            "w": 1.0,
            "h": 2.0,
            "layers": ["F.Cu"],
            "drill": 0.0,
            "poly": [[0.0, 0.0], [1.0, 0.0], [1.0, 2.0], [0.0, 2.0]],
        }
    ]
    assert dump["zones"] == [
        {
            "net": "A",
            "rule_area": False,
            "priority": 0,
            "fills": {
                "F.Cu": [
                    {
                        "outline": [[0.0, 0.0], [9.0, 0.0], [9.0, 9.0], [0.0, 9.0]],
                        "holes": [[[2.0, 2.0], [4.0, 2.0], [4.0, 4.0], [2.0, 4.0]]],
                    }
                ]
            },
        }
    ]
