# YAML record format (paste this whole file into an AI)

This file is the complete specification for records in `data/`. It is meant to be
pasted, in full, into ChatGPT / Gemini / Claude together with your notes. The
format is enforced by `src/schema.py`; if the two ever disagree, `schema.py` wins.

---

## Instructions for the AI

You are converting notes about mechanical watches and their movements into YAML
records for the `watch-agent` database. Follow these rules exactly:

1. Output one fenced ```yaml code block per file, and put the file path on the line
   just above each block, e.g. `data/movements/omega_1120.yaml`.
2. Every movement goes in `data/movements/<caliber_id>.yaml`; every watch goes in
   `data/watches/<watch_id>.yaml`. The file name must equal the id.
3. Ids use only lowercase letters, digits and underscores: `omega_1120`, `eta_2824_2`.
   No spaces, hyphens, dots or capitals.
4. Use **only** the keys listed below, spelled exactly as shown. Do not invent
   extra keys (no `diameter_mm`, `family`, `model`, `reference_number`, etc.).
   Unknown keys are rejected.
5. If a value is not known, write `null` (or `[]` for lists). **Never guess** a
   jewel count, power reserve, reference number or year.
6. Enum fields must be copied **character for character** from the allowed lists.
7. A watch's `caliber_id` must match a movement file that exists or that you are
   also creating. If the movement is new, output its movement file too.
8. `tests_passed` is a list of mappings, each starting with `- standard:`. Never
   write a bare string like `- METAS Master Chronometer`.
9. Quote any value that looks like a number but is really a label: `caliber_number: '861'`,
   reference numbers `'2254.50.00'`.

---

## Movement file: `data/movements/<caliber_id>.yaml`

| Key | Required | Type | Notes |
|---|---|---|---|
| `caliber_id` | yes | text | lowercase slug, equals file name, e.g. `omega_1120` |
| `manufacturer` | yes | text | e.g. `Omega`, `ETA`, `Seiko` |
| `caliber_number` | yes | text (quoted) | e.g. `'1120'`, `'2892-A2'` |
| `base_caliber` | no | text or null | ebauche/parent, e.g. `ETA 2892-A2` |
| `winding_type` | yes | enum | `Manual` or `Automatic` |
| `winding_mechanism` | yes | enum | see list below; must be `None (Manual)` when `winding_type: Manual`, and must **not** be when `Automatic` |
| `escapement_type` | no | text | default `Swiss Lever`; usual values: `Swiss Lever`, `Co-Axial`, `Chronergy`, `Detent`, `Cylinder` |
| `frequency_vph` | yes | integer | 7200–72000, e.g. `18000`, `21600`, `25200`, `28800`, `36000` |
| `jewels` | no | integer or null | 0–100 |
| `power_reserve_hours` | no | number or null | e.g. `44.0` |
| `hacking` | no | true / false / null | stop-seconds |
| `hand_winding` | no | true / false | default `true` |
| `description` | yes | text, 10+ characters | one or two sentences of history/notes |

Allowed `winding_mechanism` values:

- `None (Manual)`
- `Unidirectional (Pawl/Click)`
- `Bidirectional (Reversing Wheels)`
- `Bidirectional (Seiko Magic Lever)`
- `Bidirectional (Pellaton Pawl)`
- `Bumper / Hammer`
- `Peripheral Rotor`
- `Micro-Rotor / Planetary`

### Example movement

```yaml
caliber_id: omega_1120
manufacturer: Omega
caliber_number: '1120'
base_caliber: ETA 2892-A2
winding_type: Automatic
winding_mechanism: Bidirectional (Reversing Wheels)
escapement_type: Swiss Lever
frequency_vph: 28800
jewels: 23
power_reserve_hours: 44.0
hacking: true
hand_winding: true
description: Refined derivative of the ETA 2892-A2 with rhodium-plated finish and a redesigned automatic bridge.
```

---

## Watch file: `data/watches/<watch_id>.yaml`

| Key | Required | Type | Notes |
|---|---|---|---|
| `watch_id` | yes | text | lowercase slug, equals file name |
| `brand` | yes | text | |
| `model_family` | yes | text | e.g. `Seamaster`, `Speedmaster` |
| `model_name` | yes | text | e.g. `Seamaster 300M Chronometer` |
| `reference_numbers` | no | list of quoted text | `[]` if unknown |
| `caliber_id` | yes | text | must match a movement file |
| `production_year_start` | no | integer or null | 1500–2035 |
| `production_year_end` | no | integer or null | null if still in production; not earlier than start |
| `tests_passed` | no | list of test mappings (below) | `[]` if none |
| `notes` | no | text or null | |

Each entry in `tests_passed`:

| Key | Required | Type | Notes |
|---|---|---|---|
| `standard` | yes | enum | see list below |
| `rated_accuracy_sec_per_day` | no | `[min, max]` | e.g. `[-4.0, 6.0]` for COSC, `[0.0, 5.0]` for METAS |
| `water_resistance_bar` | no | number | |
| `water_resistance_meters` | no | integer | |
| `magnetic_resistance_gauss` | no | integer | e.g. `15000` for METAS |
| `test_notes` | no | text | |

Allowed `standard` values:

- `COSC (ISO 3159)`
- `METAS (Master Chronometer)`
- `Poinçon de Genève`
- `Qualité Fleurier`
- `Japanese Chronometer (JCS)`
- `Observatory Tested`
- `ISO 6425 (Diver's Watch)`
- `ISO 22810 (Standard Water Resistance)`
- `Manufacturer Internal Spec`

### Example watch

```yaml
watch_id: omega_seamaster_2254_50
brand: Omega
model_family: Seamaster Professional 300M
model_name: Seamaster 300M Chronometer
reference_numbers:
  - '2254.50.00'
caliber_id: omega_1120
production_year_start: 1996
production_year_end: 2008
tests_passed:
  - standard: COSC (ISO 3159)
    rated_accuracy_sec_per_day: [-4.0, 6.0]
    water_resistance_bar: 30.0
    water_resistance_meters: 300
  - standard: ISO 6425 (Diver's Watch)
notes: Black wave dial, sword hands, helium escape valve.
```

---

## Checking your files before pushing

From the repository folder:

    python3 src/build_db.py --check

It lists every problem in every file (file name, key, and what was wrong). If you
used an AI, you can paste that error list back to it and ask it to fix the files.
GitHub runs the same check on every push; if it fails, the website keeps showing
the last good version and the error list appears in the Actions log.
