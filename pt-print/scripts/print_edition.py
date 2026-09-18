#!/usr/bin/env python3
"""print_edition.py -- the paper edition's Latch leg, from disk, not the model.

Measured live 2026-09-17: pt-print told the model to `cat` edition.html and
paste that ~43k page into plow_write_file's `content`. The LLM stream died
mid tool-call (RemoteProtocolError: incomplete chunked read); `lp` never
ran. The chat PDF still arrived because post_to_chat.py reads the file
itself. This script is that same shape for paper.

A later run that DID reach `lp` failed because the CUPS queue refused HTML
(`Unsupported document-format "text/html"` on JornalVirtual). The file
shipped is edition.pdf, the one the chat already got. Latch write_file is
text, so the PDF rides as base64 and is decoded on the Mac before `lp`.

Usage:

    print_edition.py <edition.pdf> <config.json>

Date comes from sibling edition.json. Skips with exit 0 when
printer.configured is not true. Any real Latch or `lp` failure exits
non-zero with `page not printed` in the message.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent / "pt-shared" / "scripts"))
from bearer_http import NoRedirect, require  # noqa: E402

MCP_TIMEOUT = 60
POLL_SECONDS = 120
PATH_RE = re.compile(
    r"(/Users/[^\s'\"]+/Plow/pt/edition-[0-9-]+\.(?:html|pdf)(?:\.b64)?)"
)


def printer_name(config_path):
    """CUPS name when printer.configured is exactly true; else None (skip)."""
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(cfg, dict):
        return None
    printer = cfg.get("printer") or {}
    if not isinstance(printer, dict) or printer.get("configured") is not True:
        return None
    name = printer.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def read_pdf(path):
    try:
        data = Path(path).read_bytes()
    except OSError:
        sys.exit(f"error: pdf path cannot be read: {path}")
    if not data:
        sys.exit(f"error: pdf is empty: {path}")
    return data


def edition_date(pdf_path):
    sibling = Path(pdf_path).resolve().parent / "edition.json"
    try:
        data = json.loads(sibling.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        sys.exit(f"error: sibling edition.json has no date: {sibling}")
    date = data.get("date") if isinstance(data, dict) else None
    if not isinstance(date, str) or not date.strip():
        sys.exit(f"error: sibling edition.json has no date: {sibling}")
    return date.strip()


def mac_pdf_path(date):
    return f"~/Plow/pt/edition-{date}.pdf"


def mac_b64_path(date):
    return f"~/Plow/pt/edition-{date}.pdf.b64"


def pdf_path_from_b64(b64_path):
    if b64_path.endswith(".b64"):
        return b64_path[:-4]
    return b64_path


def decode_mcp_body(content_type, raw):
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    ctype = content_type or ""
    if "text/event-stream" in ctype:
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            obj = json.loads(chunk)
            if "result" in obj or "error" in obj:
                return obj
        sys.exit("error: page not printed — empty latch stream")
    if not text.strip():
        return {}
    return json.loads(text)


def unwrap_tool_result(result):
    if not isinstance(result, dict):
        return {"raw": result}
    texts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text") or "")
    blob = "\n".join(texts).strip()
    if result.get("isError"):
        sys.exit(f"error: page not printed — {blob or result}")
    if blob:
        try:
            return json.loads(blob)
        except ValueError:
            return {"raw": blob}
    return result


def settle(parsed, get_result, sleep=time.sleep, max_wait=POLL_SECONDS):
    if not isinstance(parsed, dict):
        return parsed
    for _ in range(max_wait + 1):
        status = parsed.get("status")
        if status == "pending":
            handle = parsed.get("handle")
            if not handle:
                sys.exit("error: page not printed — latch pending with no handle")
            sleep(1)
            parsed = get_result(handle)
            continue
        if status in ("denied", "failed", "expired", "unknown", "blocked"):
            sys.exit(f"error: page not printed — latch {status}")
        if status == "ready":
            inner = parsed.get("result", parsed)
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except ValueError:
                    inner = {"raw": inner}
            return inner
        return parsed
    sys.exit("error: page not printed — latch timed out")


def written_path(parsed):
    candidates = []
    if isinstance(parsed, dict):
        for key in ("path", "absolute_path", "file", "wrote"):
            if parsed.get(key):
                candidates.append(parsed[key])
        if parsed.get("raw"):
            candidates.append(parsed["raw"])
    else:
        candidates.append(parsed)
    blob = " ".join(str(c) for c in candidates)
    match = PATH_RE.search(blob)
    if match:
        return match.group(1)
    if candidates:
        first = str(candidates[0])
        if first.startswith("/"):
            return first
    sys.exit("error: page not printed — write did not return a Mac path")


def is_bfd(parsed):
    blob = json.dumps(parsed) if not isinstance(parsed, str) else parsed
    return "bad file descriptor" in blob.lower()


def require_lp_ok(parsed):
    if isinstance(parsed, dict) and "exit_code" in parsed:
        if parsed["exit_code"] not in (0, "0"):
            sys.exit(
                f"error: page not printed — lp {parsed['exit_code']}: "
                f"{parsed.get('output', parsed)}"
            )
        return
    output = ""
    if isinstance(parsed, dict):
        output = str(parsed.get("output") or parsed.get("raw") or "")
    else:
        output = str(parsed)
    lowered = output.lower()
    if "bad file descriptor" in lowered or lowered.startswith("lp:"):
        sys.exit(f"error: page not printed — lp {output}")


def ship(pdf_path, printer, date, call_tool, sleep=time.sleep):
    pdf = read_pdf(pdf_path)
    dest_b64 = mac_b64_path(date)

    def poll(handle):
        return call_tool("plow_get_result", {"handle": handle})

    wrote = settle(
        call_tool(
            "plow_write_file",
            {"path": dest_b64, "content": base64.b64encode(pdf).decode("ascii")},
        ),
        poll,
        sleep=sleep,
    )
    abs_b64 = written_path(wrote)
    abs_pdf = pdf_path_from_b64(abs_b64)
    decoded = settle(
        call_tool(
            "plow_run_command",
            {
                "argv": ["base64", "-D", "-i", abs_b64, "-o", abs_pdf],
                "read_paths": [abs_b64],
                "write_paths": [abs_pdf],
                "goal": "Decode the edition PDF on the owner's Mac",
            },
        ),
        poll,
        sleep=sleep,
    )
    if isinstance(decoded, dict) and decoded.get("exit_code") not in (0, "0", None):
        sys.exit(
            f"error: page not printed — base64 {decoded.get('exit_code')}: "
            f"{decoded.get('output', decoded)}"
        )
    lp = settle(
        call_tool(
            "plow_run_command",
            {
                "argv": ["lp", "-d", printer, abs_pdf],
                "network": True,
                "read_paths": [abs_pdf],
                "goal": "Print today's Plow Times edition",
            },
        ),
        poll,
        sleep=sleep,
    )
    if is_bfd(lp):
        cmd = f"lp -d {shlex.quote(printer)} {shlex.quote(abs_pdf)}"
        lp = settle(
            call_tool(
                "plow_run_applescript",
                {
                    "app": "System Events",
                    "script": f"do shell script {json.dumps(cmd)}",
                    "goal": "Print today's Plow Times edition (sandboxed lp failed)",
                },
            ),
            poll,
            sleep=sleep,
        )
    require_lp_ok(lp)


class LatchClient:
    """One Streamable-HTTP MCP session against the owner's Latch device."""

    def __init__(self, base, device, token):
        self.url = f"{base.rstrip('/')}/v1/relay/devices/{device}/mcp"
        self.token = token
        self.session_id = None
        self._id = 0
        self._initialize()

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _post(self, payload):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url, method="POST", data=data, headers=self._headers(),
        )
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(request, timeout=MCP_TIMEOUT) as response:
                sid = response.headers.get("Mcp-Session-Id") or response.headers.get(
                    "mcp-session-id"
                )
                if sid:
                    self.session_id = sid
                raw = response.read()
                ctype = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            sys.exit(f"error: page not printed — latch HTTP {exc.code} {exc.reason}")
        except urllib.error.URLError as exc:
            sys.exit(
                "error: Mac unreachable, page not printed; next scheduled run retries"
            )
        return decode_mcp_body(ctype, raw)

    def _initialize(self):
        self._id += 1
        self._post(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "the-plow-times-print", "version": "1"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name, arguments):
        self._id += 1
        msg = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if "error" in msg:
            err = msg["error"]
            detail = err.get("message", err) if isinstance(err, dict) else err
            sys.exit(f"error: page not printed — latch {detail}")
        return unwrap_tool_result(msg.get("result") or {})


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the edition PDF to the owner's Mac and print it."
    )
    parser.add_argument("pdf")
    parser.add_argument("config")
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    printer = printer_name(args.config)
    if not printer:
        print("skipped: printer.configured is not true")
        return
    date = args.date or edition_date(args.pdf)
    if args.dry_run:
        print(f"dry-run: would write {mac_pdf_path(date)} and lp -d {printer}")
        return

    base = os.environ.get("PLOW_API_BASE", "https://api.plow.co").strip() or "https://api.plow.co"
    device = require("DOMO_DEVICE_UID")
    token = require("DOMO_MCP_TOKEN")
    client = LatchClient(base, device, token)
    ship(args.pdf, printer, date, client.call_tool)
    print(f"page printed on {printer}")


if __name__ == "__main__":
    main()
