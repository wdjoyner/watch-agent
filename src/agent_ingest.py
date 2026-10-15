# src/agent_ingest.py
import argparse
import sys
from pathlib import Path
import yaml
from ollama import chat
from pydantic import BaseModel, ValidationError, model_validator

from schema import MovementSpec, WatchReference
import build_db

ROOT_DIR = Path(__file__).resolve().parent.parent
MOVEMENTS_DIR = ROOT_DIR / "data" / "movements"
WATCHES_DIR = ROOT_DIR / "data" / "watches"


class IngestionBundle(BaseModel):
    """Combined payload so the LLM extracts both the movement and the watch together."""
    movement: MovementSpec
    watch: WatchReference

    @model_validator(mode="after")
    def ensure_foreign_key_matches(self) -> "IngestionBundle":
        if self.watch.caliber_id != self.movement.caliber_id:
            raise ValueError(
                f"watch.caliber_id ('{self.watch.caliber_id}') must exactly match "
                f"movement.caliber_id ('{self.movement.caliber_id}')."
            )
        return self


EXTRACTION_PROMPT = """
Extract the mechanical watch and movement specifications from the user's notes into the exact JSON schema provided.

Rules:
1. Both `caliber_id` and `watch_id` MUST be lowercase alphanumeric strings with underscores only (e.g., 'seiko_6r15', 'seiko_alpinist_sarb017').
2. Ensure `watch.caliber_id` is identical to `movement.caliber_id`.
3. If the movement is Manual, `winding_mechanism` MUST be "None (Manual)".
4. If the movement is Automatic, pick the closest matching `winding_mechanism` from the enum.
5. Never invent quartz frequencies; use standard mechanical vibrations per hour (e.g., 18000, 21600, 25200, 28800, 36000).
6. Convert ATM or meters to bar where applicable (10 ATM = 100m = 10.0 bar).
"""


def extract_with_retry(
    raw_text: str, model_name: str = "watch-agent", max_retries: int = 3
) -> IngestionBundle:
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": raw_text},
    ]

    for attempt in range(1, max_retries + 1):
        print(f"[INFO] Querying '{model_name}' (Attempt {attempt}/{max_retries})...")
        response = chat(
            model=model_name,
            messages=messages,
            format=IngestionBundle.model_json_schema(),
            think=False,  # Disables Qwen3 reasoning monologue for fast structured output
            options={"temperature": 0.1, "num_ctx": 16384},
        )

        raw_json = response.message.content
        try:
            bundle = IngestionBundle.model_validate_json(raw_json)
            print("[SUCCESS] Extracted data passed all Pydantic horological validations!")
            return bundle
        except ValidationError as err:
            print(f"[WARN] Validation failed on attempt {attempt}:\n{err}\n")
            if attempt == max_retries:
                raise RuntimeError(
                    f"Failed to extract valid schema after {max_retries} attempts."
                ) from err
            # Feed the exact Pydantic error back to the model so it self-corrects
            messages.append({"role": "assistant", "content": raw_json})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your output failed Pydantic validation with the following errors:\n{err}\n"
                        "Please fix these exact fields and return the corrected JSON."
                    ),
                }
            )

    raise RuntimeError("Unexpected exit from retry loop.")


def save_yaml_files(
    bundle: IngestionBundle, overwrite_movement: bool = False, overwrite_watch: bool = False
) -> None:
    MOVEMENTS_DIR.mkdir(parents=True, exist_ok=True)
    WATCHES_DIR.mkdir(parents=True, exist_ok=True)

    movement_path = MOVEMENTS_DIR / f"{bundle.movement.caliber_id}.yaml"
    watch_path = WATCHES_DIR / f"{bundle.watch.watch_id}.yaml"

    # Use mode="json" so Enums and Tuples serialize as clean YAML strings and lists
    movement_dict = bundle.movement.model_dump(mode="json")
    watch_dict = bundle.watch.model_dump(mode="json")

    if movement_path.exists() and not overwrite_movement:
        print(
            f"[SKIP] Movement '{movement_path.name}' already exists. "
            "Reusing existing movement file (pass --overwrite-movement to replace)."
        )
    else:
        with open(movement_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(movement_dict, f, sort_keys=False, allow_unicode=True)
        print(f"[SAVED] Wrote movement spec -> data/movements/{movement_path.name}")

    if watch_path.exists() and not overwrite_watch:
        print(
            f"[SKIP] Watch '{watch_path.name}' already exists "
            "(pass --overwrite-watch to replace)."
        )
    else:
        with open(watch_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(watch_dict, f, sort_keys=False, allow_unicode=True)
        print(f"[SAVED] Wrote watch reference -> data/watches/{watch_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest plain-text watch notes into validated YAML files using Ollama."
    )
    parser.add_argument(
        "notes",
        nargs="?",
        help="Plain text notes about the watch and movement (or pass via --file / stdin).",
    )
    parser.add_argument(
        "-f", "--file", type=Path, help="Path to a text file containing watch notes."
    )
    parser.add_argument(
        "-m",
        "--model",
        default="watch-agent",
        help="Ollama model name to use (default: watch-agent).",
    )
    parser.add_argument(
        "--overwrite-movement",
        action="store_true",
        help="Overwrite the movement YAML if it already exists.",
    )
    parser.add_argument(
        "--overwrite-watch",
        action="store_true",
        help="Overwrite the watch YAML if it already exists.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Automatically rebuild horology.db after saving YAML files.",
    )

    args = parser.parse_args()

    if args.file:
        raw_text = args.file.read_text(encoding="utf-8")
    elif args.notes:
        raw_text = args.notes
    elif not sys.stdin.isatty():
        raw_text = sys.stdin.read()
    else:
        parser.error("Provide watch notes as an argument, via --file, or piped via stdin.")
        return

    bundle = extract_with_retry(raw_text, model_name=args.model)
    save_yaml_files(
        bundle,
        overwrite_movement=args.overwrite_movement,
        overwrite_watch=args.overwrite_watch,
    )

    if args.build:
        print("[INFO] Rebuilding SQLite database...")
        build_db.main([])


if __name__ == "__main__":
    main()
