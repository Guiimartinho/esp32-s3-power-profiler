# Simulation Results

Everything in this folder is a simulation result: circuits taken from
the netlist of the schematic, run in ngspice, with models that are
named beside every result. Nothing here is measured on hardware. A
figure that passes says that the circuit as drawn, with these models,
keeps the limit; it does not say that a built board will.

The pages are written by `circuit-sim report` from the result files;
do not edit them by hand.

| Block | Bench | What is simulated | Pass | Fail | No limit |
| --- | --- | --- | --- | --- | --- |
| analog_rails | [boost-detector](analog_rails/README.md) | Boost converter with the voltage detector of decision D-84 fitted at U9 | 3 | **7** | 12 |
| analog_rails | [boost-output](analog_rails/README.md) | Boost converter: +13V5 with tolerances, against load, and its ripple | 7 | 0 | 21 |
| analog_rails | [boost-start](analog_rails/README.md) | Boost converter as drawn: its start on a source limited to 0.67 A to 0.85 A | 26 | **1** | 17 |
| analog_rails | [clamps](analog_rails/README.md) | Clamp diodes D8 and D9: one analog rail present, the other one absent | 4 | **2** | 3 |
| analog_rails | [monitor](analog_rails/README.md) | Rail monitor: thresholds with tolerances, hysteresis, and the edge of PWR_GOOD | 15 | **2** | 16 |
| analog_rails | [negative-rail](analog_rails/README.md) | -4V_A: its level and the 5 V rail it needs | 7 | 0 | 1 |
| analog_rails | [power-down](analog_rails/README.md) | Power-off and supervisor trip: the order in which the rails fall | 10 | **12** | 2 |
| analog_rails | [power-up](analog_rails/README.md) | Power-up: the order in which the rails arrive | 27 | **1** | 1 |
| analog_rails | [reference](analog_rails/README.md) | Reference line: level under load, impedance with the capacitors as drawn, noise | 4 | 0 | 18 |
| analog_rails | [supply-noise](analog_rails/README.md) | Noise and ripple of +12V_A and -4V_A, and what passes from the rails ahead | 2 | 0 | 17 |
| digital | [converter-lines](digital/README.md) | Converter lines: edges behind 47 ohm and 220 ohm, cost in timing, reading window | 16 | **2** | 15 |
| digital | [logic-abuse](digital/README.md) | A logic input at +12 V, at -12 V and under a contact discharge of 8 kV | 9 | **5** | 11 |
| digital | [logic-input](digital/README.md) | A logic input: edge, levels, open line, load on the device under test | 22 | 0 | 1 |
| digital | [module-supply](digital/README.md) | The 5 V of the controller module against the 5 V rail: which way current flows | 6 | **1** | 4 |
| digital | [monitor-channels](digital/README.md) | Monitor channels at rest: scale, tolerance, input leakage, VIN at -20 V and +20 V | 18 | **3** | 7 |
| digital | [monitor-sampling](digital/README.md) | Monitor converter while it samples: charge step, settling, edges of the slow SPI bus | 10 | 0 | 4 |
| digital | [released-pins](digital/README.md) | Lines of the controller with its pins released, and the two status lines | 24 | 0 | 2 |
| digital | [side-data](digital/README.md) | Side data chain: load pulse, shift and the sixteen bits at the controller | 12 | 0 | 2 |
| digital | [translator-supply](digital/README.md) | Supply of the user side of the translator: clamp levels, drop at rest, sag | 18 | 0 | 1 |
| digital | [unpowered-inputs](digital/README.md) | Controller lines driven high into parts that have no supply | 10 | 0 | 2 |
| ladder | [change](ladder/README.md) | A range change at the ladder: make-before-break of the range switches | 8 | 0 | 0 |
| ladder | [ranges](ladder/README.md) | The four ranges at rest: shunt seen by the amplifier and burden voltage | 12 | 0 | 6 |
| models | [analog-rails-b0530w](models/README.md) | B0530W models against the datasheet | 9 | 0 | 2 |
| models | [analog-rails-detector](models/README.md) | 803-type voltage detector model against its datasheet | 4 | 0 | 0 |
| models | [analog-rails-lm27761](models/README.md) | LM27761 models against the datasheet | 14 | 0 | 0 |
| models | [analog-rails-lmr62014](models/README.md) | LMR62014 models against the datasheet | 11 | **2** | 2 |
| models | [analog-rails-lt3042](models/README.md) | LT3042 model against its datasheet | 15 | 0 | 0 |
| models | [analog-rails-mcp6569](models/README.md) | MCP6569 model (open-drain output) against its datasheet | 8 | 0 | 0 |
| models | [analog-rails-mlcc](models/README.md) | Ceramic capacitor with its loss under bias against the cited curves | 8 | 0 | 0 |
| models | [analog-rails-ref5025](models/README.md) | REF5025 model against its datasheet | 15 | 0 | 0 |
| models | [digital-1n5819hw](models/README.md) | 1N5819HW model against its datasheet | 11 | 0 | 0 |
| models | [digital-ads8860](models/README.md) | ADS8860 digital pins: model against the datasheet | 6 | 0 | 0 |
| models | [digital-bat54s](models/README.md) | BAT54S model against its datasheet | 15 | 0 | 0 |
| models | [digital-mcp3208](models/README.md) | MCP3208 inputs: model against the datasheet | 7 | 0 | 0 |
| models | [digital-mcp9700a](models/README.md) | MCP9700A model against its datasheet | 6 | 0 | 0 |
| models | [digital-rp2350](models/README.md) | Controller module: pad and supply models against the datasheets | 15 | 0 | 0 |
| models | [digital-sn74lv165a](models/README.md) | SN74LV165A model against its datasheet | 7 | 0 | 0 |
| models | [digital-sn74lvc8t245](models/README.md) | SN74LVC8T245 model against its datasheet | 23 | 0 | 0 |
| models | [digital-tpd4e1u06](models/README.md) | TPD4E1U06 model against its datasheet | 13 | 0 | 0 |
| models | [mosfet-csd17577q3a](models/README.md) | CSD17577Q3A model against its datasheet | 4 | 0 | 2 |
| models | [mosfet-irlml0030](models/README.md) | IRLML0030 model against its datasheet | 4 | 0 | 2 |
| models | [output-stage-buffer](models/README.md) | OPA197 model with a capacitive load behind an isolation resistor | 10 | **7** | 4 |
| models | [output-stage-suppressor](models/README.md) | PTVS15VS1UR model against its datasheet | 6 | 0 | 6 |
| models | [output-stage-transistor](models/README.md) | CSD17577Q3A at the limits of its datasheet: the variants of the output stage | 5 | 0 | 8 |
| models | [path-switching-bc847b](models/README.md) | BC847B model against its datasheet | 8 | 0 | 3 |
| models | [path-switching-bss138](models/README.md) | BSS138 model of the path switching sheet against its datasheet | 9 | 0 | 1 |
| models | [path-switching-fuse](models/README.md) | Model of the fuse 0466004.NR against its datasheet | 1 | 0 | 2 |
| models | [path-switching-smaj20ca](models/README.md) | SMAJ20CA model against its datasheet | 9 | 0 | 0 |
| models | [power-input-capacitors](models/README.md) | Capacitor models of the power input against their datasheets | 13 | **1** | 0 |
| models | [power-input-diodes](models/README.md) | 1N5819HW, SMAJ10A, TPD4E1U06 and LED models against their datasheets | 14 | 0 | 4 |
| models | [power-input-limiter](models/README.md) | TPS259621 model against its datasheet | 24 | 0 | 0 |
| models | [power-input-multiplexer](models/README.md) | TPS2116 model against its datasheet | 16 | 0 | 1 |
| models | [power-input-regulator](models/README.md) | LP5907-3.3 model against its datasheet | 14 | 0 | 0 |
| models | [power-input-supervisor](models/README.md) | TPS3808G01 model against its datasheet | 6 | 0 | 3 |
| models | [range-logic-mcp6561](models/README.md) | MCP6561 model against its datasheet: thresholds, hysteresis and delay | 4 | 0 | 6 |
| models | [signal-chain-ad8421](models/README.md) | AD8421 model against its datasheet | 35 | **2** | 1 |
| models | [signal-chain-ads8860](models/README.md) | ADS8860 analog input and reference pin: model against the datasheet | 7 | 0 | 1 |
| models | [signal-chain-opa197](models/README.md) | OPA197 model against its datasheet | 21 | 0 | 2 |
| models | [signal-chain-opa365](models/README.md) | OPA365 model against its datasheet | 17 | 0 | 1 |
| models | [source-meter-lt3080](models/README.md) | LT3080 model of the source meter against its datasheet | 18 | **3** | 15 |
| models | [source-meter-mcp4921](models/README.md) | MCP4921 model of the source meter against its datasheet | 11 | 0 | 0 |
| models | [source-meter-parts](models/README.md) | Diode, transistor, bead and inductor of the source meter against their datasheets | 19 | 0 | 1 |
| models | [source-meter-tps63020](models/README.md) | TPS63020 model of the source meter against its datasheet | 16 | **2** | 3 |
| output_stage | [guard](output_stage/README.md) | The guard buffer: stability with the guard ring, static error, range change, output off | 14 | 0 | 13 |
| output_stage | [on-resistance](output_stage/README.md) | The closed output pair at 1 A: burden behind the shunts, over the output range | 4 | 0 | 8 |
| output_stage | [short-circuit](output_stage/README.md) | A short circuit at the closed output: current, trip, energy and voltages | 58 | **2** | 57 |
| output_stage | [terminal](output_stage/README.md) | The output terminal under abuse: reversed source, live source on the open output, charged capacitor on a lower output | 17 | 0 | 30 |
| output_stage | [turn-off](output_stage/README.md) | The output switch opens under load: gate, current, terminal and suppressor | 33 | **3** | 27 |
| output_stage | [turn-on](output_stage/README.md) | The output switch closes: gate ramp, output ramp and in-rush into a capacitor | 25 | **1** | 7 |
| path_switching | [close](path_switching/README.md) | A mode pair closes on a live supply: gate ramp and source follower | 28 | 0 | 12 |
| path_switching | [detector](path_switching/README.md) | The over-voltage detector of VIN: levels with tolerances and reaction time | 12 | **2** | 6 |
| path_switching | [drop](path_switching/README.md) | The two paths at rest: drop at 1 A, gate drive and current taken from VIN | 12 | **3** | 26 |
| path_switching | [hand-over](path_switching/README.md) | A pair closes while the supply node still holds a higher voltage | 2 | 0 | 4 |
| path_switching | [idle](path_switching/README.md) | The supply node with every path switch open: idle level and decay | 3 | 0 | 5 |
| path_switching | [interlock](path_switching/README.md) | The interlock of the two mode pairs and a change of mode | 29 | 0 | 1 |
| path_switching | [open](path_switching/README.md) | A mode pair opens under load: time to block and the kick of the supply leads | 47 | **3** | 28 |
| path_switching | [overvoltage](path_switching/README.md) | The supply rises above its range while the ampere pair is closed | 27 | **3** | 23 |
| path_switching | [plug](path_switching/README.md) | A supply of +20 V or -20 V is plugged into VIN with the ampere pair open | 24 | 0 | 28 |
| path_switching | [reversal](path_switching/README.md) | The supply reverses while the ampere pair is closed | 15 | **4** | 29 |
| path_switching | [ring](path_switching/README.md) | Ampere mode: a load step to 1 A rings on the supply leads against the capacitor at the load | 4 | 0 | 23 |
| path_switching | [sag](path_switching/README.md) | Ampere mode: the supply node after a load step of 500 mA behind supply leads | 3 | 0 | 4 |
| path_switching | [short](path_switching/README.md) | A short circuit in ampere mode: the trip opens the output and the supply leads kick | 41 | **4** | 30 |
| path_switching | [trip](path_switching/README.md) | Ampere mode: the output opens at 0.5 A to 1.2 A behind 0.5 uH to 3 uH of supply leads | 14 | 0 | 15 |
| path_switching | [withstand](path_switching/README.md) | The VIN terminal from -20 V to +20 V with the ampere pair open | 27 | 0 | 1 |
| power_input | [contact-bounce](power_input/README.md) | A contact of the USB-C cable opens and closes again: what reaches the multiplexer | 22 | 0 | 13 |
| power_input | [current-limit](power_input/README.md) | The current limits of the two inputs and a short circuit of the 5 V rail | 5 | **4** | 10 |
| power_input | [load-step](power_input/README.md) | A load step of 1 A on the 5 V rail: the dip and its recovery with the capacitors as drawn | 11 | 0 | 14 |
| power_input | [logic-rails](power_input/README.md) | The supervisor of the 5 V rail and the two 3.3 V rails: thresholds, delay, start and trip | 15 | **2** | 6 |
| power_input | [overload](power_input/README.md) | A load beyond what the source gives: the rail falls and the supervisor sheds the carrier | 13 | 0 | 6 |
| power_input | [overvoltage](power_input/README.md) | Too much voltage and the wrong polarity at the USB-C receptacle | 9 | **3** | 4 |
| power_input | [path-drop](power_input/README.md) | The drop from each connector to the 5 V rail at the loads of the specification | 9 | 0 | 5 |
| power_input | [plug-module](power_input/README.md) | Plugging the cable of the controller module: in-rush on the port of a computer | 17 | **13** | 8 |
| power_input | [plug-usbc](power_input/README.md) | Plugging a live USB-C source: peak at the receptacle, in-rush, soft start, the 5 V rail | 13 | **2** | 13 |
| power_input | [replug-module](power_input/README.md) | The cable of the module is plugged again: what reaches input 2 of the multiplexer | 35 | **2** | 14 |
| power_input | [switch-over](power_input/README.md) | USB-C plugged while the module input supplies: the change of input and the dip of the rail | 16 | 0 | 8 |
| power_input | [thresholds](power_input/README.md) | The levels at which the limiter and the multiplexer switch, and what the monitor reads | 18 | 0 | 1 |
| power_input | [unplug](power_input/README.md) | The USB-C cable is pulled: the rail falls, the multiplexer changes to the module input | 7 | **1** | 11 |
| range_logic | [blanking](range_logic/README.md) | The blanking time: the old voltage after a change and the pulse of a step down | 4 | 0 | 23 |
| range_logic | [hot-plug](range_logic/README.md) | Hot plug of 100 uF and a short circuit at the output: the surge in the ladder | 14 | **1** | 5 |
| range_logic | [input-clamp](range_logic/README.md) | The comparator inputs with 3V3_A off and the amplifier output at 10 V | 9 | 0 | 4 |
| range_logic | [jump](range_logic/README.md) | The jump path: from the jump threshold at the ladder to range 3 conducting | 12 | 0 | 5 |
| range_logic | [landing](range_logic/README.md) | Load steps with a capacitor at the load: the range reached and the time to a true reading | 1 | **1** | 37 |
| range_logic | [load-step](range_logic/README.md) | Requirement R-07: the drop on a step from 1 uA to 500 mA, and the ladder clamp | 23 | 0 | 7 |
| range_logic | [power-on](range_logic/README.md) | DUT power on into 1000 uF to 3300 uF: the in-rush against the armed trip | 6 | 0 | 6 |
| range_logic | [ramp](range_logic/README.md) | A slow ramp from 1 uA to 1 A and back: one range at a time, no bounce | 18 | 0 | 10 |
| range_logic | [reverse](range_logic/README.md) | Reverse current through the ladder: under-range level and voltage across the ladder | 6 | 0 | 2 |
| range_logic | [supply-leads](range_logic/README.md) | Ampere mode behind supply leads: sag of the supply node, ringing and the trip | 7 | **2** | 9 |
| range_logic | [thresholds](range_logic/README.md) | The three comparator thresholds, with tolerances, and their hysteresis | 31 | 0 | 4 |
| range_logic | [trip](range_logic/README.md) | The over-current trip after 12 us, and the recharge of a load capacitor | 12 | **2** | 10 |
| signal_chain | [common-mode](signal_chain/README.md) | Offset and gain of the chain against the output voltage | 6 | 0 | 14 |
| signal_chain | [driver-rail](signal_chain/README.md) | The driver rail: output of the buffer U28, the rail, and the stability of its loop | 8 | **3** | 11 |
| signal_chain | [frequency](signal_chain/README.md) | Frequency response: input filter and anti-alias filter | 8 | 0 | 9 |
| signal_chain | [head-room](signal_chain/README.md) | Head room of the amplifier near full scale with the output voltage near 0 V | 10 | **2** | 15 |
| signal_chain | [limiter](signal_chain/README.md) | The limiter in front of the converter driver during an over-range | 13 | 0 | 15 |
| signal_chain | [noise](signal_chain/README.md) | Noise of the chain at the converter input, by range | 4 | 0 | 22 |
| signal_chain | [pedestal](signal_chain/README.md) | The pedestal: divider with its 1 uF, the buffer U26 and the reference pin of U27 | 7 | **1** | 10 |
| signal_chain | [reference-line](signal_chain/README.md) | The reference pin of the converter during a conversion: R131 and C89 | 4 | 0 | 8 |
| signal_chain | [sampling-kick](signal_chain/README.md) | The converter input: settling of the sampling kick through R130 and C90 | 6 | **2** | 3 |
| signal_chain | [settling](signal_chain/README.md) | Settling of the chain after a range change | 31 | 0 | 0 |
| signal_chain | [transfer](signal_chain/README.md) | From the shunt voltage to the converter input and to the code, with tolerances | 16 | 0 | 4 |
| source_meter | [enable](source_meter/README.md) | The enable pin of the pre-regulator behind Q1, over the 5 V rail | 11 | 0 | 1 |
| source_meter | [external](source_meter/README.md) | A device above the set-point: current drawn from it, clamps, the 5 V rail | 6 | **2** | 10 |
| source_meter | [filter](source_meter/README.md) | The filter in front of the IN pin: source impedance with and without the damper | 0 | 0 | 18 |
| source_meter | [load-step](source_meter/README.md) | Load steps from microamperes to 100 mA and to the curve: droop, recovery, head room | 28 | 0 | 72 |
| source_meter | [loop](source_meter/README.md) | Loop gain and phase margin: linear regulator, pre-regulator, tracking amplifier | 6 | 0 | 33 |
| source_meter | [noise](source_meter/README.md) | Noise of the source across the 1 kohm shunt of range 0 | 8 | 0 | 2 |
| source_meter | [pre-regulator](source_meter/README.md) | The pre-regulator with its tracking amplifier: start and a load step to the curve | 13 | 0 | 49 |
| source_meter | [rails](source_meter/README.md) | A missing or falling rail, the minimum load and the set-point filter in a hold-off | 16 | 0 | 1 |
| source_meter | [sequence](source_meter/README.md) | Start and stop of the source in the order of rules F-28 and F-29, set-point steps | 21 | **1** | 15 |
| source_meter | [setpoint](source_meter/README.md) | The set-point: DAC code to output voltage, step, ceiling and tolerances | 15 | 0 | 12 |
| source_meter | [short](source_meter/README.md) | Short circuit at the output: current limit, pre-regulator, dissipation of U18 | 20 | 0 | 20 |
| source_meter | [tracking](source_meter/README.md) | The tracking pre-regulator at rest: law, head room on the curve, dissipation | 32 | 0 | 14 |
| system | [accuracy](system/README.md) | From the load current to the code, every range held | 18 | 0 | 0 |
| system | [profile](system/README.md) | A load profile with automatic ranging: sleep, wake, burst, sleep | 7 | 0 | 3 |

Simulator: ngspice-45.2 shared library.
