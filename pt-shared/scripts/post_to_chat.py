#!/usr/bin/env python3
"""post_to_chat.py -- the edition's chat leg: POST the PDF (or, if none, the
chat text) to the owner's home channel over the Plow Chat API, directly,
with no dependency on a connected live platform adapter.

Originally the fallback for a run with no --deliver arm. Promoted to the
PRIMARY chat leg (not a fallback) after measuring cron/scheduler.py's own
delivery live: the same unchanged content, run to run, both delivered fine
via --deliver and was silently discarded with "Fire claim ownership lost;
stale result was discarded" -- a genuine intermittent race in Hermes' own
cron heartbeat/claim mechanism, not anything about this script's content.
Calling the Plow Chat REST API directly, the same three calls
plow-chat-platform's own adapter makes internally (declare an attachment,
PUT the bytes to its signed upload_url, POST the message with
attachment_uids), needs no live adapter and is not subject to that race --
it is a plain HTTP call that either succeeds or exits loudly, same as the
text-only POST below always was.

The text is read on STDIN only -- never argv -- and only when there is no
PDF. With ``--pdf`` the message is the attachment alone (empty body), the
same envelope plow-chat-platform uses for photo-only sends. An edition is
the newspaper file; piping the chat transcript in as a caption is how the
owner got the PDF *and* a wall of text. Omit ``--pdf`` to post text only
(the fallback when weasyprint could not write the file).

The endpoint and credential come
from the process environment alone (PLOW_API_BASE, PLOW_HOME_CHANNEL,
PLOW_AGENT_TOKEN), which first boot publishes from the credential the host
dropped in: a file the agent can write is not a place to look for the API
base its own bearer is sent to. Any of the three unset or blank is refused
BY NAME, before anything posts, so a half-delivered run cannot happen.

`--pdf PATH` attaches that file (declare -> upload -> message-with-
attachment_uids) and sends no caption. After a successful `--pdf` POST it
stamps the session seal and runs print_edition.py when the printer is
configured (best-effort; a print failure does not undo the chat).
`--dry-run` prints the redacted envelope and never sends.
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path

from bearer_http import post_json, post_json_read, put_bytes, require


CONFIG_DEFAULT = "/var/lib/hermes/pt/config.json"
PRINT_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "pt-print"
    / "scripts"
    / "print_edition.py"
)


def resolve_chat():
    """The chat endpoint (base + path) + bearer, validated before anything posts."""
    base = require("PLOW_API_BASE").rstrip("/")
    uid = require("PLOW_HOME_CHANNEL")
    token = require("PLOW_AGENT_TOKEN")
    return base, uid, token


def read_message():
    return sys.stdin.read().strip()


def read_text_file(path):
    """The edition text from a file, so the text leg needs no shell redirect.

    Measured live: told to "pass the chat text on stdin" with no command
    shown, a run built `/bin/sh -c '... post_to_chat.py < edition.chat.txt'`.
    A shell operator is exactly what SOUL.md's gate flags, so the owner got
    an /approve prompt instead of their newspaper. A flag needs no shell.
    """
    try:
        text = open(path, encoding="utf-8").read().strip()
    except OSError:
        sys.exit(f"error: --text-file path cannot be read: {path}")
    if not text:
        sys.exit(f"error: --text-file is empty: {path}")
    return text


def attachment_filename(pdf_path, override=None):
    """The name Plow Chat shows on the attachment.

    Measured live: declare used os.path.basename of the run-dir file, so
    the owner saw "edition.pdf" in the thread. An override is a single
    basename (no slash), and always ends in .pdf.
    """
    name = override if override else os.path.basename(pdf_path)
    name = name.strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        sys.exit("error: --filename must be a basename, not a path")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def after_posted(stamp=None):
    """The PDF is out; the next owner message must not re-read this turn.

    A dry-run never calls this. Marks the stamp delivered so the gateway
    swallows any recap the model types, then on agent:end rotates the
    plow_chat session.
    """
    import seal_chat_session

    path = stamp or seal_chat_session.STAMP_DEFAULT
    prev = seal_chat_session.peek(path) or {}
    seal_chat_session.request(
        path,
        session_key=prev.get("session_key") or "",
        platform=prev.get("platform") or "",
        delivered=True,
    )
    reopen_sections_after_paper()


def reopen_sections_after_paper():
    """Sections must be pending for the next paper. The model often marks
    delivered and stops; the next on-demand copy then ships desks only.
    """
    intake = Path("/var/lib/hermes/skills/pt-intake/scripts/topics.py")
    if not intake.is_file():
        intake = Path(__file__).resolve().parent.parent.parent / "pt-intake" / "scripts" / "topics.py"
    if not intake.is_file():
        return "REOPEN:skipped"
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(intake), "reopen-sections"],
        capture_output=True,
        text=True,
    )
    blob = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return f"REOPEN:failed {blob or proc.returncode}"
    return blob or "REOPEN:none"


def run_print_edition(pdf_path, config_path):
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(PRINT_SCRIPT), pdf_path, config_path],
        capture_output=True,
        text=True,
    )
    blob = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        if "page not printed" in blob:
            return blob
        return f"page not printed — {blob or proc.returncode}"
    return blob


def maybe_print(pdf_path, config_path=None, runner=None):
    """Ship the page after the chat PDF. Best-effort: never undoes the POST.

    Measured live 2026-09-18: the model posted the PDF, had edition.html
    and printer.configured true, and never ran print_edition.py. Later the
    same day this gated on a sibling edition.html the print never reads;
    runs that rendered only the PDF logged "skipped: no html" and printed
    nothing. The PDF just posted is the page.
    """
    config_path = config_path or CONFIG_DEFAULT
    if not pdf_path:
        return "skipped: no pdf"
    run = runner or run_print_edition
    try:
        out = run(str(Path(pdf_path).resolve()), config_path)
    except SystemExit as exc:
        out = str(exc) if exc.args else "page not printed"
    except Exception as exc:
        out = f"page not printed — {exc}"
    text = (out or "").strip()
    return text or "page not printed — empty print result"


def compose_payload(text, attachment_uid=None):
    """One chat message: PDF-only when attached, otherwise the chat edition.

    plow-chat-platform posts ``{"body": "", "attachment_uids": [...]}`` for
    attachment-only sends; an empty body with a PDF is the newspaper, not a
    missing caption.
    """
    if attachment_uid:
        return {"body": "", "attachment_uids": [attachment_uid]}
    if not text:
        sys.exit("error: no edition text on stdin")
    return {"body": text}


def declare_and_upload(base, uid, token, pdf_path, filename=None):
    """Declare the attachment, PUT its bytes to the signed upload_url, return its uid.

    Mirrors plow-chat-platform's own ``_send_attachment`` exactly (same three
    calls, same field names) -- this is not a new contract, just this
    script's own copy of the one Plow's REST API defines.
    """
    if not os.path.isfile(pdf_path):
        sys.exit(f"error: --pdf path does not exist: {pdf_path}")
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    filename = attachment_filename(pdf_path, filename)
    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    declared = post_json_read(
        base, f"/v1/chats/{uid}/attachments", token, "Plow Chat attachment declare",
        {"filename": filename, "content_type": content_type, "size_bytes": len(data)},
    )
    put_bytes(declared["upload_url"], declared.get("upload_headers") or {}, data,
              "Plow Chat attachment")
    return declared["uid"]


def main():
    parser = argparse.ArgumentParser(description="Post an edition to the owner's Plow Chat.")
    parser.add_argument(
        "--pdf", default=None,
        help="path to a PDF to attach (declare -> upload -> attach, same call the "
             "platform's own adapter makes); omit to post text only",
    )
    parser.add_argument(
        "--text-file", default=None,
        help="read the chat edition from this file instead of stdin (no shell "
             "redirect needed); refused together with --pdf, which posts an "
             "empty body",
    )
    parser.add_argument(
        "--filename", default=None,
        help="attachment name shown in chat (basename). Default is the PDF's "
             "own basename, which for a run file is edition.pdf",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the request instead of sending it"
    )
    args = parser.parse_args()

    if args.text_file and args.pdf:
        sys.exit("error: --pdf posts an empty body; --text-file cannot be combined with it")
    base, uid, token = resolve_chat()
    text = read_text_file(args.text_file) if args.text_file else read_message()
    if not args.pdf and not text:
        sys.exit("error: no edition text on stdin")

    if args.dry_run:
        attach_note = f" + attach {args.pdf}" if args.pdf else ""
        if args.pdf:
            attach_note += f" as {attachment_filename(args.pdf, args.filename)}"
        kind = "pdf-only" if args.pdf else f"{len(text)} chars"
        print(
            f"dry-run: would POST {kind} to {base}/v1/chats/{uid}/messages"
            f'{attach_note}'
        )
        return

    attachment_uid = None
    if args.pdf:
        attachment_uid = declare_and_upload(
            base, uid, token, args.pdf, filename=args.filename,
        )
    body = compose_payload(text, attachment_uid)

    post_json(base, f"/v1/chats/{uid}/messages", token, "Plow Chat", body)
    after_posted()
    if args.pdf:
        print(f"chat edition posted (pdf only) {args.pdf}")
        print(maybe_print(args.pdf))
    else:
        print(f"chat edition posted ({len(text)} chars)")


if __name__ == "__main__":
    main()