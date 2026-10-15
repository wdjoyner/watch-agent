# src/agent_prompt.py
"""
Instructions for the local Ollama model used by src/agent_ingest.py.

The instructions are assembled from the repository itself, so they never
drift from the format:

  * docs/YAML_FORMAT.md        - the complete record format (keys, enums, null rule)
  * a few real records in data/ - shown as worked examples

agent_ingest.py sends these instructions with every request, so editing
YAML_FORMAT.md or the example records takes effect immediately.

The same text can also be baked into the Ollama model (useful for chatting
with it via `ollama run watch-agent`):

    python3 src/agent_prompt.py --modelfile          # rewrites ./Modelfile
    ollama create watch-agent -f Modelfile
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
FORMAT_DOC = ROOT_DIR / "docs" / "YAML_FORMAT.md"
MOVEMENTS_DIR = ROOT_DIR / "data" / "movements"
WATCHES_DIR = ROOT_DIR / "data" / "watches"
MODELFILE = ROOT_DIR / "Modelfile"

DEFAULT_BASE_MODEL = "qwen3:30b"

# How the JSON output differs from the chat-assistant workflow in YAML_FORMAT.md.
HEADER = """\
You are a careful horological archivist. You convert a researcher's notes about
mechanical watches and their movements into database records.

OUTPUT
Return ONE JSON object with exactly three keys:
  "movements": a list of movement records (may be empty)
  "watches":   a list of watch records (may be empty)
  "skipped":   a list of short strings, one per thing in the notes that you could
               not record, saying why (e.g. "Bulova 11AF movement: notes give no
               frequency"). May be empty.
Each record uses exactly the keys, types and enum values in the format below.

The notes may describe only a movement, only a watch, or several of each.
  * Movement only: return it in "movements" and leave "watches" empty.
  * Watch only: its caliber_id must be an EXISTING movement id (the list is given
    with the notes) or a movement you also return. Reuse existing ids exactly;
    do not create a second id for a movement that already exists.

THE MOST IMPORTANT RULE: NEVER GUESS.
  * Every value must come from the notes. Do not fill gaps from your own
    knowledge of watches, even when you are confident.
  * If an optional value is not stated, use null (or [] for lists).
  * Required values for a MOVEMENT: manufacturer, caliber_number, winding_type,
    winding_mechanism, frequency_vph, description. If the notes do not give
    one of these, do NOT return that movement; add a line to "skipped" instead.
  * Required values for a WATCH: brand, model_family, model_name, and a movement
    named in the notes. If the notes do not say which movement the watch uses,
    do NOT return the watch; add a line to "skipped".
  * "description" (movement) and "notes" (watch) summarize what the notes say,
    in one or two sentences. Do not add facts that are not in the notes.
  * Conversions are allowed: 2.5 Hz = 18000 vph, 3 Hz = 21600, 4 Hz = 28800;
    10 ATM = 10 bar = 100 m; power reserve in days x 24 = hours.

The format specification follows. It was written for chat assistants that
reply with fenced YAML blocks; you reply with the JSON object described above
instead. Everything else in it (keys, types, enum values, id rules, null rule)
applies exactly.
"""

# Worked examples. The notes are written for illustration; the expected output
# for examples 1 and 2 is loaded from the real files in data/, so the examples
# always match the current schema.
EXAMPLES = [
    {
        "title": "Movement only, with unknown values left null",
        "existing": "(none relevant)",
        "notes": (
            "Omega cal. 861 - manual-wind chronograph, built on the Lemania 1873 "
            "ebauche. Beats at 21,600 vph. Introduced in 1968 to replace the 321: "
            "the column wheel was swapped for a cam-actuated chronograph, which "
            "made it sturdier and simpler to produce."
        ),
        "movements": ["omega_861"],
        "watches": [],
        "skipped": [],
    },
    {
        "title": "Watch only, using a movement that already exists",
        "existing": "omega_354 (Omega 354, Automatic)",
        "notes": (
            "Vintage mid-century Omega Seamaster automatic, the 'bumper' kind - "
            "runs on the cal. 354 hammer-wind movement. No reference number or "
            "dates in my notes."
        ),
        "movements": [],
        "watches": ["omega_vintage_seamaster_bumper"],
        "skipped": [],
    },
    {
        "title": "Not enough information: nothing recorded, reasons given",
        "existing": "(none relevant)",
        "notes": (
            "Saw a 1950s gold dress watch at the show, unsigned movement marked "
            "'AS 1130', 17 jewels, manual wind. Ref 6512 on the caseback."
        ),
        "movements": [],
        "watches": [],
        "skipped": [
            "AS 1130 movement: notes give no frequency (vph)",
            "1950s gold dress watch, ref 6512: notes give no brand or model, "
            "and its movement could not be recorded",
        ],
    },
]

# Further real records shown as plain reference examples.
REFERENCE_RECORDS = [
    ("movements", "seiko_7s26"),
    ("movements", "omega_1120"),
    ("watches", "omega_seamaster_2254_50"),
]


def _load_record(kind: str, rec_id: str):
    path = (MOVEMENTS_DIR if kind == "movements" else WATCHES_DIR) / f"{rec_id}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _examples_text() -> str:
    parts = ["WORKED EXAMPLES (notes -> your JSON reply)"]
    n = 0
    for ex in EXAMPLES:
        movements = [_load_record("movements", i) for i in ex["movements"]]
        watches = [_load_record("watches", i) for i in ex["watches"]]
        if any(r is None for r in movements + watches):
            continue  # example record was renamed or removed; skip the example
        n += 1
        reply = {"movements": movements, "watches": watches, "skipped": ex["skipped"]}
        parts.append(
            f"\nExample {n}: {ex['title']}\n"
            f"Existing movements: {ex['existing']}\n"
            f"Notes:\n{ex['notes']}\n"
            f"Reply:\n{_json(reply)}"
        )
    refs = []
    for kind, rec_id in REFERENCE_RECORDS:
        rec = _load_record(kind, rec_id)
        if rec is not None:
            refs.append(f"A real {kind[:-1]} record from the database:\n{_json(rec)}")
    if refs:
        parts.append("\nMORE REAL RECORDS (for style and level of detail)\n\n" + "\n\n".join(refs))
    return "\n".join(parts)


def build_system_prompt() -> str:
    """The complete, static instructions (same for every set of notes)."""
    fmt = FORMAT_DOC.read_text(encoding="utf-8")
    return (
        f"{HEADER}\n"
        f"===== BEGIN FORMAT SPECIFICATION (docs/YAML_FORMAT.md) =====\n"
        f"{fmt.strip()}\n"
        f"===== END FORMAT SPECIFICATION =====\n\n"
        f"{_examples_text()}\n"
    )


def existing_records_summary() -> str:
    """List of the movements and watches already in data/, for the user message."""
    lines = ["Existing movements (reuse these ids exactly):"]
    for p in sorted(MOVEMENTS_DIR.glob("*.yaml")):
        rec = _load_record("movements", p.stem) or {}  # (a broken file shows as '?')
        label = f"{rec.get('manufacturer', '?')} {rec.get('caliber_number', '?')}, {rec.get('winding_type', '?')}"
        lines.append(f"  {p.stem} ({label})")
    lines.append("Existing watches (do not return these again):")
    for p in sorted(WATCHES_DIR.glob("*.yaml")):
        rec = _load_record("watches", p.stem) or {}
        lines.append(f"  {p.stem} ({rec.get('brand', '?')} {rec.get('model_name', '?')})")
    return "\n".join(lines)


def build_user_message(notes: str) -> str:
    return (
        f"{existing_records_summary()}\n\n"
        f"Notes:\n{notes.strip()}\n\n"
        "Reply with the JSON object only."
    )


def modelfile_text(base_model: str = DEFAULT_BASE_MODEL) -> str:
    prompt = build_system_prompt().replace('"""', "'''")
    return (
        "# Generated by `python3 src/agent_prompt.py --modelfile`; edit\n"
        "# docs/YAML_FORMAT.md or src/agent_prompt.py instead of this file.\n"
        "# agent_ingest.py sends the same instructions with every request, so\n"
        "# this SYSTEM block only matters when you chat via `ollama run watch-agent`.\n"
        f"FROM {base_model}\n"
        "PARAMETER temperature 0.1\n"
        "PARAMETER num_ctx 16384\n"
        f'SYSTEM """\n{prompt}"""\n'
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelfile", action="store_true", help="rewrite ./Modelfile with these instructions")
    ap.add_argument("--base", default=DEFAULT_BASE_MODEL, help=f"base Ollama model (default {DEFAULT_BASE_MODEL})")
    args = ap.parse_args(argv)
    if args.modelfile:
        MODELFILE.write_text(modelfile_text(args.base), encoding="utf-8")
        print(f"Wrote {MODELFILE.relative_to(ROOT_DIR)} (FROM {args.base}). Now run:")
        print("    ollama create watch-agent -f Modelfile")
    else:
        sys.stdout.write(build_system_prompt())
    return 0


if __name__ == "__main__":
    sys.exit(main())
