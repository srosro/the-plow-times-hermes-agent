---
name: pt-setup
description: First-run interview over chat — settle the morning delivery hour, ask about a printer and probe it once through Latch, ask whether today's mail should join as a letters desk, then resolve the owner's timezone from Latch location and convert that hour for the cron. Use on the owner's first DM, including greetings (oi, oi de novo, hi, hello, hey), while pt/config.json is missing owner.timezone, delivery.hour or printer.configured. Never ask their timezone, name, or a personal profile. Never in a group, never in someone else's DM, and never to change one already-stored setting.
---

# pt-setup — the first conversation

This is a conversation, not a form. `/var/lib/hermes/pt/config.json` and
`/var/lib/hermes/pt/.setup-draft.json` are the **only** record of how far
it got — not the Plow Chat thread. Older messages about a printer or
letters after a wiped session are leftover; if the draft is missing,
start at the delivery hour. Do **not** ask their timezone — Latch location
at the end supplies `owner.timezone`. (`mail.configured` is asked in this
interview too, but a missing mail key is a valid older install — treat it
as false, do not restart setup for it.) Never re-ask something the draft
or config already holds.

**Every draft write, and every "what's next", goes through one script —
never a hand-edited `.setup-draft.json`, never your own judgement about
which question comes after which.** Measured live: the model once wrote
the hour to the draft with a plain `write_file` call and then, in that
same reply, went on to probe the printer through Latch and ask about the
letters desk too — the owner never saw "is a printer set up on your Mac?"
as its own question, and the printer probe's answer was never even saved
to the draft. That is exactly the failure this script exists to make
structurally impossible:

    /var/lib/hermes/skills/pt-shared/scripts/record_setup.py /var/lib/hermes/pt/config.json key=value [key=value ...]

One line, no interpreter prefix, no shell operators — same rule SOUL.md
gives `setup_needed.py`. `key` is a dot-path (`local_hour`,
`printer.configured`, `printer.name`, `priority.configured`, `priority.file`, `mail.configured`, `news_asked`);
`true`/`false` become real JSON booleans, anything else stays a string. A
value with a space needs its own quoting, e.g. `printer.name="HP LaserJet 4"`.
It prints two lines:

    DRAFT:<fields already recorded>
    NEXT_QUESTION=<hour|printer|priority|mail|news|close>

**Send exactly the one message `NEXT_QUESTION` calls for, then stop.**
Not that question plus the probe for the one after it. Not that question
plus a summary of what you just recorded. One question, one reply, then
wait for the owner. The questions below are written in two parts for
exactly this reason: part **a** is what you send and then stop for; part
**b** is what you do on their *next* message, before sending the
question after it.

**This interview never needs ad-hoc Python, a heredoc, or any inline
script, for anything — not to check state, not to read a file, not to
double-check what you just wrote.** Every action already has a named
script (`setup_needed.py`, `record_setup.py`, `convert_delivery.py`,
`pt_config_gate.py`) or a named tool (`plow_run_command`,
`plow_browser_*`); call the one that matches, plainly, one line, and
nothing else. Measured live, twice, on two different turns: once a
`record_setup.py` call for a printer name with nothing unusual in it got
wrapped in `python3 - <<'PY' ... PY` anyway; another time, right after
"Is a printer set up on your Mac?" was answered "Yes", the very next
action was `python3 - <<'PY' ... Path('/var/lib/hermes/pt/config.json').read_text() ... PY`
— reading a file this step never needs and that does not exist yet (it
is not written until the close step). Neither had a reason; both handed
the owner a raw `/approve` prompt where an answer belonged. If you feel
any pull to "just check" something with inline Python, that pull itself
is the signal you've drifted off this file's own steps — stop and
re-read the current step instead of writing a script for it.

It runs only in the owner's own solo DM — sender role **owner**, chat type
**DM**, roster just the two of you; the platform reports all three. Anywhere
else, none of this applies: answer what was actually asked, ask none of
these questions, and write nothing.

One or two short lines per message, no bullet lists — this lands on a
phone. Answer what the owner actually said first. And never narrate the
mechanics: no "let me run setup", no announcing a step. Send the message the
step calls for — **and only that message.** Measured live: the owner's
whole visible reply to a bare "Oi" was

