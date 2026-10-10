# Board Figures

A small Python package that calculates, from the KiCad board file of the
carrier, the figures that the documents quote for its layout: the
resistance of the 1 A path, whether a loop closes on one layer, the lengths
of the Kelvin pairs and the surface leakage into the measured node.

Everything here is calculated from the drawn copper. Nothing is measured on
hardware: no board is built. The figures compare one layout with another
and show whether a layout rule of section 10 of the
[specification](../../docs/specification.md) is kept. They do not predict
what a bench will read.

## Status

- The package exists with five commands: `squares`, `path`, `pairs`,
  `leakage` and `report`.
- It is tested without hardware and without KiCad: 260 tests on small
  synthetic boards, lines and branches covered to 100 %, ruff and mypy in
  strict mode without a finding, the wheel builds and installs. All of
  that ran on one Windows machine. The workflow `Tools` has not been
  started yet.
- On the board in `hardware/kicad/` it gives the figures that the
  documents quote: 19.5 squares (10.4 mΩ) in source mode and 23.3 squares
  (12.3 mΩ) in ampere mode for the 1 A path, a surface leakage into the
  measured node of 4.46 nA on the top layer and 0.67 nA on the bottom
  layer, the lengths of the three Kelvin pairs, and 10 of 11 sense and
  guarded nets without a via. All of them are calculated from the drawn
  copper.
- Missing: an automated test of the dump adapter, which needs KiCad; the
  scripts that drew the layout and the simulation files, which are not in
  the repository; and any comparison with a built board.
- Next: the first board replaces these figures with bench readings, and
  the temperature rise of the linear regulator (D-93) is read there, not
  calculated here.

## Why

The layout rules of the specification are written as numbers: at most
30 squares in the 1 A path, no via in a sense net, pairs of equal length,
a surface leakage into the measured node inside its budget of 10 nA. A
design rules check does not answer any of them. These scripts do, the same
way every time, so that a figure in a document can be calculated again from
the board file it describes, and so that a change of the layout shows as a
change of the figure.

## Parts

| Path | Content |
| --- | --- |
| `src/board_figures/` | The package. The calculations are pure functions on an immutable model of the board and know nothing of files, KiCad or the command line |
| `kicad/dump_board.py` | The adapter that runs under the Python of KiCad and writes the board as JSON. The only part that needs KiCad |
| `carrier.toml` | The definition for the carrier board: every net name, pad and assumption behind a figure |
| `tests/` | pytest, on small synthetic boards with answers known by hand. No test needs KiCad or the real board |

Inside the package:

| Module | Content |
| --- | --- |
| `model` | The board as frozen dataclasses: nets, pads, tracks, vias, zone fills |
| `loader` | From the JSON dump to the model, with a clear error for a malformed dump |
| `geometry`, `raster` | The copper of a net on a layer as shapes, and shapes on a grid of cells |
| `resistance` | Squares of copper between two groups of pads |
| `path` | A path between two pads on one layer alone |
| `pairs` | Length of a track along its center line |
| `leakage` | Surface leakage into the measured node |
| `definition` | The board definition file as value objects |
| `report` | The figures of a definition put together, and their text |
| `cli` | The command `board-figures` |
| `sketch` | Small boards built from rectangles, for tests and hand checks |

## Install

Python 3.10 or later. From this directory:

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"    # Windows
.venv/bin/python -m pip install -e ".[dev]"        # Linux, macOS
```

The package needs numpy, scipy and shapely. The `dev` extra adds the test
and lint tools.

The examples below call the command as `board-figures` and the interpreter
as `python`. Both are those of this environment, so activate it first:

```sh
source .venv/Scripts/activate    # Windows, Git Bash
source .venv/bin/activate        # Linux, macOS
```

Without activating it, write `.venv/Scripts/board-figures` and
`.venv/Scripts/python` (`.venv/bin/` on Linux and macOS) in their place.

## Make the Dump

The package does not read a `.kicad_pcb` file. The adapter
`kicad/dump_board.py` does, with the `pcbnew` module, and so it has to run
under the Python that KiCad ships, not under the environment above. Where
that Python is depends on the installation: on Windows it is
`bin/python.exe` in the folder KiCad was installed to, on macOS it lies
inside the application bundle, and on Linux it is usually the `python3` of
the system. Put its path into the environment variable `KICAD_PYTHON` and
run, from the root of the repository:

```sh
"$KICAD_PYTHON" tools/board/kicad/dump_board.py \
    hardware/kicad/power-profiler-carrier.kicad_pcb tools/board/board.json
