"""post_to_chat.py -- PDF-only payload vs text fallback."""
from __future__ import annotations

import json
import sys

import pytest

from conftest import ROOT, load_module

sys.path.insert(0, str(ROOT / "pt-shared" / "scripts"))
post = load_module("post_to_chat", "pt-shared/scripts/post_to_chat.py")


class TestComposePayload:
    def test_pdf_is_attachment_with_empty_body(self):
        payload = post.compose_payload("ignored transcript", "att_1")
        assert payload == {"body": "", "attachment_uids": ["att_1"]}

    def test_attachment_filename_defaults_to_basename(self):
        assert post.attachment_filename("/var/lib/hermes/pt/run/edition.pdf") == (
            "edition.pdf"
        )

    def test_attachment_filename_override_is_a_paper_name_not_a_path(self):
        # Measured live: the chat showed the attachment as "edition.pdf"
        # because declare used the run-dir basename. The owner asked for
        # the newspaper, not a working-file name.
        assert (
            post.attachment_filename(
                "/var/lib/hermes/pt/run/edition.pdf",
                "The-Plow-Times-2026-09-17.pdf",
            )
            == "The-Plow-Times-2026-09-17.pdf"
        )
        with pytest.raises(SystemExit, match="filename"):
            post.attachment_filename("edition.pdf", "../secret.pdf")

    def test_text_only_when_no_pdf(self):
        payload = post.compose_payload("THE PLOW TIMES")
        assert payload == {"body": "THE PLOW TIMES"}

    def test_text_only_refuses_blank_stdin(self):
        with pytest.raises(SystemExit, match="no edition text"):
            post.compose_payload("")

    def test_successful_post_stamps_a_session_seal(self, tmp_path):
        stamp = tmp_path / "seal-session.json"
        post.after_posted(stamp)
        assert json.loads(stamp.read_text(encoding="utf-8"))["pending"] is True
        assert json.loads(stamp.read_text(encoding="utf-8"))["delivered"] is True

    def test_after_posted_reopens_delivered_sections(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PT_HOME", str(tmp_path / "pt"))
        intake = load_module("topics_reopen", "pt-intake/scripts/topics.py")
        intake.main(["add", "--text", "AI", "--kind", "section", "--depth", "quick"])
        tid = json.loads((tmp_path / "pt" / "topics.json").read_text())["topics"][0]["id"]
        intake.main(["mark", tid, "--status", "running"])
        intake.main(["mark", tid, "--status", "delivered"])
        post.after_posted(tmp_path / "seal.json")
        status = json.loads((tmp_path / "pt" / "topics.json").read_text())["topics"][0]["status"]
        assert status == "pending"


class TestTextFileFlag:
    """`--text-file` exists so the text leg needs no shell redirect.

    Measured live: told to "pass the chat text on stdin" with no command
    shown, a run built `/bin/sh -c '... post_to_chat.py < .../edition.chat.txt'`
    -- a shell operator, which is exactly what SOUL.md's gate flags. The owner
    got an /approve prompt instead of their newspaper.
    """

    def test_reads_the_edition_text_from_a_file(self, tmp_path):
        f = tmp_path / "edition.chat.txt"
        f.write_text("THE PLOW TIMES\nfront page\n", encoding="utf-8")
        assert post.read_text_file(str(f)) == "THE PLOW TIMES\nfront page"

    def test_missing_file_is_refused_by_name(self, tmp_path):
        with pytest.raises(SystemExit, match="text-file"):
            post.read_text_file(str(tmp_path / "nope.txt"))

    def test_blank_file_is_refused(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("   \n", encoding="utf-8")
        with pytest.raises(SystemExit, match="empty"):
            post.read_text_file(str(f))


class TestMaybePrint:
    """Measured live 2026-09-18: PDF posted, edition.html existed,
    printer.configured true (JornalVirtual), and print_edition.py was
    never invoked — the model marked topics and NO_REPLY'd. Chat is
    not a gate for paper; post_to_chat.py is.
    """

    def test_configured_printer_prints_the_pdf_with_no_html_beside_it(self, tmp_path):
        # Measured live 2026-09-18: runs that rendered only the PDF logged
        # "skipped: no html" -- a gate on a file the print never reads.
        pdf = tmp_path / "edition.pdf"
        pdf.write_bytes(b"%PDF")
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps({"printer": {"configured": True, "name": "JornalVirtual"}}),
            encoding="utf-8",
        )
        seen = []

        def runner(pdf_path, config_path):
            seen.append((pdf_path, config_path))
            return "page printed on JornalVirtual"

        out = post.maybe_print(str(pdf), str(cfg), runner=runner)
        assert seen == [(str(pdf.resolve()), str(cfg))]
        assert "page printed" in out

    def test_a_print_failure_does_not_undo_the_chat_post(self, tmp_path):
        pdf = tmp_path / "edition.pdf"
        pdf.write_bytes(b"%PDF")
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps({"printer": {"configured": True, "name": "JornalVirtual"}}),
            encoding="utf-8",
        )

        def runner(pdf_path, config_path):
            raise SystemExit("error: page not printed — lp 1")

        out = post.maybe_print(str(pdf), str(cfg), runner=runner)
        assert "page not printed" in out
