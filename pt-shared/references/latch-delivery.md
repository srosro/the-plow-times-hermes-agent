# Latch delivery — when the printed edition has to go through the Mac

The printer sits on the owner's Mac (`lp` targets CUPS there), and this
container has no printer of its own — so when `pt/config.json` says
`printer.configured: true`, `pt-print` ships the edition PDF through Latch:
the same "reach the owner's machine, never this container" pattern every
Latch-using skill draws. The Mac authorises each action; that is the point.

**The model does not perform this handoff.** Measured live, pasting the
rendered HTML into a Latch tool argument killed the LLM stream and `lp`
never ran. A later run that did reach `lp` failed because the queue
refused HTML (`Unsupported document-format "text/html"`). `print_edition.py`
ships `edition.pdf` instead: Latch `write_file` is text, so the bytes ride
as base64 and are decoded on the Mac before `lp`. One command:

    /var/lib/hermes/skills/pt-print/scripts/print_edition.py /var/lib/hermes/pt/run/<id>/edition.pdf /var/lib/hermes/pt/config.json

Inside the script, in this order and nothing else. Paths under `~/Plow`
auto-approve on the Mac.

    1. plow_write_file  path=~/Plow/pt/edition-<date>.pdf.b64  content=<base64 of edition.pdf>
    2. plow_run_command argv=["base64","-D","-i","<abs .b64>","-o","<abs .pdf>"]
    3. plow_run_command argv=["lp","-d","<printer name>","<abs .pdf>"]  network=true

`plow_run_command` takes an **argv array and runs it directly — there is no
shell**. `~` is never expanded, so later steps use the absolute path the
write returned. `network: true` on `lp` is required: `lp` reaches `cupsd`
over a local Unix socket, and Latch's sandbox only grants that with the flag
(the same "Bad file descriptor" failure as the printer probe). If sandboxed
`lp` still returns that error, the script retries once through
`plow_run_applescript` (unsandboxed), which also wakes `cupsd`.

**The print is not done until step 3 exited 0.** A CUPS job id in its output
is the receipt. Any other exit — `lp: unable to print file`, `no such
printer`, a deny on the Mac — is a failed step: the script exits non-zero;
do not pretend the page printed.

**A `{"status":"pending","handle":…}` answer is not a result.** Either call
outruns the Mac's 10-second Latch call budget when review ahead of exec takes
its time; the script polls `plow_get_result` until `ready`. `denied` /
`failed` / `expired` / `unknown` is a failed step.

## Printing is best-effort, never a delivery blocker

The chat edition is the contract; paper is the bonus. Every failure above —
no printer configured, write refused, lp non-zero, the Mac asleep or Latch
not running (the relay's unreachable-device error) — ends the same way: the
chat edition already delivered is the outcome. Do not retry in a loop and do
not queue the page: report in chat, in these words — "Mac unreachable, page
not printed; next scheduled run retries" — and end the run. The next
scheduled run recomposes and re-delivers on its own.