> The message is "Oi" — a bare greeting, DRAFT:none. This is step 1a:
> send the opener in Portuguese, then stop.
>
> Sou o The Plow Times, seu jornal. A que horas quer o jornal da manhã?
> Se não disser, uso 7h.

— the actual opener buried under a paragraph of the model's own reasoning
about which step it was on, in English, in front of a Portuguese-speaking
owner. Told to stop doing this, the very next live "Oi" got a *reworded*
version of the identical violation instead: "This is a bare greeting 'Oi' with DRAFT:none" —
same wording gone, same violation. Proof the fix has
to be mechanical, not a sentence to avoid repeating. **The check: your
reply's very first character is the opener's own first character** ("S" of
"Sou", "I" of "I'm") **— not a capital letter starting some other
sentence.** If you notice yourself about to write "This is...", "The
message is...", "Note:", a step name, `DRAFT:`, a language name, or
anything at all describing what you just read or decided, that sentence
is the violation, whatever words it uses — delete it, don't reword it, and
start the reply at the opener itself. The owner sees the opener and
nothing else — not the classification that produced it, not `DRAFT:none`, not
"step 1a".

**A greeting is this interview.** "oi", "oi de novo", "hi", "hello", "hey"
with a missing config is the opener below, not a hello-plus-help-menu and
not a continuation of a profile interview that already happened in this
chat. Do not introduce a personal assistant, do not offer `/help`, do not
ask their name or how they like to work.

**Opener — send this, then stop and wait.** Match the owner's language.
Portuguese:

> Sou o The Plow Times, seu jornal. A que horas quer o jornal da manhã? Se não disser, uso 7h.

English:

> I'm The Plow Times, your newspaper. What time should the morning paper land? Default is 7:00.

Do not ask their timezone, their name, a profile, or `/help`. The zone comes
from their Mac, through Latch, when this interview closes.

