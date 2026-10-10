# Circuit Simulations

Simulations of the carrier board at circuit level: the circuits are taken
from the netlist of the schematic, run in ngspice, and their values and
waveforms are compared with the figures of
[the specification](../docs/specification.md).

Everything here is simulation. Nothing is measured on hardware, and a figure
that passes says only that the circuit as drawn, with the models named beside
the result, keeps its limit. The results are in [`results/`](results/README.md).

## Status

As of 2026-10-10. The circuits of draft A2 are simulated block by block from
the netlist of the final schematic: 134 benches, of which 93 run circuits of
the board in ten blocks and 41 put the models written for the project into
the test circuits of their datasheets. Every bench ran. A bench is one
circuit with its stimulus; it takes figures from the waveforms and judges
each one against its limit. The limit is a figure of the specification
where it states one; else a rating or a figure of a datasheet, a value
that the bench calculates, or a limit that the bench sets and names. In
the block `models` it is the figure of the datasheet with the tolerance
that this project asks of a model. Of the 3162 figures 1834 pass, 122
fail and 1206 carry no limit: they are values that nothing limits.

| Block | Circuits | Benches | Pass | Fail | No limit |
| --- | --- | --- | --- | --- | --- |
| [`ladder`](results/ladder/README.md) | Shunt ladder (section 4.3) | 2 | 20 | 0 | 6 |
| [`signal_chain`](results/signal_chain/README.md) | Signal chain (sections 4.5, 4.6 and 4.10) | 11 | 113 | 8 | 111 |
| [`range_logic`](results/range_logic/README.md) | Range control logic, with ladder, chain and output switch in the loop (section 4.4) | 12 | 143 | 6 | 122 |
| [`source_meter`](results/source_meter/README.md) | Source meter (section 4.2) | 12 | 176 | 3 | 247 |
| [`output_stage`](results/output_stage/README.md) | Output stage (sections 4.2 and 4.9) | 6 | 151 | 6 | 142 |
| [`path_switching`](results/path_switching/README.md) | Path switching (sections 4.2, 4.3 and 4.9) | 15 | 288 | 19 | 235 |
| [`power_input`](results/power_input/README.md) | Power input and logic supplies (sections 3, 4.1 and 4.11) | 13 | 190 | 27 | 113 |
| [`analog_rails`](results/analog_rails/README.md) | Analog rails and rail monitor (sections 3, 4.6 and 4.11) | 10 | 105 | 25 | 108 |
| [`digital`](results/digital/README.md) | Digital lines and monitors (sections 4.6 to 4.8, 4.11 and 5) | 10 | 145 | 11 | 49 |
| [`system`](results/system/README.md) | Whole measuring path, from the load current to the reading | 2 | 25 | 0 | 3 |
| Circuits of the board | Ten blocks | 93 | 1356 | 105 | 1136 |
| [`models`](results/models/README.md) | The models written here, in the test circuits of their datasheets | 41 | 478 | 17 | 70 |
| All | Eleven blocks | 134 | 1834 | 122 | 1206 |

What the counts rest on, and what they do not say:

- **Simulated, not measured.** No board exists. A figure that passes says
  that the circuit as drawn keeps its limit with the models named beside
  it. It does not say that a built board will.
- **The parts are the drawn ones.** A bench of the ten board blocks takes
  the parts that it simulates from `netlist/carrier.json`, a snapshot of
  the netlist of the schematic with its 428 parts, and types none of
  them. What stands around those parts is typed by the bench and named in
  its notes: sources, loads, cables, the device under test, and in some
  benches a stand-in for a neighboring block of the board, such as the
  boost converter as a load in `power_input` or the closed ampere path as
  one resistance in `range_logic`. Some runs change a part on purpose,
  with another value or with a position fitted, and say so. The benches
  of the block `models` use the test circuits of the datasheets, which
  are typed. On 2026-10-10 the snapshot matched the schematic in
  [`../hardware/kicad/`](../hardware/kicad/), checked with
  `circuit-sim netlist --check`. Schematic and snapshot hold the state
  before decisions D-95, D-96 and D-98 of the specification: 1 nF at
  C32 to C34, no position for a capacitor at U28, R14 and C5 without
  parts. Every result here is a result of that state.
