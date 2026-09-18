"""print_edition.py -- PDF goes to Latch from disk, never through the model."""
from __future__ import annotations

import base64
import json
import sys

import pytest

from conftest import ROOT, load_module

sys.path.insert(0, str(ROOT / "pt-shared" / "scripts"))
pe = load_module("print_edition", "pt-print/scripts/print_edition.py")


def _config(tmp_path, configured=True, name="HP_LaserJet"):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({
            "owner": {"timezone": "America/Sao_Paulo"},
            "delivery": {"hour": "07:00"},
            "printer": {"configured": configured, "name": name if configured else None},
        }),
        encoding="utf-8",
    )
    return path


def _edition(tmp_path, pdf=b"%PDF-1.4 fake"):
    (tmp_path / "edition.json").write_text(
        json.dumps({"date": "2026-09-17", "sections": []}),
        encoding="utf-8",
    )
    path = tmp_path / "edition.pdf"
    path.write_bytes(pdf)
    return path


class TestPrinterGate:
    def test_missing_config_is_a_skip_not_a_crash(self, tmp_path):
        assert pe.printer_name(str(tmp_path / "nope.json")) is None

    def test_unconfigured_printer_skips(self, tmp_path):
        assert pe.printer_name(str(_config(tmp_path, configured=False))) is None

    def test_configured_without_name_skips(self, tmp_path):
        assert pe.printer_name(str(_config(tmp_path, configured=True, name=""))) is None

    def test_configured_returns_exact_cups_name(self, tmp_path):
        assert pe.printer_name(str(_config(tmp_path, name="HP_LaserJet_4"))) == "HP_LaserJet_4"


class TestPdfAndDate:
    def test_missing_pdf_is_refused_by_name(self, tmp_path):
        (tmp_path / "edition.json").write_text(
            json.dumps({"date": "2026-09-17"}), encoding="utf-8"
        )
        with pytest.raises(SystemExit, match="pdf"):
            pe.read_pdf(str(tmp_path / "edition.pdf"))

    def test_date_comes_from_sibling_edition_json(self, tmp_path):
        pdf = _edition(tmp_path)
        assert pe.edition_date(str(pdf)) == "2026-09-17"

    def test_mac_path_is_pdf_under_plow_pt(self):
        assert pe.mac_pdf_path("2026-09-17") == "~/Plow/pt/edition-2026-09-17.pdf"
        assert pe.mac_b64_path("2026-09-17") == "~/Plow/pt/edition-2026-09-17.pdf.b64"


class TestSettleAndParse:
    def test_pending_is_polled_until_ready(self):
        calls = []

        def get_result(handle):
            calls.append(handle)
            if len(calls) < 2:
                return {"status": "pending", "handle": handle}
            return {"status": "ready", "result": {"path": "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64"}}

        out = pe.settle(
            {"status": "pending", "handle": "h1"},
            get_result,
            sleep=lambda _n: None,
        )
        assert out["path"] == "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64"
        assert calls == ["h1", "h1"]

    def test_denied_is_a_failed_print(self):
        with pytest.raises(SystemExit, match="denied"):
            pe.settle({"status": "denied", "handle": "h"}, lambda _h: {}, sleep=lambda _n: None)

    def test_written_path_from_result(self):
        assert pe.written_path(
            {"path": "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64"}
        ) == "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64"

    def test_lp_nonzero_is_a_failed_print(self):
        with pytest.raises(SystemExit, match="lp"):
            pe.require_lp_ok({"exit_code": 1, "output": "Unsupported document-format"})

    def test_lp_zero_passes(self):
        pe.require_lp_ok({"exit_code": 0, "output": "request id is HP-1"})


class TestShip:
    def test_writes_pdf_via_base64_then_lp_with_network_for_cups(self, tmp_path):
        # Measured live 2026-09-17: JornalVirtual rejected HTML
        # (`lp: Unsupported document-format "text/html"`). The chat leg
        # already has edition.pdf from weasyprint; paper must ship that.
        pdf = _edition(tmp_path, pdf=b"%PDF-1.4 PAGE")
        calls = []

        def call_tool(name, arguments):
            calls.append((name, arguments))
            if name == "plow_write_file":
                return {"path": "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64"}
            if name == "plow_run_command":
                if arguments["argv"][0] == "base64":
                    return {"exit_code": 0, "output": ""}
                return {"exit_code": 0, "output": "request id is HP-1"}
            raise AssertionError(name)

        pe.ship(
            str(pdf),
            "JornalVirtual",
            "2026-09-17",
            call_tool,
            sleep=lambda _n: None,
        )
        write_name, write_args = calls[0]
        assert write_name == "plow_write_file"
        assert write_args["path"] == "~/Plow/pt/edition-2026-09-17.pdf.b64"
        assert write_args["content"] == base64.b64encode(b"%PDF-1.4 PAGE").decode("ascii")
        decode_name, decode_args = calls[1]
        assert decode_name == "plow_run_command"
        assert decode_args["argv"] == [
            "base64", "-D", "-i",
            "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64",
            "-o", "/Users/jj/Plow/pt/edition-2026-09-17.pdf",
        ]
        lp_name, lp_args = calls[2]
        assert lp_name == "plow_run_command"
        assert lp_args["argv"] == [
            "lp", "-d", "JornalVirtual",
            "/Users/jj/Plow/pt/edition-2026-09-17.pdf",
        ]
        assert lp_args["network"] is True

    def test_lp_bad_file_descriptor_retries_via_applescript(self, tmp_path):
        pdf = _edition(tmp_path)
        tools = []

        def call_tool(name, arguments):
            tools.append(name)
            if name == "plow_write_file":
                return {"path": "/Users/jj/Plow/pt/edition-2026-09-17.pdf.b64"}
            if name == "plow_run_command":
                if arguments["argv"][0] == "base64":
                    return {"exit_code": 0, "output": ""}
                return {"exit_code": 1, "output": "lp: Bad file descriptor"}
            if name == "plow_run_applescript":
                return {"exit_code": 0, "output": "request id is HP-1"}
            raise AssertionError(name)

        pe.ship(
            str(pdf),
            "JornalVirtual",
            "2026-09-17",
            call_tool,
            sleep=lambda _n: None,
        )
        assert tools == [
            "plow_write_file",
            "plow_run_command",
            "plow_run_command",
            "plow_run_applescript",
        ]
