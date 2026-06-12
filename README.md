# vitalforge

Persona-driven synthetic longitudinal health data generator. Produces
deterministic, seeded, distributionally plausible health signal and clinical
record data for demos, tests, and ML fixtures. Pure-math/template generation:
no network access, no LLMs, no real patient data.

## What it generates

### Daily signals (`vitalforge generate`)

| Signal | Model | Unit |
|---|---|---|
| `heart_rate` | Circadian-aware sampling: sleep distribution 22:00-06:00, resting distribution shifted by a sinusoidal circadian factor, probabilistic exercise bursts | bpm |
| `blood_pressure` | Linear start-to-end trend with gaussian noise; morning/evening readings | mmHg |
| `steps` | Daily totals with separate weekday/weekend distributions | steps |
| `sleep` | Nightly episodes: sampled bedtime and duration, 5-20 min onset latency, ~90-minute light/deep/REM cycles that exactly partition the sleep window | min |
| `glucose` | Fasting (07:00) and postprandial (13:00, 19:00) readings with an optional linear trend over the period | mg/dL |
| `weight` | Linear interpolation between start and end weight, N readings per week | kg |
| `activity_energy` | Daily totals with weekday/weekend distributions | kcal |

### Clinical records

Conditions, medications, allergies, immunizations, lab results, and
encounters, as declared in the persona file, with terminology codings
(SNOMED CT, ICD-10, RxNorm, LOINC, CVX).

### Multi-year trajectories (`vitalforge trajectory`)

Yearly health snapshots interpolated from anchor points: blood-pressure
phases, arbitrary named metric series (e.g. `weight_kg`, `resting_hr`),
milestones, encounters, and medication periods.

## Install

```bash
pip install -e .
# with test dependencies:
pip install -e ".[dev]"
```

Requires Python >= 3.10. Runtime dependency: PyYAML.

## CLI usage

```bash
# 30 days of daily signals + clinical records, JSONL
vitalforge generate --persona examples/personas/alex_rivera.yaml \
    --days 30 --seed 42 --out ./out --format jsonl

# 10-year trajectory, JSON
vitalforge trajectory --persona examples/personas/jordan_kim.yaml \
    --years 10 --seed 42 --out ./out --format json
```

`generate` options: `--persona` (required), `--days` (default 30), `--seed`
(default 42), `--start-date` (overrides the persona's `start_date`), `--out`
(default `./out`), `--format` (`json` | `jsonl` | `csv` | `fhir`, default
`json`).

`trajectory` options: `--persona` (required), `--years` (default 10),
`--seed`, `--out`, `--format` (`json` | `jsonl` | `csv`).

## Library usage

```python
from vitalforge import load_persona, build_dataset, build_trajectory_dataset
from vitalforge.output import to_fhir_bundle, write_dataset

persona = load_persona("examples/personas/alex_rivera.yaml")
dataset = build_dataset(persona, days=30, seed=42)
bundle = to_fhir_bundle(dataset)            # FHIR R4 Bundle dict
write_dataset(dataset, out_dir, "jsonl")    # files on disk

trajectory = build_trajectory_dataset(
    load_persona("examples/personas/jordan_kim.yaml"), years=10, seed=42
)
```

## Determinism

The same persona file, parameters (`--days`/`--years`, `--start-date`), and
`--seed` always produce byte-identical output files:

- All randomness flows through a single `random.Random(seed)` consumed in a
  fixed generation order.
- Timestamps derive from the persona's `start_date` (or the `--start-date`
  override), never from the current clock.
- Record ids are UUIDv5 values computed from a fixed namespace and stable
  keys.

Changing the seed changes sampled values but not record structure.

## Persona schema

Personas are YAML or JSON documents (`schema_version: 1`):

