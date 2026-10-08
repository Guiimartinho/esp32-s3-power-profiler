# Component Checks

A component check confirms that a candidate part, or a peripheral of the
microcontroller, does what the design asks of it. The answers come from the
manufacturer's documentation, never from memory.

## Open Checks

The list mirrors section 16 of the [specification](../specification.md). A
check is closed when its record is merged and the specification is updated.

| Subject | Questions | Record | Status |
| --- | --- | --- | --- |
| AD8421 | Common-mode range with +12 V / −4 V, settling time and noise at G = 20, bias current | — | Open |
| ADS8860 | Convert-start and data timing against the I2S frame and the delay of the logic device, input driver, reference drive | — | Open |
| ESP32-S3 I2S | Integer clock dividers, master and slave ports on shared clocks, DMA block callbacks | — | Open |
| LT3080 | Dropout on both supply pins with 0.45 V of headroom, minimum load, thermal resistance | — | Open |
| Pre-regulator (TPS63020) | Stability with the difference amplifier in the feedback path, the 5.5 V end, ripple after the filter, land pattern | — | Open |
| Range MOSFETs, multiplexer and clamp (CSD17577Q3A, IRLML0030, MUX509, BAV199) | Leakage at 40 °C, gate-charge injection into VOUT, surge current of the clamp | — | Open |
| Comparators (MCP6561, MCP6562) | Propagation delay, input range, thresholds and hysteresis | — | Open |
| Logic device (MAX II EPM240) | Supply, pins while blank and while unpowered, internal oscillator, pull-ups; description of the range logic | — | Open |
| Gate drivers (TC4427) | Input thresholds with 3.3 V logic, delay, supply current, output without supply | — | Open |
| Analog rails (LMR62014, LT3042, LM27761, LP5907, REF5025) | Load of each rail, start-up order, noise, −4 V at the lowest USB voltage | — | Open |
| VBUS transients | Hot-plug overshoot against the 5.8 V and 6 V ratings on the 5 V rail | — | Open |
| Level translator (SN74LVC8T245) | Supply current drawn from the buffer, behavior when VOUT is off or below 1.65 V | — | Open |
| USB-C power | CC thresholds, behavior on 500 mA, 1.5 A and 3 A sources | — | Open |
| Development board in hand | Header labels, row spacing (25.40 mm expected), module marking (N8R2 or N16R2), LED pin, 5 V path | — | Open |
| Monitor ADC (MCP3208) | Input range and source impedance of each channel, SPI mode shared with the DAC | — | Open |
| Board interface | Boundary parts with one power domain off, series resistor values | — | Open |
| Path resistance | Switches, shunt, fuse and connectors against the 150 mV limit in ampere mode | — | Open |
| Library symbols | Pin numbers of every symbol taken from the KiCad library against its datasheet | — | Open |
| USB device stack | TinyUSB component for ESP-IDF v6.0: name, version and license | — | Open |

The schematic in [`hardware/kicad/`](../../hardware/kicad/) is a draft drawn
with these candidates before any record was closed (decision D-37 of the
specification). A closed record can therefore change the schematic.

## Writing a Record

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to a file named after the subject in
   lowercase, for example `ad8421.md`.
2. Use the current datasheet from the manufacturer. Record its title,
   document number, revision and date.
3. For every question, quote the parameter with its test condition, the
   minimum, typical and maximum values, and the page, table or figure.
4. Compare the worst-case values with the design value and state the margin.
5. Give a verdict and list the changes the specification needs.
6. Update the table above and section 16 of the specification.

Datasheet files are not added to the repository. Link to the manufacturer's
page instead.