```

The adapter prints what it wrote:

```text
nets 258, footprints 425, pads 1273, tracks 3716, vias 694, zones 45, drawings 127
```

The zones are dumped as the board file stores them. Fill the zones in the
board editor and save before dumping. The dump is a working file of a few
megabytes and stays out of the repository: the `.gitignore` of this
directory leaves out every `.json` file in it.

All coordinates of the dump are millimeters in the coordinates of the board
editor, x to the right and y downward.

## Commands

Every command takes the dump and prints plain text. The commands that need
the definition read `carrier.toml` from the working directory unless
`--definition` names another file; the examples below run in this directory
with the dump of the carrier board as `board.json`. The outputs shown are
those of the board in `hardware/kicad/` at the time of writing.

Exit status: 0 on success, 1 when a file or the board does not allow the
calculation (and for `path` when there is no path), 2 on a usage error.

Net names are written as KiCad shows them, and most begin with a slash. Git
Bash on Windows takes an argument that begins with a slash for a path and
puts the folder of its own installation in front of it; the command then
answers that the board has no net of that longer name. Turn that off for
the session before running the examples:

```sh
export MSYS_NO_PATHCONV=1    # Git Bash on Windows only
```

### `squares`: Resistance of a Piece of Copper

```sh
board-figures squares board.json --net "/Monitors/VIN_P" --from F1.2 --to Q5.5
```

```text
/Monitors/VIN_P: from F1.2 to Q5.5: 7.99 squares, 4.25 mOhm at 40 C (calculated from the drawn copper; grid 0.1 mm; copper area 96.5 mm2 on 3 layers)
```

`--from` and `--to` each take one pad or several; the pads of a group are
held at one potential. `--grid` and `--layers` replace the values of the
definition.

### `path`: One Layer Alone

```sh
board-figures path board.json --net "/Shunt Ladder/INN" --from U24.9 --to U27.1
```

```text
/Shunt Ladder/INN: 0 vias; tracks on F.Cu
path from U24.9 to U27.1 on F.Cu alone: 16.61 mm between the pad edges
```

When the copper of the layer does not join the pads, the second line says
`NO path ...` and the exit status is 1. `--layer` chooses the layer,
`--grid` the cell size (0.05 mm).

### `pairs`: Center-Line Lengths

```sh
board-figures pairs board.json
```

```text
range 3 shunt to multiplexer: Net-(U24-S4A): 46.31 mm; Net-(U24-S4B): 45.42 mm; difference 0.89 mm (center lines, pad edge to pad edge)
range 2 shunt to multiplexer: Net-(U24-S3A): 28.35 mm; Net-(U24-S3B): 27.78 mm; difference 0.56 mm (center lines, pad edge to pad edge)
multiplexer to amplifier: /Shunt Ladder/INP: 17.01 mm; /Shunt Ladder/INN: 17.89 mm; difference 0.88 mm (center lines, pad edge to pad edge)
```

Without options it prints the pairs of the definition. One pair can be
given on the command line instead, each conductor as a net and two pads:
`--first NET REF.PAD REF.PAD --second NET REF.PAD REF.PAD`.

### `leakage`: Surface Leakage Into the Measured Node

```sh
board-figures leakage board.json --layer B.Cu
```

```text
Surface leakage on B.Cu (raster 0.04 mm, reach 3 mm, 81290 cells)
   into the measured node: 0.67 nA (13.4 squares of length over gap), 0.00 nA inside the can, 0.67 nA outside (calculated, 1e+11 ohm per square)
     0.34 nA      6.8 squares  5 V  GND
     0.33 nA      6.7 squares  5 V  /Output Stage/VIN_RAW
```

The list names the foreign nets that the current comes from, the largest
first; `--top` sets how many. `--grid`, `--reach` and `--window` replace
the values of the definition. On the top layer of the carrier the command
gives 4.46 nA, of which 0.73 nA inside the shield can.

### `report`: Everything the Definition Asks For

```sh
board-figures report board.json
```

```text
Figures of the board, calculated from the drawn copper. Nothing is measured.
The 1 A path (limit: 30 squares in either mode)
   source mode: 19.5 squares = 10.4 mOhm at 40 C
      regulator output                 /Path Switching/LDO_OUT         2.2
      source pair, common source       Net-(D18-A)                     0.4
      supply node                      /Path Switching/SUPPLY          6.5
      range 3 transistor to shunt      Net-(Q14-S-Pad1)                1.3
      ladder output                    /Output Stage/VOUT_S            5.6
      output pair, common source       Net-(Q15-S-Pad1)                0.6
      VOUT to the terminal             Net-(D21-K)                     2.9
   ampere mode: 23.3 squares = 12.3 mOhm at 40 C
      VIN terminal to fuse             /Output Stage/VIN_RAW           3.5
      fuse to ampere pair              /Monitors/VIN_P                 8.0
      ampere pair, common source       Net-(D19-A)                     0.3
      supply node                      /Path Switching/SUPPLY          1.0
      ...
