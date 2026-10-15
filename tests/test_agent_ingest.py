# tests/test_agent_ingest.py
"""Tests for src/agent_ingest.py that need no Ollama: the model is replaced by
a fake that returns scripted replies. Run with:  python3 -m pytest -q"""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import agent_ingest  # noqa: E402
import agent_prompt  # noqa: E402
import build_db  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A copy of data/ in a temporary folder, with all modules pointed at it."""
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    mov, wat = data / "movements", data / "watches"
    for mod in (agent_ingest, agent_prompt, build_db):
        monkeypatch.setattr(mod, "MOVEMENTS_DIR", mov)
        monkeypatch.setattr(mod, "WATCHES_DIR", wat)
    monkeypatch.setattr(agent_ingest, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(agent_ingest, "RUNS_DIR", tmp_path / "ingest_runs")
    monkeypatch.setattr(build_db, "ROOT_DIR", tmp_path)
    agent_ingest._PENDING_CALIBERS.clear()
    return tmp_path


def fake_chat(*replies):
    """A stand-in for ollama.chat returning the given replies in turn."""
    calls = []

    def chat(model, messages, **kw):
        calls.append([dict(m) for m in messages])
        reply = replies[min(len(calls), len(replies)) - 1]
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(message=SimpleNamespace(content=text))

    chat.calls = calls
    return chat


def movement(**kw):
    rec = {
        "caliber_id": "bulova_11af", "manufacturer": "Bulova", "caliber_number": "11AF",
        "base_caliber": None, "winding_type": "Manual", "winding_mechanism": "None (Manual)",
        "escapement_type": "Swiss Lever", "frequency_vph": 18000, "jewels": 15,
        "power_reserve_hours": None, "hacking": None, "hand_winding": True,
        "description": "Bulova manual-wind movement from the notes.",
    }
    rec.update(kw)
    return rec


def watch(**kw):
    rec = {
        "watch_id": "bulova_example_watch", "brand": "Bulova", "model_family": "Example",
        "model_name": "Example Watch", "reference_numbers": [], "caliber_id": "bulova_11af",
        "production_year_start": None, "production_year_end": None, "tests_passed": [],
        "notes": None,
    }
    rec.update(kw)
    return rec


NOTES = "Bulova 11AF, manual wind, 15 jewels, 18,000 vph. Used in the Example Watch from 1951."


def run(notes, chat, retries=3):
    return agent_ingest.extract(notes, "notes.txt", "fake", retries, "SYSTEM", chat=chat)


def test_prompt_contains_format_and_real_examples():
    prompt = agent_prompt.build_system_prompt()
    assert "Bidirectional (Seiko Magic Lever)" in prompt  # from YAML_FORMAT.md
    assert '"caliber_id": "omega_861"' in prompt  # a real record as a worked example
    assert "NEVER GUESS" in prompt
    assert "omega_354" in agent_prompt.build_user_message("x")  # existing ids listed


def test_movement_only(repo):
    res = run(NOTES, fake_chat({"movements": [movement()], "watches": [], "skipped": []}))
    assert [r.rec_id for r in res.accepted] == ["bulova_11af"] and not res.rejected
    agent_ingest.write_records(res, overwrite=False, dry_run=False)
    saved = yaml.safe_load((repo / "data/movements/bulova_11af.yaml").read_text())
    assert saved["caliber_number"] == "11AF" and saved["power_reserve_hours"] is None


def test_watch_only_with_existing_movement(repo):
    notes = "Omega Seamaster bumper automatic, cal. 354, made 1950."
    w = watch(watch_id="omega_seamaster_test", brand="Omega", model_family="Seamaster",
              model_name="Bumper", caliber_id="omega_354", production_year_start=1950)
    res = run(notes, fake_chat({"movements": [], "watches": [w], "skipped": []}))
    assert [r.rec_id for r in res.accepted] == ["omega_seamaster_test"]


def test_guessed_value_is_sent_back_and_corrected(repo):
    chat = fake_chat(
        {"movements": [movement(jewels=17)], "watches": [], "skipped": []},  # 17 not in notes
        {"movements": [movement(jewels=None)], "watches": [], "skipped": []},
    )
    res = run(NOTES, chat)
    assert len(chat.calls) == 2
    assert "jewels = 17 is not stated in the notes" in chat.calls[1][-1]["content"]
    assert res.accepted[0].model.jewels is None and not res.rejected


def test_hz_conversion_counts_as_stated(repo):
    notes = "Bulova 11AF manual wind movement beating at 2.5 Hz."
    res = run(notes, fake_chat({"movements": [movement(jewels=None)], "watches": [], "skipped": []}))
    assert res.accepted and not res.rejected


def test_persistent_failure_is_rejected_but_good_records_kept(repo):
    bad_watch = watch(reference_numbers=["9999"])  # never stated
    reply = {"movements": [movement()], "watches": [bad_watch], "skipped": []}
    res = run(NOTES, fake_chat(reply), retries=2)
    assert [r.rec_id for r in res.accepted] == ["bulova_11af"]
    assert [r.rec_id for r in res.rejected] == ["bulova_example_watch"]
    assert "9999" in res.rejected[0].errors[0]


def test_schema_error_and_unknown_movement(repo):
    reply = {"movements": [movement(winding_mechanism="Peripheral Rotor")],  # manual + rotor
             "watches": [watch()], "skipped": []}
    res = run(NOTES, fake_chat(reply), retries=1)
    assert not res.accepted
    errors = {r.rec_id: " ".join(r.errors) for r in res.rejected}
    assert "Manual movements must have" in errors["bulova_11af"]
    assert "neither an existing movement" in errors["bulova_example_watch"]


def test_watch_linked_to_unmentioned_movement_is_rejected(repo):
    notes = "Bulova Example Watch, ref 1234; my notes don't say which movement."
    w = watch(caliber_id="omega_354", reference_numbers=["1234"])
    res = run(notes, fake_chat({"movements": [], "watches": [w], "skipped": []}), retries=1)
    assert not res.accepted and "not mentioned in the notes" in res.rejected[0].errors[0]


def test_skipped_and_bad_json(repo):
    res = run(NOTES, fake_chat("not json", {"movements": [], "watches": [], "skipped": ["no data"]}))
    assert res.skipped_by_model == ["no data"] and res.failure is None
    res = run(NOTES, fake_chat("not json"), retries=1)
    assert res.failure.startswith("Reply was not valid JSON")


def test_existing_file_not_overwritten(repo):
    path = repo / "data/movements/bulova_11af.yaml"
    path.write_text("original")
    res = run(NOTES, fake_chat({"movements": [movement()], "watches": [], "skipped": []}))
    agent_ingest.write_records(res, overwrite=False, dry_run=False)
    assert path.read_text() == "original" and res.kept_existing


def test_folder_run_writes_only_valid_records(repo, monkeypatch, capsys):
    notes_dir = repo / "bulova_notes"
    notes_dir.mkdir()
    (notes_dir / "a_movement.txt").write_text(NOTES)
    (notes_dir / "b_watch.md").write_text("Bulova Example Watch with the 11AF, from 1951.")
    (notes_dir / "c_bad.txt").write_text("Bulova 11AF watch, ref 42.")
    (notes_dir / ".hidden.txt").write_text("ignored")

    def chat(model, messages, **kw):
        notes = messages[1]["content"]
        if "18,000 vph" in notes:
            reply = {"movements": [movement()], "watches": [], "skipped": []}
        elif "from 1951" in notes:
            reply = {"movements": [], "watches": [watch(production_year_start=1951)], "skipped": []}
        else:
            reply = {"movements": [], "watches": [watch(watch_id="bulova_bad", reference_numbers=["43"])],
                     "skipped": []}
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))

    monkeypatch.setattr("ollama.chat", chat)
    code = agent_ingest.main(["--dir", str(notes_dir), "--retries", "1"])
    out = capsys.readouterr().out
    assert code == 1  # one record rejected
    assert (repo / "data/movements/bulova_11af.yaml").exists()
    assert (repo / "data/watches/bulova_example_watch.yaml").exists()
    assert not (repo / "data/watches/bulova_bad.yaml").exists()
    assert "REJECTED watch bulova_bad" in out and "All files in data/ pass" in out
    run_dir = next((repo / "ingest_runs").iterdir())
    assert "bulova_bad" in (run_dir / "report.txt").read_text()
    assert any(run_dir.glob("rejected/*bulovabad.yaml"))
    _, _, errors = build_db.load_all()
    assert not errors


def test_dry_run_writes_nothing(repo, monkeypatch, capsys):
    monkeypatch.setattr("ollama.chat", fake_chat({"movements": [movement()], "watches": [], "skipped": []}))
    assert agent_ingest.main(["--dry-run", NOTES]) == 0
    assert not (repo / "data/movements/bulova_11af.yaml").exists()
    assert "would write" in capsys.readouterr().out
