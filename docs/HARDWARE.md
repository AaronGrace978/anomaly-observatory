# Physical prototype build specification

This is a design guide, not an assembled or electrically validated instrument. No sensor driver is included. Start with low-voltage, commercially documented sensor modules and a shared-trigger DAQ; choose exact parts after defining sensitivity, bandwidth and budget.

| Subsystem | Two matched pods | Validation required |
|---|---|---|
| Magnetic | Three-axis magnetometers with known range and noise | Known field orientations; hard/soft iron offsets; temperature drift |
| Acoustic | Calibrated microphones, conditioning and anti-alias filters | Known sound pressure; document gain and bandwidth |
| Optical | Photodiodes and transimpedance amplifiers | Dark noise, linearity, calibrated illumination |
| Environment | Temperature, humidity and pressure modules | Compare against reference instruments |
| Timing | Shared DAQ clock/trigger and monotonically increasing counter | Measure channel skew with a common pulse |
| Recording | Buffered native-rate storage and acquisition manifests | Dropout detection, disk exhaustion and restart behavior |

The software demo uses only scalar magnetic, sound, light and temperature readings. A real three-axis magnetometer requires an explicitly defined calibrated scalar reduction or an extended schema. Humidity, pressure and reference/dummy channels require extending this version's schema and analysis.

RF receivers, E-field probes, ultrasound, accelerometers, infrared and optional radiation counters are separate future acquisition subsystems. Specify calibrated passbands, sample rates, dynamic ranges, channel latency, anti-aliasing and transfer functions for each. A single slow CSV must not be used to represent raw high-bandwidth channels.

Use matched mechanical housings, documented wiring, stable isolated supplies where appropriate, and both shielded and unshielded paths when experimentally relevant. Log computer/DAQ activity, mains interference, motion, machinery and radio traffic. Add terminated dummy inputs to identify electronic artifacts. Swapping physical locations and cables helps distinguish location effects from instrument effects.

Store calibration ID, date, operator, instrument serial number, units, uncertainty, gain, sensitivity, bandwidth, clock source, sample rate and firmware in an acquisition manifest. Measure clock skew rather than treating equal software timestamps as proof of simultaneity. Retain raw samples continuously, including quiet periods. These are acceptance requirements for future hardware integration, not capabilities certified by this release.