Kelvin pairs (track center lines, pad edge to pad edge)
   range 3 shunt to multiplexer: 46.31 / 45.42 mm, difference 0.89 mm
   ...
Sense and guarded nets: 10 of 11 without a via
   ...
Track widths (share of the track length at the class width or wider)
   ...
Mounting holes: 4 holes; tracks nearer than 4 mm to a center: 0
Shield can: 32 lands, 32 with a ground via within 1.5 mm, 0 without
Surface leakage on F.Cu (raster 0.04 mm, reach 3 mm, 427410 cells)
   into the measured node: 4.46 nA (72.3 squares of length over gap), 0.73 nA inside the can, 3.73 nA outside (calculated, 1e+11 ohm per square)
   ...
```

The whole report takes about ten seconds on the carrier board.
`--skip-path` and `--skip-leakage` leave out the two parts that take the
longest.

The sum of a mode adds its pieces as they were solved, and every figure is
rounded only where it is printed. The printed pieces can therefore add to
0.1 square more or less than the printed sum: the pieces of the ampere mode
add to 23.25 squares, which prints as 23.3, while the pieces as printed add
to a tenth of a square less.

The design rules check is not part of the report: it is the work of KiCad
(see the [hardware guide](../../hardware/README.md)).

## The Definition File

`carrier.toml` holds what is specific to the carrier board, so that no net
name and no pad is typed in Python:

- the copper: the layers that carry current, the thickness of each layer,
  the resistance of a square, the squares of a via;
- the pieces of the 1 A path in source mode and in ampere mode, each as a
  net with the pads where the current enters and leaves it;
- the three Kelvin pairs;
- for the leakage: the net classes that make up the measured node, the
  nets that follow it, the voltage rule, the sheet resistance, the window
  and the rectangle of the shield can;
- the net classes that should have no via, the track width of each net
  class, the keep-out of the mounting holes and the rule for the lands of
  the shield can.

A renamed net or a renumbered part changes this file. A pad that the board
does not have, or that sits on another net than the file says, stops the
command with a message that names it.

## Method and Assumptions

### Squares

One square is the resistance of a square piece of copper measured between
two opposite sides. It does not depend on the size of the square, only on
the thickness of the copper: a strip of length L and width W has L / W
squares. Squares are counted in copper of 35 µm, the outer layers; one
square is taken as 0.531 mΩ at 40 °C. An inner layer has 17.5 µm, so the
same shape counts double there.

The copper of the net on each layer (pads, tracks, vias and the filled
polygons of the zones, as KiCad filled them) is laid on a grid of cells of
0.1 mm. Neighboring copper cells of a layer are joined by one square of
that layer. The pads of the first group are held at one potential, the pads
of the second at another, the potentials of all other cells are solved, and
the current that flows gives the resistance.

How vias count: a via joins the layers at the one cell that holds its
center. A via of 0.4 mm drill counts 1.7 squares from one layer to the next
(25 µm of plating over 1.6 mm of board), another drill in inverse
proportion. The layers solved are the top, the second inner layer and the
bottom, so a via from the top to the bottom passes the inner layer and
counts twice. That overstates a via; the figure errs to the high side. The
plated hole of a through-hole pad counts 0.5 squares. The first inner layer
is the ground plane and takes no part.

What is left out: the parts between the pieces (transistors, the shunt,
the fuse, the terminal), solder, the heating of the copper by its own
current, and the current in the plane under the path.

### The Grid

A polygon is laid on the grid by one rule, in `raster.py`: every corner
moves to the sample point of a cell at or before it, and the moved outline
is filled including its boundary. The rule draws copper wider than it is,
by up to one cell. On the grid of 0.1 mm a track of 1.5 mm is drawn up to
0.1 mm too wide, so its resistance reads up to 7 % low; a wide pour is
hardly touched. The distance between two conductors comes out right to one
cell, either way: on the leakage raster of 0.04 mm that is up to 8 % of a
gap of 0.5 mm. The rule is the one the figures in the documents of the
board were calculated with, and it is kept so that old and new figures
compare.

The cell size moves the figures of the carrier board as follows. On a grid
of 0.05 mm the two sums of the 1 A path read about 2 % higher than on the
grid of 0.1 mm of the definition: 19.9 squares in source mode and
23.8 squares in ampere mode, against 19.5 and 23.3. The leakage figure is
converged at its raster of 0.04 mm.

### Path on One Layer

The copper of the net on one layer is laid on a grid of 0.05 mm; vias count
only as the dot of copper they have on that layer. The shortest way from
the first pad to the second through copper cells is searched, with steps to
the eight neighbors of a cell. The length is from pad edge to pad edge and
cuts the corners of a meander, so it is shorter than the track. It is good
to one cell: where a corner lies between two sample points, the place of the
grid decides on which side it falls. The grid starts 0.3 mm outside the
copper of the net, as it did for the lengths in the documents of the board.

A pad counts only on a layer it has copper on. Two surface pads on the top
have no path on the bottom, even where a pour of their net lies under both.

### Pair Lengths

The tracks of a net are a graph of their center lines. A track end that
lies on another track, or within 0.03 mm of it, is joined to it. The length
is the shortest way along the center lines from the first pad to the
second; a track end inside a pad counts from there. Layers are not told
apart: tracks that meet at a via are joined, and the via adds no length.
A conductor that runs through a zone has no center line there and reads as
not joined.

### Leakage

The copper of one outer layer inside a window around the measured node is
laid on a raster of 0.04 mm. Every cell is one of four things:

- the measured node: every net of the classes Sense, Guarded and Node1A;
- a follower: the guard, the output of the guard buffer, the supply node
  and the gates of the two ladder clamps. They sit at the potential of the
  node, or within the burden voltage of it, and feed no current into it;
- foreign copper: every other conductor;
- bare laminate.

The bare laminate within 3 mm of the node is solved as a resistive sheet,
with the node and its followers at 0 and the foreign copper at 1. The
current into the node is summed in squares of length over gap: two parallel
edges of length L at a gap g give L / g. Each piece of the current is
booked to the nearest foreign conductor and multiplied by the voltage
assumed for it: 5 V to ground and logic, 7 V to the +12 V rail and to gate
nodes, 9 V to the −4 V rail. The sheet resistance is taken as 10¹¹ Ω per
square, the assumption of section 10.3 of the specification for a clean
board surface.

What the leakage figure leaves out: the solder mask, flux residue,
moisture and dust, the leakage through the laminate to the inner layers,
the leakage of the parts themselves (the suppressor, the switches, the
amplifier inputs), and the bottom of parts that bridge two conductors. The
sheet resistance of a real surface can be orders of magnitude off the
assumed value in either direction. The figure ranks layouts and shows where
the current would come from; it is not an error budget.

## Limits

- It compares layouts and does not predict a measurement. A bench result
  replaces every figure here.
- It reads what is drawn. Zones that were not filled before the dump, or a
  board that fails its design rules check, give figures of a board that
  does not exist.
- The figures depend on the cell size and on the raster rule. Compare
  figures made with the same grid only.
- The dump adapter follows the scripting interface of KiCad 10. Another
  version of KiCad may need changes in `kicad/dump_board.py`, which has no
  automated test.

## Checks

From the root of the repository, with the environment of this directory
(`tools/board/.venv/Scripts/python` on Windows, `tools/board/.venv/bin/python`
elsewhere):

```sh
python -m ruff check tools/board
python -m ruff format --check tools/board
```

From this directory:

```sh
python -m mypy
python -m pytest --cov
```

The whole run takes a few seconds. mypy runs in strict mode over the
package and its tests. The tests build small boards from rectangles and
compare with hand calculations: a strip of length L and width W is L / W
squares, two layers joined by vias halve it, an inner layer of half the
thickness counts double, two parallel strips leak L / g squares and nothing
past a guard between them. Coverage of lines and branches has a floor of
90 %. The adapter in `kicad/` is outside that measurement, because it
cannot run without KiCad.

The same checks are the workflow `Tools`, which is started by hand
(decision D-22 of the specification). It runs the tests on Linux, Windows
and macOS with the oldest and the newest supported Python, and builds the
wheel and installs it in a clean environment. It has not been started yet:
so far the checks ran on one Windows machine, with Python 3.11 and 3.10,
and neither Linux nor macOS has run them.
