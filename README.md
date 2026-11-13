# Anomaly Observatory

A runnable software prototype for a **Synchronized Multimodal Anomaly Array**: matched observation/reference pods, preserved raw recordings, blinded trial planning, frozen screening thresholds, and optional Ollama Cloud interpretation.

This measures physical sensor differences. It does not detect souls or establish spiritual causes. The included acquisition source is a **simulator**; physical pods, hardware drivers, synchronization, and calibration are not yet built or validated.

## Launch the dashboard

From the project directory, with Python 3.11+:

```bash
python -m anomaly_observatory serve
```

Open **http://127.0.0.1:8765** in your browser. No frontend build, Node installation, or Python runtime dependencies are needed.

The local dashboard provides:

- Paired pod charts for all four channels, with explicit simulation/import labels.
- A one-click demonstration, simulated recordings, and validated CSV imports.
- Baseline selection and a frozen screening protocol, required before a trial is analyzed.
- Channel RMS values, thresholds, flags, recording checksums, and CSV/JSON downloads.
- A recording archive that persists across server restarts.
- Blinded schedules with separately stored operator keys.
- Ollama Cloud model discovery and advisory review of a selected trial result.

Start with **Load demonstration**, or choose **New recording → Baseline**, freeze its protocol under **Detection protocol**, then create a **Trial & analysis** using that frozen baseline. A baseline is a noise reference; the app does not certify hardware calibration. Chart traces are reduced to approximately 600 points for display only; the full recording is used in analysis and raw downloads.

Dashboard files are stored in `data/ui/` and custodian keys in `private/ui/`, both ignored by Git. The private key is never served to the browser. Keep it with an independent operator. This is an analyst interface, not an access-controlled multi-user research system: anyone with filesystem access to the server account can read its files.

For AI review, open **AI review** and paste an Ollama API key, or set `OLLAMA_API_KEY` before launch. The saved key stays in the server's private directory and is not returned to the browser. Then use **Refresh models**. A review request sends only the selected result JSON to Ollama Cloud; it does not send raw CSVs or blinded labels, and does not alter numerical results. AI notes are shown in the browser and are not automatically archived.

The server binds to loopback only and checks request hosts, origins, and a per-process request token. It is intended to run on your own computer. Do not expose it directly to a public network. Override local storage locations or port if needed:

```bash
python -m anomaly_observatory serve --port 8800 --data-dir data/ui --private-dir private/ui
```

## Run the CLI

Python 3.11+; the core has no third-party runtime dependencies. From this directory:

```bash
mkdir -p data private
python -m anomaly_observatory simulate data/baseline.csv --seed 42
python -m anomaly_observatory preregister data/baseline.csv data/protocol.json
python -m anomaly_observatory simulate data/trial.csv --seed 91 --inject 1
python -m anomaly_observatory analyze data/trial.csv data/protocol.json data/result.json
python -m anomaly_observatory plan data/blinded-plan.json private/operator-key.json
python -m unittest discover -s tests -v
```

The synthetic injection adds a 1 µT offset to pod A. The magnetic channel should flag; the other channels should remain below their thresholds. Use another seed and omit `--inject` for a null run. Output files are created exclusively so an existing result cannot silently be overwritten. Simulation CSV sidecars preserve generator settings and a SHA-256 checksum. Archive the protocol hash before collecting trials; local files are not tamper-proof preregistration.

Optional install: `pip install -e .` exposes the same commands as `observatory`.

## Ollama Cloud and current models

The direct cloud API needs no local Ollama daemon or GPU. Create a key at https://ollama.com/settings/keys and set `OLLAMA_API_KEY` using your shell or secret manager. Never put the key in a file committed to Git.

```bash
python -m anomaly_observatory models
python -m anomaly_observatory explain data/result.json --model MODEL_NAME_FROM_LIST
```

`models` fetches the current catalog from `https://ollama.com/api/tags`, allowing newly released models without a code update. Choose a model returned by that endpoint; there is no stable universal “newest model” alias. Only `explain` sends the selected result JSON to cloud inference. Raw recordings and the blind key are not included. AI text is advisory and cannot change the numerical screening result. A live authenticated cloud call requires your own API key; the request construction is tested with mocks.

## What the screening test means

For each channel, compute `sqrt(mean((pod_A - pod_B)^2))`. Freeze a threshold at three times the baseline score by default, then compare an independent trial against that fixed value. This is an engineering screen, **not a calibrated statistical hypothesis test**. It has no p-value, modeled false-positive rate, frequency search, causal inference, or correction for serial correlation or multiple comparisons. Stable pod offsets and common-mode signals can hide real differences or inflate baselines. Predefine your controls and inspect artifacts before interpreting a flag.

The four low-rate demonstration channels are magnetic field, sound pressure, light and temperature. `sound_pa` means an already conditioned low-rate measurement, not a raw audio waveform; this prototype does not provide audio, RF, ultrasonic, optical imaging, radiation or spectral acquisition.

## Hardware data contract

A driver can export CSV with this exact header:

```csv
tick,time_s,pod,magnetic_uT,sound_pa,light_lux,temperature_c
0,0.0,A,50.01,0.02,100,21.0
0,0.0,B,50.02,0.02,100,21.0
```

Use a shared hardware trigger/sample counter. `tick` increases per pod and paired timestamps must match exactly. Supply all channels in the documented physical units, at least ten pairs, finite readings, and strictly increasing timestamps. Missing pairs, duplicates and invalid numbers fail analysis rather than being filled in. Imports without a simulator sidecar are labeled `UNVERIFIED IMPORT`: passing CSV validation does not certify acquisition provenance, units, timing, or calibration. Preserve the original native-rate recordings outside this reduced demonstration format.

See [hardware guide](docs/HARDWARE.md) and [experiment protocol](docs/PROTOCOL.md).

## Project status

Implemented: local web dashboard; deterministic paired simulation; complete simulated recording; integrity hashes; baseline protocol; paired RMS screening; randomized condition key; pod swaps; cloud model discovery and advisory reports; CLI; automated tests and GitHub Actions.

Next hardware milestones: choose DAQ and sensor ranges; implement a real hardware adapter and continuous recorder; validate shared-clock skew; calibrate each channel and preserve calibration manifests; expand the data model for independent native-rate streams and dummy channels. Before scientific claims, add a separately reviewed statistical protocol with independent trials, an appropriate null model, multiplicity control and independent replication.
