# Firmware

ESP-IDF firmware for the ESP32-S3-WROOM-1 module. It acquires the samples,
controls the analog front end and streams the data to the host over USB.

Status: not started. The first code arrives with the risk prototypes of
phase 1.

## Planned Layout

```text
firmware/
├── CMakeLists.txt       ESP-IDF project file (added with the first prototype)
├── sdkconfig.defaults   Project configuration defaults
├── main/                Application entry point
└── components/
    ├── acq/             I2S capture, alignment, decimation, sample words
    ├── afe/             Range control, mode and output switches, fault latch
    ├── smu/             DAC, voltage ramp, regulator enable, power budget
    ├── monitor/         Slow ADC channels: VOUT, VIN, VBUS, CC, temperature
    ├── cal/             Calibration table in NVS, zero calibration
    ├── proto/           Frame encoding and decoding, command dispatch
    ├── usb_link/        TinyUSB CDC ACM, host-open detection
    └── app/             Device state machine, start-up self-test
```

## Architecture Rules

These rules come from section 6 of the
[specification](../docs/specification.md):

- The sampling clock comes from the I2S peripheral. There is no per-sample
  interrupt and no per-sample driver call.
- Core 0 runs the acquisition. Core 1 runs USB, commands and monitoring.
- `acq` depends only on the driver layer. Only `app` calls across
  components. Only `cal` writes to flash.
- No flash writes while streaming, and no PSRAM in the real-time path.
- WiFi and Bluetooth stay disabled while capturing.
- Section 5 of the specification is the only source for pin assignments.

## Toolchain

The firmware targets [ESP-IDF](https://github.com/espressif/esp-idf) v6.0
and the `esp32s3` chip target. Once the project file exists, the usual
commands apply:

```sh
idf.py set-target esp32s3
idf.py build
idf.py -p PORT flash monitor
```
