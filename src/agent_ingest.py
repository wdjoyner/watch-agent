# src/agent_ingest.py
"""
Turn plain-text notes into validated YAML records using a local Ollama model.

One set of notes:
    python3 src/agent_ingest.py "Omega 1120 automatic, based on ETA 2892-A2, 28800 vph, ..."
    python3 src/agent_ingest.py --file notes/omega_1120.txt
    pbpaste | python3 src/agent_ingest.py                    # from the clipboard

A folder of note files (.txt / .md, subfolders included):
    python3 src/agent_ingest.py --dir ~/Research/Bulova --dry-run   # preview, writes nothing to data/
    python3 src/agent_ingest.py --dir ~/Research/Bulova

Notes may describe only a movement, only a watch, or several of each.

Every record the model returns is checked before anything is written:
  1. the schema (src/schema.py), exactly as build_db.py checks it;
  2. the watch's caliber_id must be an existing movement or one written now;
  3. "never guess": numbers, caliber numbers and reference numbers must
     appear in the notes (unit conversions such as Hz -> vph are allowed).
Problems are sent back to the model to fix (up to --retries times). Records
that still fail are NOT written to data/; they are saved, with the reasons, in
ingest_runs/<date-time>/rejected/ and listed in ingest_runs/<date-time>/report.txt.
Existing files in data/ are never replaced unless --overwrite is given.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_db  # noqa: E402
from agent_prompt import build_system_prompt, build_user_message  # noqa: E402
from schema import MovementSpec, WatchReference  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent.parent
MOVEMENTS_DIR = ROOT_DIR / "data" / "movements"
WATCHES_DIR = ROOT_DIR / "data" / "watches"
RUNS_DIR = ROOT_DIR / "ingest_runs"
NOTE_SUFFIXES = {".txt", ".md", ".markdown", ".text"}

MAX_CTX = 40960  # qwen3:30b context limit in Ollama
OUTPUT_RESERVE = 8192  # tokens kept free for the model's reply


class IngestionBundle(BaseModel):
    """Shape of the model's reply. Passed to Ollama as a JSON schema, which
    constrains generation to valid JSON with exactly these keys and types."""
    movements: list[MovementSpec] = Field(default_factory=list)
    watches: list[WatchReference] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


# ------------------------------------------------------------ result objects
@dataclass
class Record:
    kind: str  # "movement" or "watch"
    data: dict
    model: BaseModel | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def rec_id(self) -> str:
        key = "caliber_id" if self.kind == "movement" else "watch_id"
        return str(self.data.get(key) or "(no id)")

    @property
    def path(self) -> Path:
        folder = MOVEMENTS_DIR if self.kind == "movement" else WATCHES_DIR
        return folder / f"{self.rec_id}.yaml"


@dataclass
class NoteResult:
    source: str
    accepted: list[Record] = field(default_factory=list)
    rejected: list[Record] = field(default_factory=list)
    skipped_by_model: list[str] = field(default_factory=list)
    failure: str | None = None  # the whole note could not be processed
    written: list[str] = field(default_factory=list)
    kept_existing: list[str] = field(default_factory=list)


# ------------------------------------------------------- "never guess" checks
def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _numbers(text: str) -> list[float]:
    t = re.sub(r"(?<=\d)[,  '](?=\d{3}\b)", "", text)  # 18,000 -> 18000
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]


def _stated(value: float, nums: list[float], factors=(1.0,), rel_tol: float = 1e-6) -> bool:
    """True if value (or value/factor, for a unit conversion) appears in the notes."""
    for f in factors:
        target = value / f
        for n in nums:
            if abs(n - target) <= max(rel_tol * abs(target), 1e-9):
                return True
    return False


def grounding_errors(rec: Record, notes: str, caliber_numbers: dict[str, str]) -> list[str]:
    """Values that do not appear in the notes (i.e. were probably guessed)."""
    nums = _numbers(notes)
    flat = _alnum(notes)
    errs = []
    unstated = "{} = {!r} is not stated in the notes. {}"
    use_null = "If the notes do not give it, use null."

    if rec.kind == "movement":
        m: MovementSpec = rec.model
        if _alnum(m.caliber_number) not in flat:
            errs.append(unstated.format("caliber_number", m.caliber_number,
                                        "Copy the caliber number as written in the notes."))
        # vph, or Hz (x7200), or beats per second (x3600)
        if not _stated(m.frequency_vph, nums, (1, 7200, 3600)):
            errs.append(unstated.format("frequency_vph", m.frequency_vph,
                                        "If the notes give no frequency, leave this movement out "
                                        "and explain why in 'skipped'."))
        if m.jewels is not None and not _stated(m.jewels, nums):
            errs.append(unstated.format("jewels", m.jewels, use_null))
        if m.power_reserve_hours is not None and not _stated(m.power_reserve_hours, nums, (1, 24)):
            errs.append(unstated.format("power_reserve_hours", m.power_reserve_hours, use_null))
    else:
        w: WatchReference = rec.model
        for ref in w.reference_numbers:
            if _alnum(ref) not in flat:
                errs.append(unstated.format("reference number", ref,
                                            "Only list reference numbers that appear in the notes."))
        for key in ("production_year_start", "production_year_end"):
            year = getattr(w, key)
            if year is not None and not _stated(year, nums):
                errs.append(unstated.format(key, year, use_null))
        cal = caliber_numbers.get(w.caliber_id)
        if cal is not None and _alnum(cal) not in flat:
            errs.append(
                f"caliber_id = {w.caliber_id!r}, but its caliber number {cal!r} is not mentioned in "
                "the notes. Only link a watch to the movement the notes name; if they name none, "
                "leave the watch out and explain why in 'skipped'."
            )
        for i, t in enumerate(w.tests_passed):
            where = f"tests_passed[{i}]"
            if t.water_resistance_bar is not None and not _stated(
                    t.water_resistance_bar, nums, (1, 0.1)):  # bar/ATM, or metres
                errs.append(unstated.format(f"{where}.water_resistance_bar", t.water_resistance_bar, use_null))
            if t.water_resistance_meters is not None and not _stated(
                    t.water_resistance_meters, nums, (1, 10, 1 / 3.28084), rel_tol=0.03):  # m, bar, feet
                errs.append(unstated.format(f"{where}.water_resistance_meters", t.water_resistance_meters, use_null))
            if t.magnetic_resistance_gauss is not None and not _stated(
                    t.magnetic_resistance_gauss, nums, (1, 1 / 79.577), rel_tol=0.03):  # gauss, A/m
                errs.append(unstated.format(f"{where}.magnetic_resistance_gauss", t.magnetic_resistance_gauss, use_null))
            if t.rated_accuracy_sec_per_day is not None:
                for v in t.rated_accuracy_sec_per_day:
                    if v != 0 and not _stated(abs(v), nums):
                        errs.append(unstated.format(f"{where}.rated_accuracy_sec_per_day",
                                                    list(t.rated_accuracy_sec_per_day), use_null))
                        break
    return errs


# ------------------------------------------------------------- record checks
def _pydantic_errors(e: ValidationError) -> list[str]:
    return build_db._format_pydantic(e)


# Movements accepted in this run but not on disk (only during --dry-run).
_PENDING_CALIBERS: dict[str, str] = {}


def existing_caliber_numbers() -> dict[str, str]:
    out = dict(_PENDING_CALIBERS)
    for p in MOVEMENTS_DIR.glob("*.yaml"):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
            out[p.stem] = str(d.get("caliber_number", "")) if isinstance(d, dict) else ""
        except (OSError, yaml.YAMLError):
            pass
    return out


def check_reply(raw_json: str, notes: str) -> tuple[list[Record], list[Record], list[str], str | None]:
    """Validate the model's reply record by record.
    Returns (good, bad, skipped_by_model, reply_level_error)."""
    try:
        reply = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return [], [], [], f"Reply was not valid JSON: {e}"
    if not isinstance(reply, dict):
        return [], [], [], "Reply must be a JSON object with keys movements, watches, skipped."

    good, bad = [], []
    calibers = existing_caliber_numbers()

    for kind, key, model_cls in (("movement", "movements", MovementSpec),
                                 ("watch", "watches", WatchReference)):
        items = reply.get(key) or []
        if not isinstance(items, list):
            return [], [], [], f"'{key}' must be a list."
        for item in items:
            rec = Record(kind, item if isinstance(item, dict) else {"value": item})
            try:
                rec.model = model_cls.model_validate(rec.data)
            except ValidationError as e:
                rec.errors = _pydantic_errors(e)
                bad.append(rec)
                continue
            if kind == "movement":
                calibers.setdefault(rec.model.caliber_id, rec.model.caliber_number)
            (good if not rec.errors else bad).append(rec)

    # caliber_id links and "never guess" checks, once all movements are known
    for rec in list(good):
        if rec.kind == "watch" and rec.model.caliber_id not in calibers:
            rec.errors.append(
                f"caliber_id {rec.model.caliber_id!r} is neither an existing movement nor one in "
                "your reply. Use an existing id, return the movement too, or leave the watch out "
                "and explain why in 'skipped'."
            )
        rec.errors += grounding_errors(rec, notes, calibers)
        if rec.errors:
            good.remove(rec)
            bad.append(rec)

    # a watch whose new movement was rejected cannot be accepted either
    good_cal = {r.model.caliber_id for r in good if r.kind == "movement"}
    existing = set(existing_caliber_numbers())
    for rec in list(good):
        if rec.kind == "watch" and rec.model.caliber_id not in existing | good_cal:
            rec.errors.append(f"its movement {rec.model.caliber_id!r} was rejected.")
            good.remove(rec)
            bad.append(rec)

    skipped = [str(s) for s in (reply.get("skipped") or [])]
    return good, bad, skipped, None


# ------------------------------------------------------------------ the model
def _num_ctx(system_prompt: str, user_msg: str) -> int:
    est = (len(system_prompt) + len(user_msg)) // 3 + OUTPUT_RESERVE  # rough tokens
    return min(MAX_CTX, max(16384, -(-est // 4096) * 4096))


def extract(notes: str, source: str, model_name: str, retries: int, system_prompt: str,
            chat=None) -> NoteResult:
    """Ask the model, check the reply, feed problems back, keep the best results."""
    if chat is None:
        from ollama import chat  # imported here so --help works without ollama installed

    result = NoteResult(source)
    user_msg = build_user_message(notes)
    est_tokens = (len(system_prompt) + len(user_msg)) // 3 + OUTPUT_RESERVE
    if est_tokens > MAX_CTX:
        result.failure = (f"notes too long for one request (about {est_tokens} tokens incl. "
                          f"instructions; limit {MAX_CTX}). Split the file into smaller notes.")
        return result

    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}]
    accepted: dict[tuple, Record] = {}
    rejected: dict[tuple, Record] = {}

    for attempt in range(1, retries + 1):
        print(f"  asking {model_name} (attempt {attempt}/{retries}) ...", flush=True)
        try:
            response = chat(
                model=model_name,
                messages=messages,
                format=IngestionBundle.model_json_schema(),
                think=False,  # no Qwen3 reasoning monologue; JSON straight away
                options={"temperature": 0.1, "num_ctx": _num_ctx(system_prompt, user_msg)},
            )
        except Exception as e:  # connection refused, model not found, ...
            result.failure = f"Ollama request failed: {e}"
            return result

        raw = response.message.content or ""
        good, bad, skipped, reply_error = check_reply(raw, notes)
        if skipped:
            result.skipped_by_model = skipped

        for r in good:
            accepted[(r.kind, r.rec_id)] = r
            rejected.pop((r.kind, r.rec_id), None)
        for r in bad:
            if (r.kind, r.rec_id) not in accepted:
                rejected[(r.kind, r.rec_id)] = r

        if reply_error is None and not bad:
            break
        if attempt == retries:
            if reply_error and not accepted and not rejected:
                result.failure = reply_error
            break

        problems = [reply_error] if reply_error else []
        for r in bad:
            problems.append(f"{r.kind} {r.rec_id}:\n" + "\n".join(f"  - {e}" for e in r.errors))
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": (
            "Some records failed the checks:\n\n" + "\n\n".join(problems) +
            "\n\nReturn the complete corrected JSON object (all records, including the ones "
            "that were fine). Remember: never guess; use null or leave the record out and "
            "say why in 'skipped'.")})

    # an accepted watch may depend on a movement that ended up rejected
    good_cal = {r.rec_id for r in accepted.values() if r.kind == "movement"}
    existing = set(existing_caliber_numbers())
    for key, r in list(accepted.items()):
        if r.kind == "watch" and r.model.caliber_id not in existing | good_cal:
            r.errors.append(f"its movement {r.model.caliber_id!r} was rejected.")
            rejected[key] = accepted.pop(key)

    # movements first, so a watch's movement is written before the watch
    result.accepted = sorted(accepted.values(), key=lambda r: r.kind != "movement")
    result.rejected = list(rejected.values())
    return result


# ------------------------------------------------------------------- writing
def write_records(result: NoteResult, overwrite: bool, dry_run: bool) -> None:
    for r in result.accepted:
        rel = r.path.relative_to(ROOT_DIR)
        if r.path.exists() and not overwrite:
            result.kept_existing.append(str(rel))
            continue
        if dry_run:
            if r.kind == "movement":
                _PENDING_CALIBERS[r.rec_id] = r.model.caliber_number
        else:
            r.path.parent.mkdir(parents=True, exist_ok=True)
            # mode="json" turns enums into their text and tuples into lists
            r.path.write_text(
                yaml.safe_dump(r.model.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
                encoding="utf-8")
        result.written.append(str(rel))


def save_rejects(result: NoteResult, run_dir: Path) -> None:
    if not result.rejected:
        return
    rej_dir = run_dir / "rejected"
    rej_dir.mkdir(parents=True, exist_ok=True)
    stem = _alnum(Path(result.source).stem) or "notes"
    for r in result.rejected:
        header = [f"# From: {result.source}", f"# Would go in: data/{r.kind}s/{r.rec_id}.yaml",
                  "# Not written to data/ because:"] + [f"#   - {e}" for e in r.errors]
        body = yaml.safe_dump(r.data, sort_keys=False, allow_unicode=True)
        (rej_dir / f"{stem}__{_alnum(r.rec_id) or 'noid'}.yaml").write_text(
            "\n".join(header) + "\n\n" + body, encoding="utf-8")


def report_lines(results: list[NoteResult], dry_run: bool) -> list[str]:
    wrote = "would write" if dry_run else "wrote"
    lines = []
    for res in results:
        lines.append(f"== {res.source}")
        if res.failure:
            lines.append(f"   FAILED: {res.failure}")
        for p in res.written:
            lines.append(f"   {wrote}:   {p}")
        for p in res.kept_existing:
            lines.append(f"   exists:  {p} (kept; use --overwrite to replace)")
        for r in res.rejected:
            lines.append(f"   REJECTED {r.kind} {r.rec_id}:")
            lines += [f"       - {e}" for e in r.errors]
        for s in res.skipped_by_model:
            lines.append(f"   skipped by model: {s}")
        if not (res.failure or res.written or res.kept_existing or res.rejected or res.skipped_by_model):
            lines.append("   nothing found in these notes")
    n_written = sum(len(r.written) for r in results)
    n_rej = sum(len(r.rejected) for r in results)
    n_fail = sum(1 for r in results if r.failure)
    lines.append("")
    lines.append(f"Summary: {len(results)} note file(s); {n_written} record(s) {wrote}; "
                 f"{n_rej} rejected; {n_fail} note file(s) failed.")
    return lines


# ----------------------------------------------------------------- the CLI
def collect_note_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and p.suffix.lower() in NOTE_SUFFIXES
                  and not any(part.startswith(".") for part in p.relative_to(folder).parts))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notes", nargs="?", help="the notes themselves (or use --file, --dir or stdin)")
    ap.add_argument("-f", "--file", type=Path, action="append", default=[],
                    help="a note file (may be given several times)")
    ap.add_argument("-d", "--dir", type=Path, help="a folder of note files (.txt/.md, subfolders included)")
    ap.add_argument("-m", "--model", default="watch-agent", help="Ollama model (default: watch-agent)")
    ap.add_argument("--retries", type=int, default=3, help="attempts per note file (default 3)")
    ap.add_argument("--dry-run", action="store_true", help="check everything but write nothing to data/")
    ap.add_argument("--overwrite", action="store_true", help="replace files that already exist in data/")
    ap.add_argument("--overwrite-movement", action="store_true", help=argparse.SUPPRESS)  # old flags
    ap.add_argument("--overwrite-watch", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--build", action="store_true", help="rebuild horology.db and index.html afterwards")
    args = ap.parse_args(argv)
    overwrite = args.overwrite or args.overwrite_movement or args.overwrite_watch

    inputs: list[tuple[str, str]] = []  # (source label, text)
    if args.dir:
        if not args.dir.is_dir():
            ap.error(f"{args.dir} is not a folder")
        files = collect_note_files(args.dir)
        if not files:
            ap.error(f"no .txt or .md files found in {args.dir}")
        inputs += [(str(p), p.read_text(encoding="utf-8", errors="replace")) for p in files]
    for p in args.file:
        inputs.append((str(p), p.read_text(encoding="utf-8", errors="replace")))
    if args.notes:
        inputs.append(("(command line)", args.notes))
    if not inputs and not sys.stdin.isatty():
        inputs.append(("(stdin)", sys.stdin.read()))
    inputs = [(s, t) for s, t in inputs if t.strip()]
    if not inputs:
        ap.error("give notes as an argument, with --file or --dir, or pipe them in")

    system_prompt = build_system_prompt()
    run_dir = RUNS_DIR / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    results = []
    for i, (source, text) in enumerate(inputs, 1):
        print(f"[{i}/{len(inputs)}] {source}")
        res = extract(text, source, args.model, max(1, args.retries), system_prompt)
        write_records(res, overwrite, args.dry_run)  # later notes see these as existing
        results.append(res)
        print(f"  accepted {len(res.accepted)}, rejected {len(res.rejected)}"
              + (f", FAILED: {res.failure}" if res.failure else ""))

    lines = report_lines(results, args.dry_run)
    for r in results:
        save_rejects(r, run_dir)
    if len(inputs) > 1 or any(r.rejected or r.failure for r in results):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        lines.append(f"Report and rejected records: {run_dir.relative_to(ROOT_DIR)}/")
    print()
    print("\n".join(lines))

    if not args.dry_run and any(r.written for r in results):
        _, _, errors = build_db.load_all()
        if errors:
            print("\n[WARN] data/ does not pass `python3 src/build_db.py --check`:")
            for path, errs in errors.items():
                print(f"  {path.relative_to(ROOT_DIR)}: " + "; ".join(errs))
        else:
            print("All files in data/ pass the schema check.")
        if args.build:
            print("Rebuilding horology.db ...")
            build_db.main([])

    return 1 if any(r.rejected or r.failure for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
