"""Dependency-free acquisition contract and pre-specified paired analysis."""
import csv
import hashlib
import json
import math
import random
from pathlib import Path

CHANNELS = {'magnetic_uT': 'µT', 'sound_pa': 'Pa', 'light_lux': 'lux', 'temperature_c': '°C'}
FIELDS = ['tick', 'time_s', 'pod', *CHANNELS]


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simulate(path, seconds=60, rate=20, seed=42, injection=0.0):
    if seconds <= 0 or rate <= 0 or not math.isfinite(seconds) or not math.isfinite(injection):
        raise ValueError('Duration and rate must be positive; values must be finite')
    rng = random.Random(seed)
    with Path(path).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for tick in range(int(seconds * rate)):
            common = math.sin(tick / rate) * 0.1
            for pod in ('A', 'B'):
                writer.writerow(dict(tick=tick, time_s=tick/rate, pod=pod,
                    magnetic_uT=50 + common + rng.gauss(0, .05) + (injection if pod == 'A' else 0),
                    sound_pa=.02 + rng.gauss(0, .001),
                    light_lux=100 + rng.gauss(0, 1),
                    temperature_c=21 + rng.gauss(0, .02)))
    save_new(str(path) + '.meta.json', dict(source='SIMULATED', seed=seed, rate_hz=rate,
        seconds=seconds, injected_magnetic_offset_uT=injection, sha256=digest(path),
        synchronization='Shared synthetic clock; no hardware synchronization demonstrated'))


def load_pairs(path):
    pairs = {}
    previous = {'A': -1, 'B': -1}
    with Path(path).open(newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError(f'CSV header must be {FIELDS}')
        for row in reader:
            tick, time, pod = int(row['tick']), float(row['time_s']), row['pod']
            values = {key: float(row[key]) for key in CHANNELS}
            if pod not in previous or tick < 0 or tick <= previous[pod]:
                raise ValueError('Unknown pod, duplicate tick, or unordered samples')
            if time < 0 or not all(math.isfinite(v) for v in [time, *values.values()]):
                raise ValueError('Non-finite or negative timestamp')
            previous[pod] = tick
            pairs.setdefault(tick, {})[pod] = (time, values)
    if len(pairs) < 10:
        raise ValueError('At least ten paired samples required')
    last_time = -1
    for pair in pairs.values():
        if set(pair) != {'A', 'B'} or pair['A'][0] != pair['B'][0]:
            raise ValueError('Missing or unsynchronized paired sample')
        if pair['A'][0] <= last_time:
            raise ValueError('Timestamps must strictly increase')
        last_time = pair['A'][0]
    return list(pairs.values())


def scores(path):
    pairs = load_pairs(path)
    return {key: math.sqrt(sum((p['A'][1][key]-p['B'][1][key])**2 for p in pairs)/len(pairs))
            for key in CHANNELS}


def preregister(baseline, path, factor=3.0):
    if not math.isfinite(factor) or factor <= 1:
        raise ValueError('Threshold factor must be finite and greater than one')
    baseline_scores = scores(baseline)
    if any(v <= 0 for v in baseline_scores.values()):
        raise ValueError('Zero baseline noise: check calibration and dummy channels')
    save_new(path, dict(version=1, metric='paired_rms_difference',
        baseline_sha256=digest(baseline), factor=factor,
        thresholds={key: value*factor for key, value in baseline_scores.items()},
        interpretation='Engineering screening thresholds, not statistical significance or evidence of a spirit'))


def analyze(recording, protocol):
    spec = json.loads(Path(protocol).read_text())
    if spec.get('version') != 1 or spec.get('metric') != 'paired_rms_difference':
        raise ValueError('Unsupported protocol')
    thresholds = spec['thresholds']
    if set(thresholds) != set(CHANNELS) or any(not math.isfinite(v) or v <= 0 for v in thresholds.values()):
        raise ValueError('Invalid thresholds')
    if digest(recording) == spec['baseline_sha256']:
        raise ValueError('Use a separate recording, not the baseline itself')
    values = scores(recording)
    sidecar = Path(str(recording) + '.meta.json')
    source = 'UNVERIFIED IMPORT'
    if sidecar.exists():
        metadata = json.loads(sidecar.read_text())
        if metadata.get('sha256') != digest(recording):
            raise ValueError('Recording does not match acquisition checksum')
        source = metadata.get('source', source)
    return dict(source=source, recording_sha256=digest(recording), protocol_sha256=digest(protocol),
        channels={key: dict(rms=value, threshold=thresholds[key], unit=CHANNELS[key],
            flagged=value > thresholds[key]) for key, value in values.items()},
        conclusion='Screening flags require artifact checks and independent replication. No spiritual attribution.',
        limitations='No p-values. Serial correlation and multiple comparisons are not modeled. Import provenance and hardware calibration require independent verification.')


def plan(public_path, private_path, repeats=4):
    if repeats < 1:
        raise ValueError('Repeats must be positive')
    if Path(public_path).exists() or Path(private_path).exists():
        raise ValueError('Plan output already exists')
    conditions = ['active', 'sham', 'empty'] * repeats
    rng = random.SystemRandom()
    rng.shuffle(conditions)
    mapping = []
    for index, condition in enumerate(conditions):
        mapping.append(dict(run=f'RUN-{index+1:03}', condition=condition,
                            observation_pod='A' if index % 2 == 0 else 'B'))
    save_new(private_path, mapping)
    Path(private_path).chmod(0o600)
    save_new(public_path, [dict(run=m['run'], observation_pod=m['observation_pod']) for m in mapping])
