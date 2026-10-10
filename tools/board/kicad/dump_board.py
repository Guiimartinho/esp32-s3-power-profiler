"""Dump a KiCad board into a JSON file that plain Python can work with.

Usage, with the Python that KiCad ships (it has the ``pcbnew`` module):

    python dump_board.py <board.kicad_pcb> <out.json>

All coordinates are millimeters in the coordinates of the board editor. The
dump holds the nets with their net classes, the footprints with their
courtyards, the pads (as polygons), the tracks, the vias, the zones with
their filled polygons, and the drawings.

The zones are dumped as the board file stores them: fill the zones in the
board editor and save before dumping, or the copper of the pours is stale.

This script is the only part of the board figures that needs KiCad. It is
an adapter, kept apart from the package and from its tests: the package
reads the JSON and never imports ``pcbnew``.
"""

import json
import sys

import pcbnew

MM = 1e-6
COPPER = [
    (pcbnew.F_Cu, "F.Cu"),
    (pcbnew.In1_Cu, "In1.Cu"),
    (pcbnew.In2_Cu, "In2.Cu"),
    (pcbnew.B_Cu, "B.Cu"),
]
NAME = dict(COPPER)


def mm(value):
    """A length of the board file, which counts in nanometers, in millimeters."""
    return round(value * MM, 5)


def box(rect):
    """A bounding box as [left, top, right, bottom]."""
    return [mm(rect.GetLeft()), mm(rect.GetTop()), mm(rect.GetRight()), mm(rect.GetBottom())]


def chain_points(chain):
    """The corners of one outline."""
    return [[mm(chain.CPoint(i).x), mm(chain.CPoint(i).y)] for i in range(chain.PointCount())]


def poly_set(polys):
    """A SHAPE_POLY_SET as a list of {"outline": [...], "holes": [[...], ...]}."""
    out = []
    for i in range(polys.OutlineCount()):
        entry = {"outline": chain_points(polys.Outline(i)), "holes": []}
        for k in range(polys.HoleCount(i)):
            entry["holes"].append(chain_points(polys.Hole(i, k)))
        out.append(entry)
    return out


def reference_text(footprint):
    """Where the reference of a footprint stands on the silkscreen, or None."""
    try:
        field = footprint.Reference()
        return {
            "x": mm(field.GetPosition().x),
            "y": mm(field.GetPosition().y),
            "rot": round(field.GetTextAngleDegrees(), 3),
            "visible": bool(field.IsVisible()),
            "layer": NAME.get(field.GetLayer(), str(field.GetLayer())),
            "bbox": box(field.GetBoundingBox()),
        }
    except Exception:
        return None


def courtyard(footprint):
    """The front courtyard of a footprint as polygons, empty if it has none."""
    try:
        footprint.BuildCourtyardCaches()
        return poly_set(footprint.GetCourtyard(pcbnew.F_CrtYd))
    except Exception:
        return []


def footprint_entry(footprint):
    """One footprint: reference, value, place and outline boxes."""
    return {
        "ref": str(footprint.GetReference()),
        "value": str(footprint.GetValue()),
        "fpid": str(footprint.GetFPID().GetLibItemName().wx_str()),
        "x": mm(footprint.GetPosition().x),
        "y": mm(footprint.GetPosition().y),
        "rot": round(footprint.GetOrientationDegrees(), 3),
        "layer": NAME.get(footprint.GetLayer(), str(footprint.GetLayer())),
        "bbox": box(footprint.GetBoundingBox(False)),
        "dnp": bool(footprint.IsDNP()) if hasattr(footprint, "IsDNP") else False,
        "ref_text": reference_text(footprint),
        "courtyard": courtyard(footprint),
    }


def pad_outline(pad, layer):
    """The copper of a pad on a layer as one outline, empty if KiCad gives none."""
    polys = pcbnew.SHAPE_POLY_SET()
    try:
        pad.TransformShapeToPolygon(polys, layer, 0, 2000, pcbnew.ERROR_INSIDE)
        shape = poly_set(polys)
    except Exception:
        shape = []
    return shape[0]["outline"] if shape else []


def pad_size(pad, layer):
    """The size of a pad; newer versions of KiCad ask for the layer."""
    try:
        return pad.GetSize(layer)
    except TypeError:
        return pad.GetSize()


def pad_entry(ref, pad):
    """One pad, or None for a pad without copper (a mounting hole, paste only)."""
    layers = [label for layer, label in COPPER if pad.IsOnLayer(layer)]
    if not layers:
        return None
    first = next(layer for layer, label in COPPER if pad.IsOnLayer(layer))
    size = pad_size(pad, first)
    drill = pad.GetDrillSize()
    return {
        "ref": ref,
        "num": str(pad.GetNumber()),
        "net": str(pad.GetNetname()),
        "x": mm(pad.GetPosition().x),
        "y": mm(pad.GetPosition().y),
        "w": mm(size.x),
        "h": mm(size.y),
        "rot": round(pad.GetOrientationDegrees(), 3),
        "layers": layers,
        "drill": mm(max(drill.x, drill.y)),
        "poly": pad_outline(pad, first),
        "uuid": pad.m_Uuid.AsString(),
    }


def via_entry(via):
    """One via: place, diameter of its copper, drill and the layers it joins."""
    return {
        "uuid": via.m_Uuid.AsString(),
        "net": str(via.GetNetname()),
        "x": mm(via.GetPosition().x),
        "y": mm(via.GetPosition().y),
        "d": mm(via.GetWidth(pcbnew.F_Cu)),
        "drill": mm(via.GetDrillValue()),
        "top": NAME.get(via.TopLayer(), "?"),
        "bottom": NAME.get(via.BottomLayer(), "?"),
    }