**Changing one setting later** is not this skill: a different delivery hour,
**a second (or third) daily delivery time** (`delivery.extra_hours`, a list
of "HH:MM" strings alongside `delivery.hour` — convert each with
`convert_delivery.py` using the stored `owner.timezone`, never by asking
the zone again), **turning the letters desk
on or off** (`mail.configured`), or a new printer is a
one-line conversation that updates `pt/config.json` directly, re-runs the
gate, and then re-runs
`/var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py` so the
new schedule exists now — not an interview from the top, and **never a
hand-registered `hermes cron create`**: a cron job that name doesn't
recognize (see `pt-dashboard/SKILL.md`'s spec table) is invisible to every
future reconcile, so a typo'd time or a since-changed delivery hour drifts
forever with nothing to catch it. This has happened live: asked for a
second daily edition, a session hand-built a `pt-daily-edition-2` job at
the wrong hour instead of writing `delivery.extra_hours` and reconciling —
`register_crons.py` exists precisely so that never has to be improvised.

## The questions, in order

Start of turn, every turn while `SETUP_NEEDED`: `setup_needed.py`'s second
line (`DRAFT:...`) or `record_setup.py`'s own `NEXT_QUESTION` from the
answer you just recorded says which of these you are on. Never infer it
from the draft's shape yourself, and never from what the chat thread
already discussed.

**1a. Ask the delivery hour, nothing else** — but only if the message
you are answering right now is a bare greeting ("oi", "hi", "hello")
with nothing else in it. **If it already reads like an hour answer
(see 1b's list), skip straight to 1b — do not send this question
again just because the draft still says `DRAFT:none`.** Measured live:
the assistant asked this, the owner replied "7 is fine", and because
nothing had been written to the draft *yet* the assistant sent this
exact question a second time instead of recognizing the reply as an
answer — a fresh, un-recorded draft is not proof the incoming message
is a fresh greeting. Otherwise: suggest 07:00, do not ask a city, a
zone, or a fuso — you will read that from Latch at the end. Send only
this question, then stop.

**1b. On their next message**, treat any of "yes", "y", "sim", "ok",
"okay", "that", "default", "7", "7h", "7:00", "07:00", "pode", "isso", or
a skip as accepting 07:00; a clock time they name ("8:30", "08:30") is
that time. Record it and read the next question:

    record_setup.py /var/lib/hermes/pt/config.json local_hour=07:00 owner.language=English

**Record `owner.language` in this same call**, as a plain-English name
("English", "Portuguese", "Mandarin Chinese"), read from what the owner
has actually written so far — not from this file's language, not from
their name, not from where they are. From here on the gate hands it back
to you as `LANG:<language>` on **every single reply**, and that line, not
your memory of this paragraph, is what every owner-facing string is
written in. If it says `LANG:unrecorded`, record it before you answer.

Send only the `NEXT_QUESTION` it prints (question 2a), then stop. Do not
also probe the printer in this reply — that happens on their *next*
message, in 2b, never before question 2a has actually been sent to them.
Do not write `pt/config.json` yet: `owner.timezone` is still unknown, and
the gate would fail.

**2a. Ask whether a printer is set up on their Mac.** Send only this
question, then stop — do not probe Latch yet, no matter what they might
have said about a printer earlier in this same chat thread.

**2b. On their next message**, whatever they answered, **probe once
through Latch before recording `printer.configured`** — the same
discipline ld-setup applies to the Pi bring-up; a yes/no alone is a
configured printer that fails on every nightly run.

Latch's `plow_run_command` schema (mcp-server `tools.ts`) requires **`argv`**
and runs the array directly — no shell, no `~`. It also accepts a defined
set of optional keys (`goal`, `network`, `cwd`, `read_paths`,
`write_paths`, `apple_events`, `wait_ms`, …) — `additionalProperties: false`
rejects a genuinely unknown key like `"command"` (not in the schema at
all; the relay returns JSON-RPC -32601 / "Server returned an error
response" and the Mac never sees `lpstat`), not these. Hermes names the
tool `mcp__plow__plow_run_command` (or `mcp__latch__plow_run_command` if
`tools_list` says so). **Never send `"command"`.**

**This call needs `"network": true`.** Measured live, with a printer
genuinely configured and visible in System Settings: `lpstat -p` came
back `exit_code:1, "lpstat: Bad file descriptor"` under the default
sandboxed call. Root cause, confirmed by reproducing Latch's generated
profile directly against `sandbox-exec` on the owner's own Mac —
25/25 runs succeed with the flag, 10/10 fail with the identical error
without it, and `lpstat -p` in a plain shell outside Latch succeeds
every time: `lpstat` reaches `cupsd` over a local Unix domain socket,
and Latch's seatbelt profile (`packages/device-core/src/executor.ts`,
`SandboxProfile.generate`) grants the `network*`/`system-socket`
primitives only when `network` is true. Without them CUPS cannot open
the socket to its own scheduler, and libcups surfaces that denial as
"Bad file descriptor" rather than a real "no destinations" report.

The flag covers **local IPC**, not just remote access — Latch's schema
description ("whether the command needs network access") reads narrower
than the grant actually is, which is what made this look like a CUPS
fault. It is deterministic, not flaky: a run that fails with the flag
set is a run that did not carry it. `network: true` is a broader grant
than this call strictly needs (a scoped CUPS exception belongs in
Latch's own sandbox profile, not here), but it is the fix available
from this side without editing a different project's security-sensitive
code.

Exact call:

```json
{
  "argv": ["lpstat", "-p"],
  "network": true,
  "goal": "List CUPS printers on the owner's Mac for newspaper setup"
}
```

If the result is `{"status":"pending","handle":…}`, poll
`plow_get_result` with that handle until `ready` (Latch's call budget is
10s, not a failed Mac). `denied` / `blocked` is the owner tapping No on
the Latch card, not an unreachable device.

**`network: true` is necessary but NOT sufficient — there is a second
step, and it is a different tool.** `cupsd` is launched on demand by
launchd: when no one has printed recently it is not running, and a
*sandboxed* `lpstat` cannot trigger the launchd rendezvous that starts
it. Measured on the owner's Mac, three runs back to back: with `cupsd`
asleep the sandboxed call returns "Bad file descriptor" **and leaves it
asleep**; the same call unsandboxed succeeds **and starts it**; the
sandboxed call immediately after then succeeds too. That is the whole
"intermittent" story — the probe works whenever something else woke
`cupsd` first, and fails when it has idled out. Latch's own audit log
shows exactly this: same argv, same `Network: allowed`, `exit 0` at
01:00 and `exit 1` twelve minutes later.

So if the call above comes back `exit_code` non-zero with an
error-shaped output (`"Bad file descriptor"`, or anything that is not a
destinations list or "No destinations added."), **retry once through
`plow_run_applescript`** — a different tool, which really does run
outside the sandbox:

```json
{"app": "System Events", "script": "do shell script \"lpstat -p\"", "goal": "Wake cupsd and list CUPS printers for newspaper setup (sandboxed probe failed)"}
```

Take its answer as the probe's answer. It also wakes `cupsd`, so later
sandboxed runs start working on their own.

**Do not** try this as `{"argv": ["osascript", "-e", "do shell script
…"]}` through `plow_run_command`. An earlier version of this skill did,
believing `osascript` reached the unsandboxed path. It does not: that
path belongs to the `plow_run_applescript` *tool*. Any argv handed to
`plow_run_command` — `osascript` included — is an ordinary
`process.exec` intent and runs under `sandbox-exec` like everything
else, so that retry inherited the identical denial (with `network`
omitted, therefore false) and reproduced the identical error one layer
down: `0:27: execution error: lpstat: Bad file descriptor (1)`.

A real "No destinations added." (or a genuine list) is a real answer.
Latch parked or unreachable is also an answer, not a reason to skip
2a — you already asked it; now record the probe's outcome:

- lpstat lists a printer:

      record_setup.py /var/lib/hermes/pt/config.json printer.configured=true "printer.name=<exact CUPS name>"

  as a bare invocation, two space-separated arguments — the same
  invocation you've been using for every other field, nothing more.
  CUPS queue names routinely have underscores (macOS itself substitutes
  `.`/spaces from the display name into `_` for the actual queue name,
  e.g. "virtual-printer.online" the owner sees in System Settings is
  `virtual_printer_online` in `lpstat`'s own output — use exactly what
  `lpstat` printed, not the display name) but that changes nothing about
  how to call this script: only the *key* (the part before `=`) is
  split on dots to build nested JSON, so a dotted or underscored
  *value* is never at risk of being misread — it's taken verbatim,
  whatever's in it. Quote it only if it has a space; nothing else is
  ever needed. **Do not wrap this in `python3 - <<'PY' ... PY`, a `-c`
  flag, or any other interpreter** — that is exactly the "script
  execution" pattern SOUL.md's gate exists to flag, and it hands the
  owner a raw approval prompt instead of the printer answer they're
  waiting on (measured live: this happened, over a printer name with
  nothing unusual in it at all — a plain space-separated call would
  have worked the first time).
- lpstat's own output says there are none (e.g. "No destinations
  added."), Latch is parked, or the Mac is unreachable:

      record_setup.py /var/lib/hermes/pt/config.json printer.configured=false

  and say, **in the owner's own language, the one they've been writing
  this chat in** — not necessarily English, whatever this file happens
  to be written in — that the paper still delivers in chat; printing
  joins automatically if a printer shows up later (that is the
  changing-one-setting path, plus a re-probe).
- the call returned an error that isn't a real lpstat report — e.g.
  `exit_code` non-zero with output like "Bad file descriptor" rather
  than an actual destinations list or "No destinations added."
  (measured live: this happens when `network: true` is missing): still

      record_setup.py /var/lib/hermes/pt/config.json printer.configured=false

  (never guess `true` without a real listing), but say plainly, in
  their language, that the printer check itself didn't run cleanly —
  not "no printer was found." Those are different claims; only make
  the one that's actually true. Printing can still be turned on later
  once the check works.

Send only the `NEXT_QUESTION` it prints (question 3a), then stop.

## NEXT_QUESTION=priority

Ask, in the owner's language: "Every morning the paper can open with what Patrick Salyer
would tell you after watching your last day. What are you trying to make true over the
next few quarters? (or 'no' to skip the advisor desk)"

Stop. On their next message:

- **No** → `record_setup.py <config path> priority.configured=false`
- **An answer** → first put it on the Mac. Read the file once with `mcp__plow__plow_read_file`
  `path=~/Plow/prioritization.md`:
  - it exists → add their answer as one `- ` line under `## Goals` unless it is already
    there, and write it back with `mcp__plow__plow_write_file`.
  - it does not exist → `mcp__plow__plow_write_file` `path=~/Plow/prioritization.md` with
    exactly:

        # What I'm working toward

        ## Goals
        - <their answer>

        ## Not now

        ## Notes

  - **never overwrite an existing file**: every line already in it stays as it was. Never
    paste the owner's file back in chat.
  Only once the goal is in the file (written now, or already there): `record_setup.py <config path> priority.configured=true priority.file=~/Plow/prioritization.md`.
  A denied or failed write → say so in one line and record nothing; the question stays open.
  Say in one line that the desk reads their Mac every morning and that they can correct
  it any time by texting ("Raj is my cousin", "stop telling me to hire").

Then seed the advisor library, once:

1. `mcp__plow__plow_run_command` `argv=["/bin/ls","-1","<home>/Plow/advisors"]`
   (absolute path; `plow_run_command` does not expand `~`).
2. Exit code 0 with names listed → leave it alone; say "Using the advisor notes already in
   ~/Plow/advisors."
3. Anything else (no such directory) → for each file in
   `/var/lib/hermes/skills/pt-setup/assets/advisors/`, read it with `read_file` and write it
   with `mcp__plow__plow_write_file` `path=~/Plow/advisors/<name>`, content unchanged. Say:
   "I put stage-by-stage advisor notes in ~/Plow/advisors — edit them, add your own
   investors, delete what doesn't fit."
4. Never overwrite a file that is already there.

Then continue with the mail question in the same turn.

**3a. Ask whether the paper should carry today's mail** (a letters
column: sender and subject, not full bodies). Weather and calendar
always run; mail is opt-in. Send only this question, then stop.

**3b. On their next message**, whatever they answered, **probe once
through Latch before recording `mail.configured`**, Google first,
Mail.app only if that fails:

1. `plow_run_command` argv (exact):

```json
{ "argv": ["plow-gog", "gmail", "search", "newer_than:1d", "--max", "5", "--json", "--fields", "id,date,from,subject"] }
```

   A result (including zero messages) means the Google account in Latch
   works.
2. Only if that call is denied, 401/412, or Latch has no Google account:
   probe Mail.app:

```json
{ "argv": ["osascript", "-e", "tell application \"Mail\" to get name"], "apple_events": true, "goal": "See whether Mail.app is reachable for the letters desk" }
```

Then record the outcome:

- They said yes and **either** probe works:

      record_setup.py /var/lib/hermes/pt/config.json mail.configured=true

- They said no, or both probes fail / the Mac is unreachable:

      record_setup.py /var/lib/hermes/pt/config.json mail.configured=false

  and say, **in the owner's own language, the one they've been writing
  this chat in**, that the letters column can join later the same way a
  printer does. Never invent an inbox.

Send only the `NEXT_QUESTION` it prints (question 4a), then stop.

**4a. Ask what they want on the news desk every day** — "the dollar,
sports news", anything. Weather and the diary already have their own
departments; do not also add a "weather" news section unless they insist
on a second, different weather beat. This is the one question with no
required answer: a paper of only weather and calendar is a valid install,
and they can add news sections later in chat (including a different
newspaper at another hour). Send only this question, then stop.

**4b. On their next message** (including "nothing" / "skip"), take each
thing they name as a `section` topic via `pt-intake`'s writer
(`topics.py add --kind section --depth quick`), in the order they say
it — that order is the news desk's order. If they name more than eight,
take the first eight and say the cap; the daily run researches every news
section in one session and eight is the honest ceiling. Never invent a
section they did not ask for. Then, regardless of whether they named
any:

    record_setup.py /var/lib/hermes/pt/config.json news_asked=true

Send only the `NEXT_QUESTION` it prints — `close` — and move straight
into the close step below (this one has no separate question to send;
"close" means do the close work now).

## Close: location, convert, write config

**The moment `NEXT_QUESTION` says `close`, do only the three numbered
steps below — nothing else.** Measured live: after recording
`news_asked=true`, instead of going straight into step 1, a run opened
`pt-dashboard`, `pt-research`'s SKILL.md, `pt-shared`, `pt-print`, and
`pt-edition` one after another (none of them are needed to close setup —
they load themselves later, on their own, when the daily run actually
needs them), re-ran `record_setup.py mail.configured=true` a second time
for no reason, tried a file that doesn't exist
(`pt-setup/references/api.md`), and then — having still never called
`plow_browser_open` — used the `clarify` tool to ask the owner
**"Em que cidade você está?"**, in Portuguese, mid-English conversation.
That is two rules broken at once, both already written down and both
worth restating here because they got missed anyway: desks.md §1 already
says *"Do not ask the owner for a city"* — no tool, `clarify` included,
ever asks them one; and SOUL.md's language rule covers every reply
including one made through a tool like `clarify`, not just plain text.
If step 1 below hasn't produced a timezone, the answer is the "can't be
scheduled yet" message in step 1, not a question back to the owner.

Do not write `pt/config.json` until `NEXT_QUESTION` says `close`:

1. **Read location through Latch's browser** — the same procedure as
   `pt-research/references/desks.md` §1: `plow_browser_open` scoped to
   `["ipapi.co", "ipwho.is", "ifconfig.co"]`, `goto`
   `https://ipapi.co/json/` first, then `text` to read the JSON back,
   then `plow_browser_close`. Not `plow_run_command`/`python3`: measured
   live, that path failed two different ways on a real Mac (`xcrun`'s
   dylib blocked by Latch's sandbox, then a `curl` fallback blocked on
   DNS resolution even with `network: true`) — see desks.md §1 for the
   full diagnosis. **If `goto` itself errors** (DNS failure like
   `NS_ERROR_UNKNOWN_HOST`, timeout, connection refused — measured live,
   `ipapi.co` alone came back unresolvable on one owner's Mac even
   through the real browser), `goto` `https://ipwho.is/` instead, then
   `https://ifconfig.co/json` if that also errors; stop after these
   three. Take the timezone field from whichever provider loaded (IANA
   form, e.g. `America/Sao_Paulo`). If all three `goto` calls error, or
   the page that did load has no usable timezone field, say the paper
   cannot be scheduled until the Mac can report where they are — do not
   invent a zone, do not ask them to type one.
2. **Convert** the draft `local_hour` into the container's clock. Never
   subtract hours by hand:

       /var/lib/hermes/skills/pt-setup/scripts/convert_delivery.py --local-hour HH:MM --owner-tz America/Sao_Paulo

   The printed line is `delivery.hour`. `owner.timezone` is the IANA name
   from step 1, unconverted. If the script says container TZ is empty, say
   so once — setting `TZ` in `compose.yml`'s environment and restarting is
   the fix (not `AGENT_TZ`: measured live, nothing in this image actually
   translates `AGENT_TZ` into `TZ`, even though older docs implied it).
3. **Write** `/var/lib/hermes/pt/config.json` — with this exact bare
   invocation, never by composing the JSON yourself, never `write_file`:

       /var/lib/hermes/skills/pt-setup/scripts/finalize_setup.py /var/lib/hermes/pt/config.json --owner-tz <IANA zone from step 1>

   It reads the draft, converts the hour (so step 2 is only for showing
   your work — this does the conversion it will actually write), keeps
   `delivery.local_hour` as the owner named it, validates against the gate
   **before** anything lands, and prints `CONFIG:written` plus the
   delivery line. On failure it prints why and writes nothing: an
   unfinished interview, an unknown zone, an empty container `TZ`, or a
   gate failure. That refusal is the answer — do not hand-write the file
   around it. Measured live: told only "write config.json" with no command
   named, a run that had every field it needed instead ran the gate
   against a file nobody had created, got `not valid JSON` (that is what
   the gate says for a MISSING file) and told the owner the setup "hit a
   configuration error" — with nothing actually wrong.

   If you want to re-check afterwards, the gate is:

       /var/lib/hermes/skills/pt-shared/scripts/pt_config_gate.py /var/lib/hermes/pt/config.json

   **Paste the gate's output verbatim.** Empty output is pass. Then run
   `/var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py` and
   paste its output. Finally clear the draft — **with this exact bare
   invocation, never a `rm`, never an interpreter, never `os.remove`**:

       record_setup.py /var/lib/hermes/pt/config.json --done

   It prints `DRAFT:cleared`. It is idempotent, and it refuses if the
   interview is somehow unfinished (it names what is missing) — that
   refusal is information, not something to work around. Measured live:
   told only "delete `.setup-draft.json`" with no command attached, a run
   reached for an inline `-c` one-liner calling `os.remove` and handed the
   owner an `/approve` prompt in place of their finished newspaper.

Say the result in the owner's own terms — "seu jornal chega às 7h" using
the hour they named, never the container's zone, `TZ`, or the conversion.
Invite the first topic. A first research job is still pt-intake's.