```yaml
schema_version: 1

profile:                      # required
  name: Alex Rivera           # required
  birth_date: "1989-04-12"    # required, ISO date
  sex: male                   # required: female | male | other | unknown
  height_cm: 178              # optional

start_date: "2025-03-01"      # required; day 0 / year 0 of generation

baseline:                     # optional; only listed signals are generated
  heart_rate:
    resting_mean: 74          # bpm, daytime baseline (circadian factor adds up to +10)
    resting_std: 4
    active_mean: 140          # exercise-burst distribution
    active_std: 15
    sleep_mean: 62            # 22:00-06:00 distribution
    sleep_std: 3
    samples_per_day: 72       # optional, default 72
    exercise_probability: 0.08  # optional, default 0.08
  blood_pressure:
    systolic_start: 146       # day-0 baseline
    systolic_end: 132         # final-day baseline (linear trend between)
    diastolic_start: 94
    diastolic_end: 84
    std: 5
    readings_per_day: 2       # optional, default 2
  steps:
    weekday_mean: 7200
    weekday_std: 1800
    weekend_mean: 9800
    weekend_std: 2600
  sleep:
    bedtime_hour: 23.25       # decimal hours after the day's midnight
    bedtime_std: 0.5
    duration_mean_hours: 6.7
    duration_std_hours: 0.6
  glucose:
    fasting_mean: 110         # mg/dL
    fasting_std: 8
    postprandial_mean: 144
    postprandial_std: 12
    trend_mg_dl: -6           # optional linear shift over the period, default 0
  weight:
    start_kg: 88.5
    end_kg: 87.2
    std: 0.3
    readings_per_week: 2      # optional, default 2
  activity_energy:
    weekday_mean_kcal: 330
    weekday_std: 80
    weekend_mean_kcal: 470
    weekend_std: 110

conditions:                   # optional clinical history sections
  - text: Essential hypertension
    codes:                    # system: SNOMED | ICD-10 | RxNorm | LOINC | CVX | <full URI>
      - { system: SNOMED, code: "59621000", display: Essential hypertension }
    onset_date: "2025-01-20"
medications:
  - text: Lisinopril 10 mg oral tablet, once daily
    codes: [{ system: RxNorm, code: "314076" }]
    dose: { quantity: 10, unit: mg, frequency: daily }
    start_date: "2025-01-20"  # end_date optional
allergies:        # text, codes, onset_date
immunizations:    # text, codes, date
labs:             # text, codes, value, unit, reference_range, date
encounters:
  - kind: outpatient          # required
    modality: in_person       # optional, default in_person
    service: Primary care — annual physical examination   # required
    reason: Annual physical examination
    providers: [{ role: attending, name: Dr. Naomi Feld, specialty: Internal Medicine }]
    location: Lakeside Primary Care
    time: "2025-01-20T15:00:00Z"  # required
    summary: New diagnosis of essential hypertension.

trajectory:                   # optional; required for `vitalforge trajectory`
  blood_pressure:
    phases:                   # piecewise-linear systolic/diastolic ranges
      - { year_start: 0, year_end: 5, systolic: [118, 116], diastolic: [76, 74] }
  metrics:                    # name -> anchor points, linearly interpolated
    weight_kg:                # points use `value` (exact) ...
      - { year: 0, value: 64.0 }
      - { year: 10, value: 63.5 }
    resting_hr:               # ... or `mean` + optional `std` (sampled with noise)
      - { year: 0, mean: 62, std: 3 }
      - { year: 10, mean: 55, std: 3 }
  milestones:
    - { year: 1, month: 5, event: Completed first marathon., kind: lifestyle }
  encounters:
    - { year: 0, quarter: 1, kind: outpatient, service: Annual physical,
        provider: Dr. Priya Anand, specialty: Family Medicine,
        location: Hillcrest Family Health, outcome: All vitals within normal range }
  medications:                # active for start_year <= year < end_year
    - { name: Lisinopril, start_year: 0, end_year: 3, detail: 10 mg daily }
```

Example personas: [`examples/personas/alex_rivera.yaml`](examples/personas/alex_rivera.yaml)
(hypertension + prediabetes, 30-day treatment-response window) and
[`examples/personas/jordan_kim.yaml`](examples/personas/jordan_kim.yaml)
(healthy adult with a 10-year trajectory).

## Output formats

- **json** — single document: `generator` metadata, `persona`, and record
  arrays (`signals` + `clinical`, or `trajectory`).
- **jsonl** — one record per line, preceded by a `metadata` record.
- **csv** — one file per section: `<slug>_signals.csv`,
  `<slug>_clinical.csv`, `<slug>_trajectory.csv` (flat rows; BP expands to
  systolic/diastolic rows, sleep to per-episode rows).
- **fhir** — FHIR R4 `Bundle` (type `collection`), daily datasets only:
  - `Patient`, `Condition`, `MedicationStatement`, `AllergyIntolerance`,
    `Immunization`, `Encounter`, and `Observation` (labs).
  - Signal observations: blood pressure (LOINC 85354-9 with 8480-6/8462-4
    components), glucose (2339-0), and weight (29463-7) are one Observation
    per reading; heart rate (8867-4, daily mean), steps (41950-7), active
    energy (41981-2), and sleep duration (93832-4) are one daily-summary
    Observation per day.

## Record shapes

Signal record (all signals except sleep):

```json
{
  "record_type": "signal",
  "signal": "glucose",
  "id": "…",
  "start": "2025-03-01T00:00:00Z",
  "end": "2025-03-02T00:00:00Z",
  "unit": "mg/dL",
  "samples": [{ "t": "2025-03-01T07:12:00Z", "value": 109.4, "context": "fasting" }]
}
```

Sleep records carry `episodes` (stage, start, end, duration_min),
`sleep_onset`, `latency_min`, and `total_sleep_min` instead of `samples`.
Blood-pressure samples carry `systolic`/`diastolic` instead of `value`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Tests cover determinism (byte-identical re-runs), distribution sanity
(physiologic bounds, circadian dip, sleep-cycle accounting), persona schema
validation, output formats, and CLI behavior. All tests run offline.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Disclaimer

All generated data is synthetic. It encodes simplified statistical models and
is not suitable for clinical decision-making, medical research conclusions,
or as a substitute for real-world evidence.