def track_entry(track):
    """One track segment: its two ends and its width."""
    return {
        "uuid": track.m_Uuid.AsString(),
        "net": str(track.GetNetname()),
        "layer": NAME.get(track.GetLayer(), str(track.GetLayer())),
        "x1": mm(track.GetStart().x),
        "y1": mm(track.GetStart().y),
        "x2": mm(track.GetEnd().x),
        "y2": mm(track.GetEnd().y),
        "w": mm(track.GetWidth()),
    }


def zone_clearance(zone):
    """The clearance set on a zone, or None when it takes the one of its net class."""
    try:
        clearance = zone.GetLocalClearance()
        return mm(clearance) if isinstance(clearance, int) else None
    except Exception:
        return None


def zone_fill(zone, layer):
    """The filled polygons of a zone on a layer, as the board file stores them."""
    try:
        return poly_set(zone.GetFilledPolysList(layer))
    except Exception:
        return []


def zone_entry(zone):
    """One zone: a copper pour with its fills, or a rule area with what it forbids."""
    entry = {
        "uuid": zone.m_Uuid.AsString(),
        "net": str(zone.GetNetname()),
        "name": str(zone.GetZoneName()),
        "layers": [label for layer, label in COPPER if zone.IsOnLayer(layer)],
        "rule_area": bool(zone.GetIsRuleArea()),
        "priority": zone.GetAssignedPriority(),
        "outline": poly_set(zone.Outline()),
        "fills": {},
    }
    if zone.GetIsRuleArea():
        entry["no_tracks"] = bool(zone.GetDoNotAllowTracks())
        entry["no_vias"] = bool(zone.GetDoNotAllowVias())
        entry["no_pour"] = bool(zone.GetDoNotAllowZoneFills())
        return entry
    entry["clearance"] = zone_clearance(zone)
    entry["min_width"] = mm(zone.GetMinThickness())
    entry["connect"] = {
        pcbnew.ZONE_CONNECTION_FULL: "solid",
        pcbnew.ZONE_CONNECTION_THERMAL: "thermal",
        pcbnew.ZONE_CONNECTION_THT_THERMAL: "tht_thermal",
        pcbnew.ZONE_CONNECTION_NONE: "none",
    }.get(zone.GetPadConnection(), "solid")
    never = zone.GetIslandRemovalMode() == pcbnew.ISLAND_REMOVAL_MODE_NEVER
    entry["islands"] = "never" if never else "always"
    for layer, label in COPPER:
        if zone.IsOnLayer(layer):
            entry["fills"][label] = zone_fill(zone, layer)
    return entry


def polygon_points(item):
    """The corners of a drawn polygon, empty if KiCad gives none."""
    try:
        return poly_set(item.GetPolyShape())[0]["outline"]
    except Exception:
        return []


def drawing_entry(board, item):
    """One drawing: a shape or a text on any layer."""
    kind = item.GetClass()
    entry = {
        "layer": str(board.GetLayerName(item.GetLayer())),
        "kind": str(kind),
        "uuid": item.m_Uuid.AsString(),
    }
    if kind == "PCB_SHAPE":
        shape = item.ShowShape() if hasattr(item, "ShowShape") else item.GetShape()
        entry["shape"] = str(shape)
        entry["start"] = [mm(item.GetStart().x), mm(item.GetStart().y)]
        entry["end"] = [mm(item.GetEnd().x), mm(item.GetEnd().y)]
        entry["width"] = mm(item.GetWidth())
        if item.GetShape() == pcbnew.SHAPE_T_POLY:
            entry["points"] = polygon_points(item)
    elif kind in ("PCB_TEXT", "PCB_TEXTBOX"):
        entry["text"] = str(item.GetText())
        entry["at"] = [mm(item.GetPosition().x), mm(item.GetPosition().y)]
    return entry


def dump(board):
    """The whole board as one dictionary."""
    data = {
        "nets": {},
        "footprints": [],
        "pads": [],
        "tracks": [],
        "vias": [],
        "zones": [],
        "drawings": [],
    }
    for name, net in board.GetNetsByName().items():
        if str(name):
            data["nets"][str(name)] = {
                "class": str(net.GetNetClassName()),
                "code": net.GetNetCode(),
            }
    data["edge"] = box(board.GetBoardEdgesBoundingBox())
    for footprint in board.GetFootprints():
        entry = footprint_entry(footprint)
        data["footprints"].append(entry)
        pads = (pad_entry(entry["ref"], pad) for pad in footprint.Pads())
        data["pads"].extend(pad for pad in pads if pad is not None)
    for track in board.GetTracks():
        if track.Type() == pcbnew.PCB_VIA_T:
            data["vias"].append(via_entry(track))
        else:
            data["tracks"].append(track_entry(track))
    data["zones"] = [zone_entry(zone) for zone in board.Zones()]
    data["drawings"] = [drawing_entry(board, item) for item in board.GetDrawings()]
    return data


def main(arguments):
    """Dump the board named first into the file named second."""
    if len(arguments) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    board = pcbnew.LoadBoard(arguments[0])
    board.BuildConnectivity()
    data = dump(board)
    with open(arguments[1], "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    print(", ".join(f"{key} {len(data[key])}" for key in data if key != "edge"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
