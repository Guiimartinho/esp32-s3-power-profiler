# Component Checks

A component check confirms that a candidate part, or a peripheral of the
microcontroller, does what the design asks of it. The answers come from the
manufacturer's documentation, never from memory.

## Open Checks

The list mirrors section 16 of the [specification](../specification.md). A
check is closed when its record is merged and the specification is updated.

| Subject | Questions | Record | Status |
| --- | --- | --- | --- |
| AD8421 | Common-mode range with +12 V / −5 V, settling time and noise at G = 20, bias current | — | Open |
| ADS8860 | Convert-start and data timing against the I2S frame, input driver, reference drive | — | Open |
| ESP32-S3 I2S | Integer clock dividers, master and slave ports on shared clocks, DMA block callbacks | — | Open |
| LT3080 | Dropout on both supply pins, minimum load, thermal resistance | — | Open |
| Pre-regulator | Feedback injection range, stability from 1.4 V to 5.6 V, ripple after the filter | — | Open |
| Range MOSFETs, multiplexer and clamp | Leakage at 40 °C, gate-charge injection into VOUT | — | Open |
| Comparators | Propagation delay, input range, thresholds and hysteresis | — | Open |
| Level translator | Supply current drawn from VOUT, behavior when VOUT is off | — | Open |
| USB-C power | CC thresholds, behavior on 500 mA, 1.5 A and 3 A sources | — | Open |
| Development board in hand | Header labels, row spacing, module marking, LED pin, regulator rating, 5 V path | — | Open |
| Monitor ADC | Part selection, input range and source impedance, SPI mode shared with the DAC | — | Open |
| Board interface | Boundary parts with one power domain off, series resistor values | — | Open |
| USB device stack | TinyUSB component for ESP-IDF v6.0: name, version and license | — | Open |

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