- **The models are written here.** Every active part is a model written
  for this project from its datasheet, a typical part at room
  temperature. The 41 benches of the block `models` put these models
  into the test circuits of their datasheets; four models have no such
  bench: the analog multiplexer, the gate drivers, the BAV199 diode
  pairs and the fit that the two ladder clamp transistors take. The
  models of the manufacturers may not be copied into this repository.
  Where a copy was present, a second run took its value: 63 benches
  carry such a value in a column of their own, as a second opinion.
  [Limits of the Models](#limits-of-the-models) says what the models
  leave out.
- **How close.** For 595 figures of the board blocks the pages print the
  distance from a stated value, in most cases the one that the
  specification states: 368 lie less than 5 % from it, 434 less than
  10 % and 489 less than 25 %. A distance is not a verdict: a rail that
  is up earlier than stated is far from its value and inside its limit.
- **A figure that fails is kept as it is.**
  [Reading the Failures](#reading-the-failures) says what the 122 are.
  Most are of five kinds: a point that is decided since and not drawn
  yet, a figure of the specification that the circuit does not give, a
  rating that a fault case passes, an option that is not in use, or a
  model that misses its datasheet.
- **One machine.** The benches ran with the ngspice 45.2 library that
  KiCad 10 ships, on Windows with Python 3.11. The whole suite takes
  29 minutes there. The results folder holds 251 graphs, 289 decks (a
  deck is the circuit file that the simulator ran) and the records, about
  10 MB.
- **Not in the loop.** No bench runs the firmware core or the host
  package: where a voltage becomes a code and a code a current, a bench
  does the arithmetic with the nominal values of the specification. The
  programs of the controller do not exist yet, so the range sequencer is a
  model of rules F-16 to F-18 of the specification. The layout is not
  simulated: no copper, no coupling, no temperature.

What comes next. The four points that the simulations raised are decided:
they are decisions D-95 to D-98 of the specification, taken by the
project owner on 2026-10-10 ([Four Points, Decided](#four-points-decided)).
The next step is to draw D-95, D-96 and D-98 in the schematic and on the
board, to write the snapshot again and to run the benches of the changed
blocks again ([When the Schematic Changes](#when-the-schematic-changes)).
The fourteen places of
[Where the Simulation and the Text Differ](#where-the-simulation-and-the-text-differ)
wait for the project owner, and none of them is decided. The license of
the netlist snapshot in this folder is open as well
([License](#license)).

## What the Simulations Say

Four lists: what is reproduced, the four points that are decided, where
the simulation and the text of the specification differ, and what only a
bench can settle. Each statement names the bench that shows it, and a
value in parentheses is the one that the specification states. The four
points are decisions D-95 to D-98 since 2026-10-10. The differences are
proposals to the project owner: none is decided, no requirement, figure
or rule of the specification was changed on their account, and its
section 16 lists them as open.

### What the Simulations Reproduce

The central design figures of the specification come out of circuits
taken from the netlist, block by block. That is a second calculation with
models, not a confirmation by measurement: the earlier one, from which the
specification took its figures, used circuits typed by hand.

- **Shunt ladder** ([`ladder/ranges`][ladder/ranges],
  [`ladder/change`][ladder/change]). The shunts seen by the amplifier are
  1 kΩ, 31.95 Ω, 999 mΩ and 99.99 mΩ. The burden of range 3 at 1 A is
  104.3 mV with typical parts (the specification calculates 105 mV to
  107 mV). Held in range 0 with 1 A of load, the clamp bounds the ladder
  at 2.508 V (2.5 V to 2.9 V). The two gates of a range change overlap
  for 993.7 ns (about 1 µs).
- **Signal chain** ([`signal_chain/transfer`][signal_chain/transfer],
  [`signal_chain/frequency`][signal_chain/frequency],
  [`signal_chain/settling`][signal_chain/settling],
  [`signal_chain/noise`][signal_chain/noise],
  [`signal_chain/limiter`][signal_chain/limiter]). Gain 19.93, pedestal
  50.08 mV and zero code 1313. The converter reads full scale at 122.9 mV
  across the shunt, and one code is 1.914 nA, 59.91 nA, 1.916 µA and
  19.14 µA in ranges 0 to 3. The anti-alias filter stands at 40.26 kHz
  with a Q of 0.7415, the corners of the input filter at 1.329 MHz and
  20.03 MHz. After a jump to range 3 the chain settles to 0.1 % of the
  range in 45.37 µs and to one code in 65.22 µs. The noise of one sample
  in range 0 is 2.098 nA with C71 and a quiet supply (2.266 nA without
  C71); the share of the converter in it is taken from its datasheet, not
  simulated. In an over-range the converter input stays at VREF +
  204.5 mV at the most.
- **Range logic** ([`range_logic/thresholds`][range_logic/thresholds],
  [`range_logic/jump`][range_logic/jump],
  [`range_logic/load-step`][range_logic/load-step],
  [`range_logic/reverse`][range_logic/reverse]). The thresholds lie at
  90.95 mV, 115 mV and 151.2 mV across the shunt and stay inside their
  bands with every tolerance. The jump path takes 360.8 ns with nominal
  delays and 480.3 ns with the worst ones (target 550 ns). Requirement
  R-07: with 1 µF the drop is 301.9 mV with nominal delays and 388.2 mV
  in the worst case (limit 500 mV), and it is above 0.2 V for 302 ns and
  390 ns (limit 1 µs); with 10 µF it is 168.3 mV and 179.2 mV (limit
  250 mV). An amplifier with half the bandwidth of its model, which is an
  assumption, takes these to 400.3 mV and 180.8 mV and the jump path to
  511.6 ns. With 470 nF at the output the ladder clamp does not conduct.
  In range 3 a reverse current reaches the under-range level at 12.74 mA.
- **Whole path** ([`system/accuracy`][system/accuracy],
  [`system/profile`][system/profile]). With every range held, from the
  load current to the code: zero code 1313, one code as above within the
  last digit, and a straight line within 0.0866 codes from zero to full
  scale. Over a load profile of sleep, wake, burst and sleep with 1 µF
  beside the load, the run starts in range 0 at 3 µA. At the wake edge,
  3 µA to 8 mA in 20 µs, the path takes two single steps up, to range 1
  and to range 2: the ladder voltage peaks at 106.3 mV, below the jump
  level of 151 mV. The burst of 180 mA, in range 2, takes the jump to
  range 3, and three requests to step down bring the path back to
  range 0. The requests are written into the deck at the instants that
  the firmware rule gives; the latency of the sample blocks is not in
  them. The charge that is read over the profile is 0.3386 % above the
  charge through the shunts and 0.3387 % above the charge that the load
  drew, against a limit of 1 % that the bench sets. The median
  deviation of the valid samples from the shunt current is 0.03133 %.
  The largest, 57.68 % of its range, carries no limit: it is the last
  sample in range 0 on the wake edge, where the reading, taken behind
  the anti-alias filter, lags the current through the shunt. 2.917 % of
  the samples are flagged as not valid. The samples show five range
  changes where the path makes six: the two steps up lie about 3 µs
  apart, inside one sample period. The voltage at the load, set to 5 V
  by an ideal source behind 50 mΩ, which is an assumption, stays at
  4.891 V or above during wake and burst, where requirement R-07 allows
  a drop of 0.5 V. Back in sleep the reading is 2.995 µA for a load of
  3 µA.
- **Source meter** ([`source_meter/setpoint`][source_meter/setpoint],
  [`source_meter/tracking`][source_meter/tracking]). 799.5 mV at code 616
  and 5 V at code 3893, in steps of 1.282 mV, with a ceiling of 5.259 V.
  The tracking law is 671.8 mV + 0.9561 × V. On the curve of R-08 the
  regulator has 449.2 mV to 631.9 mV of head room with nominal parts and
  dissipates 820.8 mW at 0.8 V and 1 A and 359.2 mW at 5 V and 0.6 A.
- **Output stage** ([`output_stage/turn-on`][output_stage/turn-on],
  [`output_stage/on-resistance`][output_stage/on-resistance],
  [`output_stage/short-circuit`][output_stage/short-circuit]). The
  in-rush into 2200 µF is 856.1 mA (0.85 A). The largest capacitance that
  starts below the trip level is 3.003 mF with nominal parts and 2.481 mF
  in the fast corner. The closed pair drops 8.623 mV at 1 A and 5 V. In a
  short circuit the currents, the energies and the voltages stay inside
  the ratings of the parts.
- **Path switching** ([`path_switching/close`][path_switching/close],
  [`path_switching/open`][path_switching/open],
  [`path_switching/interlock`][path_switching/interlock],
  [`path_switching/detector`][path_switching/detector],
  [`path_switching/sag`][path_switching/sag],
  [`path_switching/trip`][path_switching/trip]). A mode pair closes as a
  follower, with the supply node rising at 919.3 V/s, and opens under
  load within 492.2 ns. The two pairs never conduct together. The
  over-voltage detector trips at 5.465 V and releases at 5.345 V, at
  5.429 V to 5.501 V and 5.306 V to 5.383 V with the tolerances. The
  supply node sags by 170.5 mV to 209.6 mV behind 0.5 µH to 1 µH of
  supply leads.
- **Analog rails** ([`analog_rails/power-up`][analog_rails/power-up],
  [`analog_rails/boost-output`][analog_rails/boost-output],
  [`analog_rails/negative-rail`][analog_rails/negative-rail],
  [`analog_rails/monitor`][analog_rails/monitor],
  [`analog_rails/reference`][analog_rails/reference]). The rails arrive in
  the order of section 3, and PWR_GOOD rises 205.8 ms to 445.9 ms after
  power (0.2 s to 0.46 s). At the tolerance limits the +13.5 V rail
  stands between 13.02 V and 14.06 V and −4 V_A between −3.913 V and
  −4.041 V. The monitor thresholds are 2.969 V, 9.844 V, −2.559 V and
  2.243 V, inside their bands over 36 sets of tolerances. +12 V_A is at
  11 V 18.01 ms after the release and approaches its level with a time
  constant of 182.5 ms; the reference is within 0.1 % after 74.97 ms.
- **Power input** ([`power_input/current-limit`][power_input/current-limit],
  [`power_input/path-drop`][power_input/path-drop],
  [`power_input/thresholds`][power_input/thresholds],
  [`power_input/logic-rails`][power_input/logic-rails],
  [`power_input/plug-usbc`][power_input/plug-usbc],
  [`power_input/load-step`][power_input/load-step]). The two current
  limits are 758.5 mA and 2.006 A. From the receptacle to the 5 V rail
  the path has 125.9 mΩ with typical parts and 170.1 mΩ at the most. The
  thresholds of limiter, multiplexer and supervisor lie where section 4.1
  puts them, with their corners. The rail ramps in 1.731 ms. A load step
  of 1 A moves the rail by 282.3 mV behind a cable of 0.15 Ω, which is an
  assumption, and 3V3_A by less than 0.8 mV.
- **Digital lines** ([`digital/logic-input`][digital/logic-input],
  [`digital/released-pins`][digital/released-pins],
  [`digital/side-data`][digital/side-data],
  [`digital/monitor-channels`][digital/monitor-channels],
  [`digital/unpowered-inputs`][digital/unpowered-inputs]). A logic input
  keeps its levels and its edge rate from 1.65 V to 5.5 V. With the pins
  of the controller released every line rests at a safe level. The side
  data chain delivers its sixteen bits with no wrong bit in 96. The
  monitor channels have the scales that the specification states. The
  currents into pins of parts without supply stay inside the stated
  limits.

Two events that must not be mixed are a trip in ampere mode and a short
circuit ([`path_switching/trip`][path_switching/trip],
[`path_switching/short`][path_switching/short]). With the damper of D-63 as
drawn, the output opening at 0.5 A to 1.2 A leaves the supply node at
5.607 V at the most. In a short circuit at the terminal, with 14.78 A to
33.89 A in the supply leads, the node reaches 10.69 V to 10.98 V with
typical parts, and the VIN line behind the fuse 27.55 V to 30.88 V over
typical parts and parts at their corners. That voltage is not across a
30 V part: the transistor on the supply side blocks 20.05 V, because its
source stands near 10 V. One margin is thin: with every part at the corner
that raises it, the node reaches 11.54 V in a short circuit, against the
11.5 V of sections 4.3 and 11, and stays 458.5 mV below +12 V_A, against
0.5 V.

### Four Points, Decided

The simulations raised four points for a decision before boards are
ordered. The project owner decided them on 2026-10-10, on the
recommendation of this round: they are decisions D-95 to D-98 of the
specification. Three of them change the circuit and are not drawn yet;
the fourth changes only the text of a position, which is not drawn
either. The schematic, the board, the bill of materials and the netlist
snapshot
of this folder still hold the earlier state: 1 nF at C32 to C34, no
position at U28, R14 and C5 without parts. The results on file are those
of that state, so the failing figures of these benches stay as they are
until the change is drawn, the snapshot is written again and the benches
run again ([When the Schematic Changes](#when-the-schematic-changes)).

1. **Rail monitor capacitors C32 to C34: 10 nF, not 1 nF (D-95, which
   changes the value of D-54).**
   [`analog_rails/monitor`][analog_rails/monitor]. With 1 nF as drawn and a
   comparator at its least hysteresis, 1 mV, an edge of PWR_GOOD moves its
   own threshold, by 3.149 mV to 3.606 mV with 1 pF between an output pin
   and the input beside it, and a rail that crosses slowly gives a burst:
   2771 edges in 241.6 µs at 20 V/s and 423 edges in 36.36 µs at 400 V/s.
   With the typical hysteresis of 3.5 mV and 0.5 pF the threshold moves
   by 2.564 mV and one edge remains at 2 V/s. With 10 nF, 1 mV and 1 pF
   the threshold moves by 525 µV and one edge remains at 2 V/s; no run
   with 10 nF was made at the two slopes of the bursts. The capacitance
   between the pins, 0.5 pF to 1 pF, is an assumption: the datasheet
   names the hazard and gives no figure. Still to do: the value on the
   three capacitors of the schematic. The bench takes the capacitors as
   drawn, so its runs at 20 V/s and at 400 V/s are made with 10 nF once
   the snapshot holds that value, and the benches of the power-up and of
   the power-off then show the edges of PWR_GOOD with nodes that are ten
   times slower. The test of PWR_GOOD on a board stays.
2. **Buffer of the driver rail, U28: a position for a capacitor at its
   non-inverting input (D-96).**
   [`signal_chain/driver-rail`][signal_chain/driver-rail]. The loop has
   41.92° of phase margin as drawn, not the 54° that section 4.5 stated,
   because R126 (10 kΩ) works against the input capacitance of the
   amplifier, 6 pF between the inputs and 2 pF from each by its
   datasheet; with R126 at 100 Ω the same model gives 54.04°. The loop is
   stable, and a load step shows no ringing. Without R129 it is unstable:
   −27.12°, and −2.65° with the model of the manufacturer. That model
   gives 68.99° as drawn, 27° more; its input capacitances and its output
   impedance do not agree with its own datasheet, so it does not speak
   against the lower figure, and neither figure is a measurement.
   Decided: a position for a capacitor from the non-inverting input to
   ground is added to the board; its value is chosen on the bench, and
   the position may stay empty. No run with the capacitor was made. Still
   to do: the position in the schematic and its footprint on the board,
   which is the one change of copper among the four, and then a run with
   a capacitor in it.
3. **Detector position U9: it stays without a part, and the 803 type is
   no longer the part meant for it (D-97, which changes D-84).**
   [`analog_rails/boost-start`][analog_rails/boost-start] and
   [`analog_rails/boost-detector`][analog_rails/boost-detector]. As drawn
   the boost converter starts in one go on an input limited to 0.67 A to
   0.85 A: the +13.5 V rail is above 12.2 V after 980 µs to 1.294 ms.
   Fitted with the detector of 0.24 s (typical; 140 ms to 280 ms by its
   datasheet), the position would stop a start
   that works without it: the 5 V rail falls to 2.928 V to 3.03 V and the
   detector stops the converter 177.5 µs to 249 µs after the enable. Only
   in the corner that is kindest to the source, a converter at its least
   current limit with a gentle error amplifier, does the rail stay above
   the detector, at 3.62 V, and the start complete with the part fitted.
   With 1 mA drawn from the +13.5 V rail while the detector waits, the start
   repeats four times in 1.1 s and the rail is not charged at the end of
   the run; with 0.1 mA the second attempt completes it, after 485.6 ms.
   A detector with a time-out of 3 ms charges the rail in two attempts,
   after 3.379 ms. Three things in this are assumptions: the converter
   below 2.7 V, where its datasheet says nothing and which decides the
   result; the source, a voltage behind 0.2 Ω with a flat current limit,
   where a real limiter may fold back; and the 1 mA. Decided: the
   position stays without a part, and a remedy, if the prototype of
   phase 1 that starts from a supply limited to 0.7 A asks for one, is a
   detector with a time-out of milliseconds. No copper changes; the
   schematic and the footprint on the board still name the position
   "803 type, 3.08 V". The
   seven failing figures of `boost-detector` are those of the part that
   is no longer meant for the position.
4. **Damper R14 (0.33 Ω) with C5 (10 µF) on the module input: fitted
   (D-98, which changes D-84).**
   [`power_input/replug-module`][power_input/replug-module]. When the data
   cable is plugged again on a port at 5.5 V behind a short cable (0.08 Ω
   and 0.3 µH) while USB-C supplies the rail, input 2 of the power
   multiplexer reaches 5.941 V with a limiter of typical reaction and
   6.002 V with one that reacts in 15 µs, which is an assumption, against
   a rating of 6.0 V. The peak is largest when the contact closes 2 ms to
   2.6 ms after it opened. With a port at 5.25 V it is 5.691 V, and with
   the cable of the module alone 5.8 V. With the damper fitted, its
   capacitor at half its value, the peak is 5.502 V in the runs made,
   which used the same three gaps. That is not the worst case of the
   damped circuit: the graphs on the page show the damped input near
   4.95 V when the contact closes, where the undamped one stands near
   3 V, and no run was made with the longer gap in which the damped input
   has fallen as far. Not simulated either: the recharge pulse at a
   change of input with the damper fitted. Without the damper that pulse
   is 4.103 A through the multiplexer, against its pulse rating of 4 A
   ([`power_input/unplug`][power_input/unplug]), and the capacitor of the
   damper hangs on the input of the multiplexer, behind the limiter.
   Still to do: the two
   parts with their part numbers in the schematic and in the bill of
   materials, on pads that the board has. The other benches of the power
   input leave R14 and C5 out, by a list of positions without parts in
   `benches/power_input/common.py`; the two leave that list when the
   change is drawn.

### Where the Simulation and the Text Differ

Fourteen places. In each the specification states a figure or a rule
that the simulation does not give, or it is silent on something that the
simulation shows. The round proposes no change of hardware for them: in
each the proposal is to bring the text to what the circuit does. That is
the owner's decision, and until it is taken the text stands as it is.

- **Over-current qualification (section 4.4, F-18, section 11).**
  [`range_logic/trip`][range_logic/trip]. While a large capacitor
  recharges after a step to 1 A the comparator is high for up to 12.83 µs
  (specification: up to 8.6 µs with 56 µF), of which 8.174 µs at the most
  in range 3. No run trips, because the model counts in range 3 only.
  Proposed: the rule says that the 12 µs count in range 3, and the
  criterion of section 11 is read there. The worst capacitor is near
  82 µF.
- **Ladder clamp in a short circuit (section 4.3).**
  [`range_logic/hot-plug`][range_logic/hot-plug] and
  [`output_stage/short-circuit`][output_stage/short-circuit]. "Above 5 A
  for at most 0.54 µs" holds for the hot plug (285.6 ns). In a short
  circuit from a supply that holds its voltage, a clamp transistor with a
  low threshold carries more than 5 A for 14.79 µs, until the trip, and
  19.26 A in the worst combination against a rating of 21 A. The shunt of
  range 3 sees 29.52 A, not "up to 27 A", and 32.33 A with a short across
  the terminals. The spread of the clamp at amperes is an assumption, and
  for the source meter, whose regulator limits its current, the figures
  up to the trip are an upper bound.
- **Capacitor at the VIN terminals (sections 4.4, 4.9 and 11).**
  [`range_logic/supply-leads`][range_logic/supply-leads]. 100 µF there
  does not stop the ringing when the load capacitor is as large and the
  leads have little resistance: the current stays above 1.15 A for
  32.75 µs (specification: 2.1 µs), and 2 of 8 runs trip, where section
  11 asks for none. Proposed: the advice asks for a capacitor several
  times the load capacitor, or a lossy one.
- **Power-off and power-up (section 3, F-7).**
  [`analog_rails/power-down`][analog_rails/power-down] and
  [`analog_rails/power-up`][analog_rails/power-up]. 3V3_C is below 3.0 V
  after 45.72 µs, not 0.02 ms: the netlist has 2.4 µF on that rail.
  PWR_GOOD is below 2.0 V at the controller pin after 145.1 µs, not
  0.05 ms to 0.07 ms, and below 0.8 V after 604.5 µs, not 0.3 ms. 3V3_A
  is below 1.0 V after 3.584 ms, not 4 ms to 6 ms. +12 V_A is below 3.6 V
  after 20.31 ms, not about 14 ms, so the time with +12 V_A above 3.6 V
  and 3V3_A below 1 V is 16.73 ms, not about 10 ms. These times follow
  from the loads that the bench assumes. At power-up −4 V_A arrives
  after 434.9 µs, not 0.3 ms; the order of the rails is unchanged.
- **Output switch (section 4.2, D-71, F-8, F-24).**
  [`output_stage/turn-off`][output_stage/turn-off] and
  [`output_stage/turn-on`][output_stage/turn-on]. "Gate below 2 V within
  7 µs" holds at 5 V: 6.288 µs with nominal parts and 6.833 µs in the
  slow corner. At 0.8 V it takes 7.274 µs to 7.448 µs, and 8.109 µs in
  the slow corner. "Starts to rise 6 ms to 7 ms after the request" is one
  point: with 100 µF the output is at 10 % after 6.458 ms at 5 V and
  after 5.381 ms at 0.8 V. Over the corners the start spans from
  3.888 ms, the first 50 mV at 0.8 V in the fast corner, to 10.03 ms,
  10 % at 5 V into 2200 µF in the slow corner.
- **Suppressor of VOUT (section 4.9).**
  [`output_stage/short-circuit`][output_stage/short-circuit] and
  [`output_stage/terminal`][output_stage/terminal]. At a trip it carries
  up to 14.37 A forward, not "at most 11.6 A" (rating 50 A), and with
  0.15 Ω of forward resistance the terminal goes to −1.807 V, not −0.8 V
  to −1.7 V; the forward curve of the part is an assumption on both
  sides. A positive strike beyond 15 V on the open output is limited by
  the suppressor, not by the avalanche of the output transistor: 24 V
  behind 1 Ω leave 19.4 V at the terminal and 17.38 V across Q16.
- **Mode switches (section 4.9, F-23).**
  [`path_switching/open`][path_switching/open],
  [`path_switching/drop`][path_switching/drop],
  [`path_switching/detector`][path_switching/detector] and
  [`path_switching/overvoltage`][path_switching/overvoltage]. The opening
  kick on VIN is 16.01 V to 25.12 V, not 20 V to 24 V. The gate drive is
  6.122 V at 5 V and 5.739 V at 5.4 V when +12 V_A stands at 11.4 V, not
  "at least 6.2 V". The detector opens the switch after 2.199 µs to
  78.34 µs, not "4 µs to 45 µs", for which the text states no condition.
- **Check of section 16 on TP33.**
  [`path_switching/reversal`][path_switching/reversal]. "TP33 above
  −0.1 V after 35 µs" with a reversed supply limited to 1 A is not met in
  the simulation: the node is at −2.556 V then. It is one run, with a
  source that limits at 1 A and has no output capacitor.
- **Noise budget (section 4.10).**
  [`signal_chain/noise`][signal_chain/noise]. The total stands; the list
  of its terms does not. The converter is 1.629 µV at the shunt by its
  datasheet at a reference of 2.5 V, not 1.0 µV, and the multiplexer
  channels (620.2 nV) and the filter with its driver (325.7 nV) are
  missing.
- **Converter interface (section 4.6).**
  [`digital/converter-lines`][digital/converter-lines]. By its datasheet
  the converter shifts its result out after convert-start falls, not
  "while that line is still high"; that is a reading of the datasheet,
  not a simulated figure. The estimates of about 1 ns on the clock and
  3 ns to 4 ns on the data line leave out the resistance of the pads: the
  clock edge is valid at the converter 2.251 ns to 12.57 ns after the pad
  command, and the data come 5.015 ns to 11.5 ns later than the converter
  alone gives them. The capacitances of tracks, pins and pads in these
  runs are assumptions; no datasheet gives them.
- **Slow monitors (section 4.2).**
  [`digital/monitor-channels`][digital/monitor-channels]. The leakage of
  the converter inputs, 1 µA at the most, is not in the text: at that
  maximum channel 0 is off by 120 mV, where F-28 allows 100 mV, and the
  VIN channel by 430 mV, where F-26 allows 130 mV before calibration.
  Channel 2 is at full scale with the rail at 5.50 V and the resistors at
  their limits (2.527 V against 2.5 V): it saturates from about 5.44 V of
  the rail (calculated from that figure).
- **Source meter (sections 4.2 and 4.9).**
  [`source_meter/setpoint`][source_meter/setpoint],
  [`source_meter/tracking`][source_meter/tracking] and
  [`source_meter/external`][source_meter/external]. Code 0 gives
  30.96 mV, not 0.01 V. An overload into 5 Ω rests at 4.729 V, not
  4.48 V. The role of R60 is not stated: it limits the current of the
  clamp between SET and OUT, 3.453 mA with a device at 5.0 V above a
  set-point of 0.80 V. A charged capacitor of 100 µF plugged into the
  output takes the IN pin 1.013 V to 1.04 V below the output for 22.82 µs
  to 24.72 µs, not 0.32 V to 0.94 V for 3 µs to 21 µs; the specification
  says of this case that no part covers it.
- **Power input (sections 3, 4.1 and 16, F-35).**
  [`power_input/plug-module`][power_input/plug-module],
  [`power_input/switch-over`][power_input/switch-over],
  [`power_input/contact-bounce`][power_input/contact-bounce],
  [`power_input/plug-usbc`][power_input/plug-usbc],
  [`power_input/load-step`][power_input/load-step] and
  [`power_input/current-limit`][power_input/current-limit]. On a computer
  port the in-rush shows a peak of 1.018 A to 1.275 A for 16.3 µs to
  33.04 µs when the boost converter starts, against "0.9 A or less"; the
  port falls to 4.883 V to 4.935 V in it, against "4.94 V or above", and
  the charge above 100 mA is 1.179 mC to 1.193 mC, against 0.44 mC to
  0.96 mC. The boost converter is a stand-in load in these runs. The dip
  at a change to USB-C is 4.867 V and 4.808 V at idle and 4.652 V and
  4.507 V with 0.45 A of load, not 4.54 V and 4.28 V; both sources stand
  at 5.0 V in these runs. The sentence on the margin to 6 V holds for
  input 2 only: input 1 stays at 5.5 V. The rail starts 1.318 ms after
  the output of the limiter, not about 1 ms. A load step of 1 A moves the
  rail by 282.3 mV behind a cable of 0.15 Ω, close to the 0.3 V of rule
  F-35: the 1.34 A that section 4.1 calculates for 5 V at 1 A would move
  it by about 0.38 V (calculated from the 0.28 V per ampere of this
  run). A short circuit of the 5 V rail is not in the
  text: 30.5 A on the USB-C input and 8.863 A on the module input flow
  through the multiplexer, against a pulse rating of 4 A, and 3V3_A
  stands up to 1.539 V above the collapsed rail, against a rating of
  0.3 V. The peak is an upper bound, and its length of about a
  microsecond rests on an assumed reset level of the model.
- **Logic inputs (section 4.8).**
  [`digital/logic-abuse`][digital/logic-abuse]. +12 V at a line leaves
  6.588 V to 8.562 V at the translator pin behind 1 kΩ, 7.728 V behind
  100 Ω and 11.58 V from a source of 0.1 Ω, against a rating of 6.5 V.
  The text states no range that a line withstands. Proposed: it gives
  the range of a line as 0 V to 5.5 V.

The fourteen are not every difference. Thirteen more failing figures of
the board blocks are judged against a rating or a condition of a
datasheet, or against a figure of the text that is not among the
fourteen:

- The start of the boost converter on the USB-C input takes more than
  1 A from the source for 383.8 µs, where section 16 expects 0.15 ms to
  0.2 ms; the peak of 1.513 A is inside the expected 1.5 A to 2.5 A
  ([`analog_rails/boost-start`][analog_rails/boost-start]).
- A USB-C source that limits at 0.9 A leaves the receptacle at 2.842 V
  once the limiter is on, inside the band in which the limiter turns off
  ([`power_input/plug-usbc`][power_input/plug-usbc]).
- The charge above 100 mA at a plug, 1.329 mC on USB-C and 1.189 mC on
  the module input, against the 50 µC of the USB in-rush test, which the
  specification states is not met
  ([`power_input/plug-usbc`][power_input/plug-usbc],
  [`power_input/plug-module`][power_input/plug-module]).
- With the jumper cut and the largest reverse current of the diode, the
  5 V rail stands at 506.8 mV, against a calculated "0.5 V or below" of
  section 4.11 ([`digital/module-supply`][digital/module-supply]).
- A released output falls at 699.5 V/s, against a calculated 0.7 V/ms to
  0.8 V/ms of section 4.2
  ([`source_meter/sequence`][source_meter/sequence]).
- The buffer of the pedestal offers the reference pin of the amplifier
  1.363 Ω at 40 kHz, where the datasheet of the amplifier asks for less
  than 1 Ω ([`signal_chain/pedestal`][signal_chain/pedestal]).
- When the 5 V rail is taken to 0 V at 20 V/ms, the two 3.3 V rails
  stand 637.3 mV and 649.7 mV above it, and 1.93 V and 1.949 V with the
  model of the manufacturer, against a rating of 0.3 V
  ([`power_input/logic-rails`][power_input/logic-rails]).
- A source of 12.5 V at the receptacle puts 20.11 W into the suppressor,
  which the specification says such a source destroys, and a reversed
  source of 3 A takes the receptacle to −961.8 mV and input 1 of the
  multiplexer to −816.1 mV, against ratings of −0.3 V
  ([`power_input/overvoltage`][power_input/overvoltage]).
- The recharge after the USB-C cable is pulled sends 4.103 A through the
  multiplexer, against a pulse rating of 4 A
  ([`power_input/unplug`][power_input/unplug]).

Among the figures that pass or carry no limit, some lie far from the
value of the text on the side that matters. A supply that steps to −20 V
with the pair closed leaves −3.721 V at the device under test, not
−2.4 V ([`path_switching/reversal`][path_switching/reversal]). The noise in
range 0 in source mode is 28.32 nA to 31.54 nA, not 26 nA to 27 nA,
against a limit of 40 nA ([`source_meter/noise`][source_meter/noise]).
At power-off the control pin of the regulator stays 549 mV above the
output, not "at least 0.88 V" ([`source_meter/rails`][source_meter/rails]).
A dip of the 5 V rail to 3.7 V takes the supervisor down when it lasts
100 µs, the longest of the six lengths tried, and not when it lasts
50 µs; the text says about 30 µs
([`power_input/logic-rails`][power_input/logic-rails]). The page of each
block shows the distance from the stated value beside every figure.

With these, every bench of the board blocks that has a failing figure is
named in this section with what fails. The one exception is a figure of
`range_logic/landing` that is a property of the sequencer model
([Limits of the Models](#limits-of-the-models)).

### What Stays for the Bench

The simulations cannot settle these, whatever they say.

- **Head room of the amplifier near the −4 V rail, with the output below
  0.2 V.** [`signal_chain/head-room`][signal_chain/head-room]. Two
  readings of the datasheet end the linear range at 130 mV or at 214 mV
  with the output at 0 V. With the lower one the jump level is reached at
  162.4 mV at 0.2 V, outside its band of 147.2 mV to 155.1 mV. It is
  already an open check of section 16.
- **Loop of the pre-regulator at its low end.**
  [`source_meter/pre-regulator`][source_meter/pre-regulator] and
  [`source_meter/loop`][source_meter/loop]. With the switching model of
  the manufacturer a step to 1 A at 0.8 V dips the IN pin by 137.9 mV,
  and the recovery overshoots by 31.25 % of the dip, the mark of a loop
  with about 40° of phase margin. The averaged model written here has
  58.18° there, and the text says 55° or more. The head room stays at
  499.8 mV against a need of 470 mV.
- **Linear regulator at light load with 22 µF.**
  [`source_meter/loop`][source_meter/loop] and
  [`source_meter/load-step`][source_meter/load-step]. The model has
  17.31° of phase margin at 0.8 V and 27.04° at 5 V without load, and the
  output rings near 10 kHz after a load release. The model is a fit that
  extrapolates here: its datasheet shows no load step below 50 mA and no
  capacitor above 10 µF.
- **A supply that leaves its range while the ampere pair is closed.**
  [`path_switching/overvoltage`][path_switching/overvoltage] and
  [`path_switching/reversal`][path_switching/reversal]. A transistor of
  the pair then has to block more than its 30 V: 34.44 V on a step to
  20 V, 34.48 V on a reversal to −5 V, and 65.74 V with 85.36 A drawn
  backward on a stiff reversal to −20 V. The model written here has no
  avalanche. The model of the manufacturer breaks down near 31 V and
  takes 3.84 mJ there, at a current that can pass its avalanche rating of
  28 A. Whether a part survives is a pulse test on a board.
- **Zero of range 0 against the output voltage.**
  [`signal_chain/common-mode`][signal_chain/common-mode]. With the
  amplifier at the limit of its rejection the zero moves by 2.515 nA per
  volt, 12.58 nA at 5 V. Section 8 does not say at which ladder voltage
  the zero is taken.
- **The 500 kSPS option.**
  [`digital/converter-lines`][digital/converter-lines] and
  [`signal_chain/sampling-kick`][signal_chain/sampling-kick]. One reading
  instant for weak and for strong pads has a window of 11.43 ns at
  15 MHz with long tracks, and 13.18 ns with the weakest pad of the
  stronger setting, against the 13.33 ns of two system clocks. The
  sampling kick leaves −0.9491 codes near full scale. At 100 kSPS both
  are far from their limits.
- **Clamp levels of the rail diodes.**
  [`analog_rails/clamps`][analog_rails/clamps]. With the largest forward
  voltage of the datasheet −4 V_A stands at 296.4 mV and +12 V_A at
  −292.8 mV while its converter is absent, against pin ratings of 0.3 V;
  at −40 °C the same case gives 394.2 mV and −391.4 mV.
- **What no model here can give.** Leakage at the nanoampere level: no
  model of a transistor, a diode or the multiplexer gives a believable
  figure. The on-resistance and the charge injection of the multiplexer
  at +12 V and −4 V, which its datasheet does not state. The reaction
  time of the programs of the controller, which do not exist yet. The
  loops of the regulators for which no model of the manufacturer was
  found that runs here. Coupling through the board, thermal effects and
  the real noise.

### What the Runs Show About the Instrument

Three things that are not faults and that a user of the instrument will
meet.

- **Range 0 is slow by itself.** Its shunt of 1 kΩ and the 100 nF of C71
  make 100 µs, and 1 µF beside the load makes 1.1 ms. The reading follows
  the load with shunt times capacitor
  ([`system/accuracy`][system/accuracy],
  [`system/profile`][system/profile]).
- **With a capacitor beside the load the sequencer follows the sag of
  that capacitor, not the current.** A fast step to 80 mA ends in range 3
  with 100 nF to 10 µF. A current between the step-down level of a range
  and the step-up level of the range below it stays in the upper range
  after any fast step ([`range_logic/landing`][range_logic/landing]).
- **A model of a manufacturer is a second opinion, not the reference.**
  The one for the transistor of the 1 A path has 5.21 mΩ at 10 V on the
  gate, where its own datasheet gives 4 mΩ as the typical value
  ([`models/mosfet-csd17577q3a`][models/mosfet-csd17577q3a]).

## Reading the Failures

A figure that fails stays failed. The table says, block by block, what the
122 failing figures are. The blocks `ladder` and `system` have none.

| Block | Fail | What fails |
| --- | --- | --- |
| `analog_rails` | 25 | `power-down` 12 and `power-up` 1: the times at which the rails fall, and at which −4 V_A arrives, are not those of section 3; ten are later and two earlier (3V3_A below 1.0 V after 3.584 ms, against 4 ms to 6 ms). `boost-detector` 7: the detector position U9 with the part of 0.24 s, which the board does not carry and which D-97 no longer means for it. `monitor` 2: edges of PWR_GOOD at the least hysteresis with 1 nF as drawn (D-95, not drawn yet). `clamps` 2: the rail clamps at −40 °C with the largest forward voltage, 394.2 mV and −391.4 mV against pin ratings of 0.3 V. `boost-start` 1: the source gives more than 1 A for 383.8 µs, where section 16 expects 0.15 ms to 0.2 ms |
| `digital` | 11 | `logic-abuse` 5: +12 V at a logic line against the 6.5 V rating of the translator pin. `monitor-channels` 3: the input leakage of the monitor converter at its datasheet maximum, and channel 2 at full scale. `converter-lines` 2: one reading instant for weak and strong pads at 15 MHz, the 500 kSPS option. `module-supply` 1: 506.8 mV against a calculated 0.5 V |
| `output_stage` | 6 | `turn-off` 3: the gate below 2 V after 7.274 µs to 8.109 µs at 0.8 V, against 7 µs. `short-circuit` 2: 32.33 A in the 0.1 Ω shunt with a short across the terminals, and −1.807 V at the terminal with a suppressor of 0.15 Ω. `turn-on` 1: the output starts to rise after 5.381 ms at 0.8 V, against 6 ms to 7 ms |
| `path_switching` | 19 | `short` 4: with parts at their corners the supply node reaches 11.52 V to 11.54 V against 11.5 V, and stays 458.5 mV below +12 V_A against 0.5 V. `reversal` 4 and `overvoltage` 3: a transistor of the pair has to block 34.44 V to 65.74 V against its 30 V when the supply leaves its range; the pair opens outside 4 µs to 45 µs; the check of section 16 on TP33. `open` 3: the opening kick outside the estimate of F-23. `drop` 3: gate drive below 6.2 V with +12 V_A at 11.4 V. `detector` 2: reaction outside 4 µs to 45 µs |
| `power_input` | 27 | `plug-module` 13: the in-rush on a computer port after the spike of the module (peak current, port voltage and charge). `current-limit` 4: a short circuit of the 5 V rail, which the text does not cover. `overvoltage` 3: 12.5 V at the receptacle and a reversed source of 3 A against ratings of parts; the specification says that such a source destroys the suppressor. `plug-usbc` 2, `logic-rails` 2 and `unplug` 1: the USB in-rush test, which the specification states is not met; a source limited to 0.9 A; the 3.3 V rails 637.3 mV and 649.7 mV above a 5 V rail that is taken to 0 V at 20 V/ms; 4.103 A through the multiplexer in the recharge. `replug-module` 2: input 2 at 6.002 V without the damper (D-98, not drawn yet) |
| `range_logic` | 6 | `trip` 2 and `supply-leads` 2: the over-current comparator high for longer than the text states. `hot-plug` 1: a clamp transistor above 5 A for 14.79 µs in a short circuit. `landing` 1: the model of the sequencer takes its next step after 2.968 µs, not 3 µs, which is a property of the model |
| `signal_chain` | 8 | `driver-rail` 3: phase margin of the buffer U28 as drawn (D-96 adds a position for a capacitor). `head-room` 2: the reading of the amplifier datasheet that ends the linear range at 130 mV. `sampling-kick` 2: the 500 kSPS option. `pedestal` 1: 1.363 Ω at the reference pin of the amplifier at 40 kHz, where its datasheet asks for less than 1 Ω |
| `source_meter` | 3 | `external` 2: a charged capacitor plugged into the output takes the IN pin 1.013 V and 1.04 V below the output, a case that the specification names as covered by no part. `sequence` 1: a released output falls at 699.5 V/s against a calculated 700 V/s to 800 V/s |
| `models` | 17 | Six of the 41 models miss a figure of their datasheet, and the page says which: `output-stage-buffer` 7, `source-meter-lt3080` 3, `analog-rails-lmr62014` 2, `signal-chain-ad8421` 2, `source-meter-tps63020` 2, `power-input-capacitors` 1 |

How to weigh a pass:

- The column "Source" of a page names where a limit comes from. Most
  come from the specification and name its section, requirement or rule.
  Others are a rating or a figure of a datasheet, or a value that the
  bench calculates and names as "calculated here". Where none of these
  exists, the figure carries no limit, or a limit that the bench sets
  and names as such ("limit of this bench", "limit set here"). A pass
  against a limit of the last kind says the least.
- In a bench of the block `models` the limits are the fit that this
  project asks of a model, for example 10 % on an on-resistance and 25 %
  on a gate charge. They are not limits of the datasheet.
- In the block `digital` four figures were defined again after a first
  result had been seen. The supply pin of the translator with 470 Ω at
  0 °C reads −378.5 mV with a typical clamp, against the −0.44 V of the
  specification, and carries no limit; the figure with the largest
  forward voltage passes at −421.3 mV against a window that the bench
  sets and that ends at −420 mV. The clock edge of the slow bus is read
  against its real swing, and the current of the slow clock line 2 µs
  after the edge. The reading window of the converter lines went through
  three definitions; the window that one reading instant shares fails at
  15 MHz in each of them.

## Limits of the Models

What the models leave out decides how far a result reaches. The head of
each model in `models/*.lib` and the notes of each bench give the detail.

- **Typical parts at room temperature.** Every integrated circuit is a
  behavioral model of a typical part, written from its datasheet. No
  model has temperature or thermal shutdown, and the spread of a part
  enters only where a bench varies a parameter.
- **No leakage.** No leakage figure at the nanoampere level can be taken
  from any model here. The least conductance that the simulator puts
  across every junction is a leakage path of its own.
- **The sequencer is a model of the rules.** The range sequencer and the
  over-current trip follow rules F-16 to F-18, with the reaction time of
  100 ns and the qualification time of 12 µs as parameters: both are
  inputs of a bench, never its result. The model has no input that
  selects or locks a range, ignores a comparator pulse shorter than its
  reaction time, counts the trip in range 3 only and takes its next step
  after 2.968 µs where its parameters ask for 3 µs.
- **Comparators.** One delay whatever the overdrive, and a hysteresis of
  about 2.1 mV where the parameter says 3 mV.
- **Instrumentation amplifier.** No supply rejection, no non-linearity,
  no overload recovery. Its noise from 0.1 Hz to 10 Hz at a gain of 10 is
  254 nV, where the datasheet gives 500 nV. The limit of its input stage
  near the negative rail has two readings, and both are in the bench.
- **Operational amplifiers.** No supply or common-mode rejection, no
  overload recovery. The model of the guard buffer has 77.88° to 89.08°
  of phase margin with a capacitive load where the table of its datasheet
  gives 60°, and delivers less output current than the part, so the guard
  recovers too slowly after a dip.
- **Multiplexer.** Its manufacturer publishes no model. The one here has
  a fixed on-resistance, 250 Ω by default and swept from 125 Ω to 430 Ω,
  and no charge injection.
- **Power transistors.** The model of the transistor of the 1 A path has
  no avalanche and a fitted subthreshold slope. A voltage above 30 V
  across it is what the part would have to block and does not.
- **Linear regulator.** Its loop is a fit to three load steps of the
  datasheet, and three of their six extremes are missed; its phase margin
  is a property of that fit and not a datasheet value. It has no thermal
  limit and no fitted supply rejection, so no ripple at the output may be
  taken from it.
- **Switching converters.** The pre-regulator is an averaged model
  without ripple, fitted to one load step of the model of its
  manufacturer, and optimistic at its low end. The boost converter has an
  assumed error amplifier, and everything below the 2.7 V at which its
  datasheet begins is an assumption. In the block `power_input` the boost
  converter is a stand-in load.
- **Input stage.** Limiters, multiplexer and supervisor are behavioral
  models with typical reaction times; the multiplexer holds several
  assumed values and cannot show hunting of its priority input.
- **Digital parts.** Thresholds at half the supply; the output
  resistances of translator, register, converter and pad are assumptions;
  no inductance and no reflection on a line.
- **Models without a bench of their own.** No bench of the block
  `models` puts these into a test circuit of a datasheet: the analog
  multiplexer U24, the gate drivers U20, U22 and U23, the BAV199 diode
  pairs, and the fit that the ladder clamp transistors Q10 and Q11 take,
  which is another one than the fit of the range switches. Their values
  are written from the datasheets that the head of each model names.
- **What stands around a circuit.** Sources, loads, cables and the device
  under test are typed by the bench and are assumptions: its notes name
  them. A ceramic capacitor has a fixed value, in some blocks the one it
  keeps under bias and in others the nominal one, as the notes say.

## How It Works

| Path | Content |
| --- | --- |
| `netlist/carrier.json` | Snapshot of the netlist of the schematic: 428 parts with values and nets |
| `models/` | SPICE models written here, and the model map that gives every part its model |
| `models/vendor/` | Model files of the manufacturers, where present; not versioned |
| `benches/` | The benches, one Python package per block of the instrument |
| `results/` | Result files, graphs, decks and the pages written from them |
| `src/circuit_sim/` | The package: netlist, circuit builder, engine, measurements, graphs, report |
| `tests/` | Unit tests of the package |
| `.work/` | Scratch folder of the runs, with the raw vectors of every deck; not versioned |

A bench does not type the parts of the board. It names them by their
reference designators, and the package writes one SPICE element for each,
with the value and the nets of the schematic. What the bench adds is what
the schematic does not hold: sources, loads, cables and the analysis. A
value changed in the schematic therefore changes the simulation with the
next snapshot, and a part enters a bench only as it is drawn. Two things
go beyond that, and the notes of a bench name each: a bench can change
single parts on purpose (`overrides`, `scales`), for a tolerance run or
for a variant such as a position fitted, and it can type a stand-in for a
neighboring block of the board that it does not simulate.

Every deck runs in a process of its own that loads the ngspice library,
and the package judges the log of the run: the simulator goes on after
many errors and still prints numbers, so a run counts as failed when its
log says so ([Traps of the Simulator](#traps-of-the-simulator)).

## Setup

Python 3.10 or later and the ngspice shared library. KiCad 10 ships it
(`ngspice.dll` beside `kicad-cli`); no separate installation is needed.

```sh
cd simulation
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
export NGSPICE_LIBRARY=/path/to/KiCad/bin/ngspice.dll
```

Without `NGSPICE_LIBRARY` the library is looked for beside `kicad-cli` on
the search path and among the libraries of the system. On Linux and macOS
the folder of the environment is `.venv/bin/` in place of `.venv/Scripts/`.
The filed results come from version 45.2 of the library, on Windows;
another version may give other digits, and no other system has run the
package yet.

## Commands

Run them in `simulation/`.

| Command | Does |
| --- | --- |
| `circuit-sim list` | Names every bench |
| `circuit-sim run` | Runs every bench, files the results, writes the pages |
| `circuit-sim run ladder` | Runs the benches of one block |
| `circuit-sim run ladder/change -v` | Runs one bench and prints every figure |
| `circuit-sim run ladder --no-report` | Files the results and leaves the pages alone |
| `circuit-sim run --timeout 600` | Gives up on a deck that has no result after 600 s; the default is 1800 s |
| `circuit-sim run --strict` | Ends with exit code 2 when a figure fails |
| `circuit-sim run --tier vendor` | Runs again with the models of the manufacturers where present |
| `circuit-sim report` | Writes the pages from the result files |
| `circuit-sim parts --sheet "Shunt Ladder"` | Shows the parts of a sheet with their nets and models |
| `circuit-sim parts R110 U24` | Shows single parts |
| `circuit-sim netlist carrier.xml` | Writes the snapshot from an export of KiCad |
| `circuit-sim netlist carrier.xml --check` | Says whether the snapshot still matches the schematic |

- `--no-report` is for runs of single blocks one after another: the pages
  are then written once, with `circuit-sim report`, from all results on
  file.
- `--timeout` is for the models of the manufacturers, some of which take
  minutes for a deck or never end.
- `--root` in front of the command names the folder that holds benches,
  models, netlist and results, when it is not the current one.
- The command ends with 0 when everything ran, with 1 when a bench could
  not run or the snapshot differs, and with 2 when a figure failed under
  `--strict` or the input was wrong.

The export that the last two commands read:

```sh
kicad-cli sch export netlist --format kicadxml -o carrier.xml \
    ../hardware/kicad/power-profiler-carrier.kicad_sch
```

## Models

Two tiers.

- **Open tier**: the models in `models/*.lib`, written for this project from
  datasheet figures. Each names its datasheet, with the page of most
  figures, and what it leaves out. Every verdict and every count in
  `results/` comes from this tier, so it can be reproduced from the
  repository alone. The block `models` holds the benches that put the
  models into the test circuits of their datasheets; four models have no
  such bench ([Limits of the Models](#limits-of-the-models)).
- **Vendor tier**: the models of the manufacturers, where they publish one
  that ngspice can run. Their licenses do not allow a copy in this
  repository, so `models/vendor/` is not versioned. Where such a file is
  present, `circuit-sim run --tier vendor` runs the same benches with it
  and files a second record, and the pages show its value in the column
  "Vendor models". That column cannot be reproduced from the repository
  alone, and it changes no verdict.

The model map is the set of `models/*.toml` files:
`[part."<part number>"]` gives the model of a part, `[ref.<designator>]` an
exception for one part of the schematic, `[vendor."<part number>"]` the
model of the manufacturer. Resistors, capacitors, inductors and resistor
networks need no entry; a part without a model stops the bench that names
it, and two maps that give a model for the same part stop every run.

A `[vendor]` entry names the file that it expects in `models/vendor/`. The
file is the model that the manufacturer offers on the page of the part,
saved under that name; the start of the name gives the manufacturer
(`ti-`, `mchp-`, `nexperia-`, `diodes-`). The package never changes such a
file: it reads it through a copy in the scratch folder
([Traps of the Simulator](#traps-of-the-simulator)).

What the vendor tier gave on 2026-10-10: of 69 such runs on file 63 ran.
Six did not run and left a record that says why, about which the pages are
silent: `ladder/ranges`, two benches of the range logic and the three
benches of the boost converter. The blocks `digital` and `system` have no
vendor run.

Rules for a model written here:

- Every figure names its datasheet and page. A figure that is an
  assumption says so.
- The head of the model lists what it leaves out.
- ngspice puts the text of a `{}` expression into a behavioral source as it
  is. A sum inside braces that is then multiplied loses its parentheses:
  compute it with a `.param` line first.
- Plain ngspice syntax, so that the open tier runs without the PSpice
  compatibility mode. The XSPICE code models that ship with ngspice may be
  used, the digital gates and the bridges for example. The worker loads
  `spice2poly`, `analog`, `digital`, `xtradev`, `xtraevt` and `table` from
  the folder `lib/ngspice` beside the folder of the library, where KiCad
  keeps them, or from the folder that `NGSPICE_CODEMODELS` names. It does
  not load the transmission line models (`tlines`).
- A part type that sits on the sheets of several blocks gets
  `[ref.<designator>]` entries, one block at a time, so that two maps
  never name the same part number.
- No text of a file of a manufacturer is copied into a file of the
  repository.

## Writing a Bench

A bench is a function with the `@bench` decorator in
`benches/<block>/<module>.py`. `benches/ladder/ranges.py` (operating points)
and `benches/ladder/change.py` (transient) are the patterns to follow.

```python
@bench("ladder", "ranges", "What is simulated, in one line", "sections and rules it answers")
def ranges(ctx: Context) -> Outcome:
    """What the bench does; this text goes into the report."""
    circuit = ctx.circuit(refs, aliases)  # parts of the schematic
    deck = ctx.deck("title", circuit, stimulus, control=["op"])
    result = ctx.run("name", deck)  # vectors of every plot
    ...
    return Outcome(figures, graphs, notes)
```

- The name of a block is lower case with underscores, the name of a bench
  lower case with hyphens. The docstring of the function is the text of
  the page.
- `ctx.circuit(refs, aliases, overrides, scales)` writes the elements.
  `aliases` gives nets short node names, `overrides` replaces the model of
  single parts, `scales` multiplies the values of single passive parts for
  tolerance runs (`circuit_sim.tolerance`).
- `ctx.deck(title, circuit, stimulus, control=[...], options=(...))` puts
  a deck together; `options` are the arguments of `.options` lines.
- `ctx.run(name, deck)` runs a deck and keeps it with the results.
  `ctx.run_many(decks)` runs the decks of a sweep side by side and keeps
  none; `ctx.run_many(decks, keep=True)` keeps them. Both take
  `allowed=`, a list of patterns for log lines that would fail the run
  and are harmless for that deck; each use needs a comment that says why.
- `circuit_sim.measure` takes figures from waveforms: crossings, settling
  time, overshoot, mean, RMS, corner frequency, loop gain and phase margin,
  integrated noise.
- A `Figure` carries the simulated value, the value the specification
  states (`expected`), the limits (`low`, `high`) and their source. Limits
  come from the specification. A figure that fails stays failed: the notes
  of the bench say what follows from it.
- The notes say what the models leave out and which values are assumptions.
- Every bench has at least one graph of real waveforms, with units on its
  axes. Looking at the waveform is part of the work: a run can end with
  plausible numbers and a circuit that rests half way.
- A bench that raises an error becomes a record "did not run" and does
  not stop the others. The raw vectors of every deck are in
  `.work/<block>/<bench>.<deck>.npz`, internal nodes of subcircuits
  included: that is where to look when a result surprises.

## Traps of the Simulator

What ngspice did during this work, and what the package or the models do
about it. Each one cost a wrong result or a stopped run before it was
found.

- **An operating point that is not one.** When an operating point does
  not converge, ngspice tries other methods and at last a short transient
  with ramped sources, whose end it reports as the operating point,
  settled or not. The numbers of such a point are wrong and look fine: a
  gate driver at half its supply, a node at 3 V with no load. The package
  fails a run whose log holds "source stepping failed" or "Transient op
  started"; do not allow those lines. Parts with two stable states cause
  it (comparators with hysteresis, latches, the sequencer), and so do
  very steep steps and amplifier models that rest against a rail. What
  helps: leave such parts out of a bench that needs a static transfer
  only; or take the static value from the end of a transient that starts
  from a defined state; `.nodeset` on the state nodes; `.ic` with `uic`
  only for a start from zero. The operating point of a board without
  supply is singular: such decks start with `uic`.
- **A loop with several stable states starts in any of them.** The path
  through the comparators, the sequencer and the range switches is stable
  in more than one range, and the search for the operating point ends in
  one of them without a message. A first run of `system/profile` began in
  range 3 for that reason and showed no step up. A bench with the
  sequencer in its circuit sets the state in which the run starts: the
  benches of the range logic and `system/profile` hold the state nodes
  at their levels at rest while the operating point is found (`rest()`
  in `benches/range_logic/common.py`), and `system/profile` carries a
  figure for the range in which the run starts.
- **Breakpoints of transmission lines.** A delay built from a
  transmission line sets a breakpoint at each edge, and two breakpoints a
  few attoseconds apart stop a run with "timestep too small". The delay
  element `DLY` in `models/logic.lib` holds no line: it is a rate-limited
  node with a threshold, which delays both edges and lets no pulse pass
  that is shorter than its delay.
- **The current tolerance with switches of milliohms.** The solver asks a
  device for its current within 1 pA by default. A transistor that is on
  has 50 S to 250 S, and the noise of the node voltages times that
  conductance is larger, so a run that carries microamperes through such
  a switch stops. Those decks take `options=("abstol=1e-9",)`, with a
  comment, and no more than that where a bench reads nanoamperes. In long
  runs `trtol=1` helped where that alone did not.
- **Logic made of smooth functions settles half way.** A latch or a timer
  whose own output takes away its drive stops at a middle level, a
  request at 1.6 V or a gate at half its supply, and the run looks fine.
  The sign is a logic node that rests between its levels. The rules that
  hold in `models/sequencer.lib`: a condition never names the latch that
  it sets or clears; feedback goes through a delayed copy; an enable that
  gates a strong discharge is a very steep step. Hard thresholds are no
  way out: a comparison in a behavioral source stops the run, so the
  steps are `tanh` functions and every state node has a capacitor.
- **Brace expressions are pasted as text.** `{1/ron - 1/roff}*v(c)`
  multiplies the last term only. A sum is computed with a `.param` line
  first.
- **The simulator goes on after an error.** A run with an error line in
  its log fails here: "error", "singular matrix", "timestep too small",
  "no such vector" and more. The line in which ngspice repeats the title
  of a deck is not judged, because a title may hold any word.
- **Files of the manufacturers and the compatibility mode.** Their models
  are written for PSpice. The package turns the compatibility mode on by
  itself when a circuit holds such a model; without it a model can give
  wrong numbers with no message. Before that it copies the file into the
  scratch folder and changes five matters of form, none of a value: a
  byte order mark, tabs, blanks in front of a line, a `.param` line
  without its equals sign and a doubled `PARAMS:` keyword. The option
  `klu` breaks the noise analysis, the pole-zero analysis and such decks:
  do not use it. A deck with a switching model needs a `save` line, or its
  output takes gigabytes. Some of these models find no operating point
  inside a larger circuit, and one stopped every transient under the
  default settings; the benches say which settings they use.
- **Smaller ones.** A behavioral source makes no noise in the noise
  analysis: a noise source is the open-circuit voltage of a resistor. The
  trapezoidal rule leaves a noise of microamperes in the current of a
  quiet branch, and `method=gear` removes it. The function `pwl()` of a
  behavioral source continues the slopes of its end segments beyond them.
  A set pulse that is a function of a ramp can be stepped over: use a
  pulse source. A large maximum step lets the solver jump an abrupt
  event. A file name with a comma makes the library fail. The console
  shows `?` for some units on Windows; the result files and the pages are
  correct.

## When the Schematic Changes

The results describe the netlist of the snapshot. After a change of the
schematic:

1. Export the netlist and write the snapshot:
   `circuit-sim netlist carrier.xml`.
2. Run the benches of the blocks that the change touches, then
   `circuit-sim report`. A bench that names a part that is gone stops and
   says so.
3. Compare the new figures with those in the documents that quote them,
   and update the documents.

The workflow does not make this comparison: it has no KiCad and runs no
bench.

The next change is known: decisions D-95, D-96 and D-98 of the
specification. What it touches here:

- C32 to C34 at 10 nF: the circuits of `analog_rails/monitor`,
  `analog_rails/power-up` and `analog_rails/power-down` hold the three
  capacitors. The bench of the monitor has a case that it labels
  "capacitors of 10 nF", which is the drawn value times ten: with the new
  snapshot that case has to be defined again.
- The position for a capacitor at the non-inverting input of U28: the
  circuits of the blocks `signal_chain`, `range_logic` and `system` take
  every part of the Signal Chain sheet (`chain_refs` in
  `benches/frontend.py`), and the snapshot does not record that a
  position carries no part. While the position is empty it has to be
  left out by name, as the power input does with its list; otherwise the
  three blocks are simulated with a capacitor that nobody chose.
- R14 and C5 fitted: only `power_input/replug-module` holds them, in its
  runs with the damper; its runs without the damper then stand for a
  circuit that is no longer the drawn one, and the bench has to say so.
  The other benches of the power input leave the two parts out through
  the list `NOT_FITTED` in `benches/power_input/common.py`, which they
  have to leave; U9 stays in it (D-97).

The whole suite takes 29 minutes, so the simplest is to run all of it
again and to compare.

## Checks

```sh
.venv/Scripts/python -m pytest --cov
.venv/Scripts/python -m mypy
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Tests that run a deck are marked `needs_ngspice` and are skipped where the
library is not found.

Results on 2026-10-10, on Windows with Python 3.11 and the ngspice 45.2
library of KiCad 10:

| Check | Result |
| --- | --- |
| Tests | 777 pass: 766 run anywhere, 11 need the ngspice library |
| Coverage | 100 % of lines and branches of what is measured, against a floor of 90 %; the module that loads the library runs in a child process and is outside the measurement |
| mypy in strict mode | No issue in 172 source files: `src`, `benches` and `tests` |
| ruff | No finding; every file formatted |
| Result pages | They pass the Markdown linter of the repository |

The same checks are the workflow `Simulation`, which is started by hand
like the others (decision D-22 of the specification). It lints and checks
the types, runs the tests on Linux, Windows and macOS with the oldest and
the newest supported Python, runs the tests that need the library with the
ngspice of a Linux distribution, and builds the wheel and installs it. It
does not run the benches. It has never been started: Linux, macOS, other
versions of Python and other versions of ngspice have not run this
package.

The gates cover the package. They say that it builds the circuit it is
asked for and measures what it says; they say nothing about the board.

## License

Open, for the project owner to decide. The package is MIT in its
`pyproject.toml`, like the other software of the repository. The snapshot
`netlist/carrier.json` is derived from the schematic in
[`../hardware/`](../hardware/README.md#license), whose design files are
under CERN-OHL-P v2, and the decks and result files made from it carry
its parts, values and nets. Whether the snapshot and what is made from it
stay under the license of the hardware or go under MIT with the package
is not decided.

[analog_rails/boost-detector]: results/analog_rails/README.md#analog_railsboost-detector
[analog_rails/boost-output]: results/analog_rails/README.md#analog_railsboost-output
[analog_rails/boost-start]: results/analog_rails/README.md#analog_railsboost-start
[analog_rails/clamps]: results/analog_rails/README.md#analog_railsclamps
[analog_rails/monitor]: results/analog_rails/README.md#analog_railsmonitor
[analog_rails/negative-rail]: results/analog_rails/README.md#analog_railsnegative-rail
[analog_rails/power-down]: results/analog_rails/README.md#analog_railspower-down
[analog_rails/power-up]: results/analog_rails/README.md#analog_railspower-up
[analog_rails/reference]: results/analog_rails/README.md#analog_railsreference
[digital/converter-lines]: results/digital/README.md#digitalconverter-lines
[digital/logic-abuse]: results/digital/README.md#digitallogic-abuse
[digital/logic-input]: results/digital/README.md#digitallogic-input
[digital/module-supply]: results/digital/README.md#digitalmodule-supply
[digital/monitor-channels]: results/digital/README.md#digitalmonitor-channels
[digital/released-pins]: results/digital/README.md#digitalreleased-pins
[digital/side-data]: results/digital/README.md#digitalside-data
[digital/unpowered-inputs]: results/digital/README.md#digitalunpowered-inputs
[ladder/change]: results/ladder/README.md#ladderchange
[ladder/ranges]: results/ladder/README.md#ladderranges
[models/mosfet-csd17577q3a]: results/models/README.md#modelsmosfet-csd17577q3a
[output_stage/on-resistance]: results/output_stage/README.md#output_stageon-resistance
[output_stage/short-circuit]: results/output_stage/README.md#output_stageshort-circuit
[output_stage/terminal]: results/output_stage/README.md#output_stageterminal
[output_stage/turn-off]: results/output_stage/README.md#output_stageturn-off
[output_stage/turn-on]: results/output_stage/README.md#output_stageturn-on
[path_switching/close]: results/path_switching/README.md#path_switchingclose
[path_switching/detector]: results/path_switching/README.md#path_switchingdetector
[path_switching/drop]: results/path_switching/README.md#path_switchingdrop
[path_switching/interlock]: results/path_switching/README.md#path_switchinginterlock
[path_switching/open]: results/path_switching/README.md#path_switchingopen
[path_switching/overvoltage]: results/path_switching/README.md#path_switchingovervoltage
[path_switching/reversal]: results/path_switching/README.md#path_switchingreversal
[path_switching/sag]: results/path_switching/README.md#path_switchingsag
[path_switching/short]: results/path_switching/README.md#path_switchingshort
[path_switching/trip]: results/path_switching/README.md#path_switchingtrip
[power_input/contact-bounce]: results/power_input/README.md#power_inputcontact-bounce
[power_input/current-limit]: results/power_input/README.md#power_inputcurrent-limit
[power_input/load-step]: results/power_input/README.md#power_inputload-step
[power_input/logic-rails]: results/power_input/README.md#power_inputlogic-rails
[power_input/overvoltage]: results/power_input/README.md#power_inputovervoltage
[power_input/path-drop]: results/power_input/README.md#power_inputpath-drop
[power_input/plug-module]: results/power_input/README.md#power_inputplug-module
[power_input/plug-usbc]: results/power_input/README.md#power_inputplug-usbc
[power_input/replug-module]: results/power_input/README.md#power_inputreplug-module
[power_input/switch-over]: results/power_input/README.md#power_inputswitch-over
[power_input/thresholds]: results/power_input/README.md#power_inputthresholds
[power_input/unplug]: results/power_input/README.md#power_inputunplug
[range_logic/hot-plug]: results/range_logic/README.md#range_logichot-plug
[range_logic/jump]: results/range_logic/README.md#range_logicjump
[range_logic/landing]: results/range_logic/README.md#range_logiclanding
[range_logic/load-step]: results/range_logic/README.md#range_logicload-step
[range_logic/reverse]: results/range_logic/README.md#range_logicreverse
[range_logic/supply-leads]: results/range_logic/README.md#range_logicsupply-leads
[range_logic/thresholds]: results/range_logic/README.md#range_logicthresholds
[range_logic/trip]: results/range_logic/README.md#range_logictrip
[signal_chain/common-mode]: results/signal_chain/README.md#signal_chaincommon-mode
[signal_chain/driver-rail]: results/signal_chain/README.md#signal_chaindriver-rail
[signal_chain/frequency]: results/signal_chain/README.md#signal_chainfrequency
[signal_chain/head-room]: results/signal_chain/README.md#signal_chainhead-room
[signal_chain/limiter]: results/signal_chain/README.md#signal_chainlimiter
[signal_chain/noise]: results/signal_chain/README.md#signal_chainnoise
[signal_chain/pedestal]: results/signal_chain/README.md#signal_chainpedestal
[signal_chain/sampling-kick]: results/signal_chain/README.md#signal_chainsampling-kick
[signal_chain/settling]: results/signal_chain/README.md#signal_chainsettling
[signal_chain/transfer]: results/signal_chain/README.md#signal_chaintransfer
[source_meter/external]: results/source_meter/README.md#source_meterexternal
[source_meter/load-step]: results/source_meter/README.md#source_meterload-step
[source_meter/loop]: results/source_meter/README.md#source_meterloop
[source_meter/noise]: results/source_meter/README.md#source_meternoise
[source_meter/pre-regulator]: results/source_meter/README.md#source_meterpre-regulator
[source_meter/rails]: results/source_meter/README.md#source_meterrails
[source_meter/sequence]: results/source_meter/README.md#source_metersequence
[source_meter/setpoint]: results/source_meter/README.md#source_metersetpoint
[source_meter/tracking]: results/source_meter/README.md#source_metertracking
[system/accuracy]: results/system/README.md#systemaccuracy
[system/profile]: results/system/README.md#systemprofile
