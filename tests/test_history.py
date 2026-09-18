import json

import pytest

from conftest import load_module

hist = load_module("history", "pt-priority/scripts/history.py")

DESK = {"headline": "Book 3 customer calls by Friday", "stage_label": "Discovery"}


@pytest.fixture(autouse=True)
def pt_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PT_HOME", str(tmp_path))
    return tmp_path


def test_record_upserts_one_entry_per_day_and_prunes_old_ones():
    hist.record("2026-08-01", DESK)
    hist.record("2026-09-16", {"headline": "A"})
    hist.record("2026-09-16", DESK)
    assert hist.load() == [{"date": "2026-09-16", "desk": DESK}]


@pytest.mark.parametrize("content", [
    "{broken", '{"a": 1}', '[{"date": "2026-09-15"}]',
    '[{"date": "2026-09-15", "priority": "old shape", "status": "open"}]',
])
def test_unreadable_history_is_set_aside(pt_home, content):
    (pt_home / "history.json").write_text(content)
    assert hist.load() == []
    assert (pt_home / "history.json.corrupt").read_text() == content
    hist.record("2026-09-16", DESK)
    assert hist.load() == [{"date": "2026-09-16", "desk": DESK}]


def test_cli_records_the_printed_desk(tmp_path, capsys):
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"desk": "priority", "status": "ok", "priority": DESK}))
    hist.main(["record", "--date", "2026-09-16", "--notes-json", str(notes)])
    assert capsys.readouterr().out.strip() == "RECORDED"
    assert hist.load() == [{"date": "2026-09-16", "desk": DESK}]
