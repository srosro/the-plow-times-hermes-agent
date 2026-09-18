---
name: pt-intake
description: Classify a chat message into a research topic — new topic or status question, and which of the four shapes it is (one-off, subscription, section, assignment) and depth (quick/deep) — write it to pt/topics.json via the topics script, and schedule the run that will produce its edition. Use on every owner chat turn that is not a status question. Status questions (list my topics, list my papers, stop watching X, cancel a dated item, when will it land, add/remove a second daily delivery time, a newspaper at another hour) are answered from the files, not this skill's scheduling path. Never research inside the turn.
---

# pt-intake — a chat message becomes a scheduled research job

This is the entry skill: load it by its exact name, `pt-intake`. It lives
under the `news` category — the category name (`news`) is not a skill and
will not load. Every research or paper request starts here; if this skill is
not loaded, nothing downstream runs and the agent will improvise an
unsourced answer instead.

You classify; a later session researches. **Never run pt-research inside the
turn that received the request** — a chat turn that blocks for minutes while
a browser crawls is the single worst thing this agent can do. The turn's job
is: classify, write, schedule, confirm with a time. Nothing more.

## Read the state first, every turn

Two local files, both cheap:

- `/var/lib/hermes/pt/topics.json` — run `topics.py list` for the readable form
- `/var/lib/hermes/pt/config.json` — delivery preferences (run
  `/var/lib/hermes/skills/pt-shared/scripts/pt_config_gate.py` on it if it looks wrong)

If the config is missing keys, this is a first run: SOUL.md already routed
that to `pt-setup`. Do not treat a greeting as a casual hello — load
`pt-setup` instead. Answer status questions from these files, never from
session memory — another session may have delivered since yours started.

**Keep `owner.language` current, silently, before anything else this turn.**
It is the plain-English name of the language the owner's OWN message (not a
quoted page, not a name) is written in — "Portuguese", "English", "Mandarin
Chinese". A scheduled edition has no live message to read a language from,
so this field is what it falls back to; without it kept current, a paper
scheduled overnight would default to whatever pt-edition guesses instead of
the language the owner actually wants. If this turn's language differs from
`pt/config.json`'s stored `owner.language` (or the key is absent), update it
— write the config, validate with the gate — before classifying the rest of
the turn. This is not a confirmation to ask about and not a change to
narrate: just keep the field true, the same way you never announce reading
`topics.json`.

## Status questions — answer from the file, then stop

These are ordinary turns, not classifications. Do them and end:

- **"what are you watching" / "list my topics"** — run
  `/var/lib/hermes/skills/pt-intake/scripts/topics.py list` and render it as a short list:
  each active topic, its kind, when its edition last landed.
- **"list my paper" / "what's in my paper" / "list my papers"** — run
  `topics.py list` and group by paper. Show the main paper first (hour from
  `delivery.hour`): standing desks, then `section` topics with no
  `deliver_at` (or `deliver_at` equal to that hour), then pending
  assignments. Then one block per distinct `deliver_at` that is not the
  main hour: that hour, then its sections. Extra reprint times
  (`delivery.extra_hours`) are the same main paper again, not a different
  roster — mention them as extra arrivals of the main paper.
- **"stop watching X" / "drop X from my paper"** — resolve X against the
  active topics; if ambiguous, ask which one and stop. Then
  `topics.py cancel <id>`, and immediately run
  `/var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py` so the nightly job is
  removed now rather than at the next bring-up. Confirm in one line.
- **"cancel what I asked for in tomorrow's paper"** — resolve against pending
  `assignment` topics and `topics.py cancel <id>`. A delivered assignment is
  terminal; say so rather than pretending to cancel it.
- **"when will it land" / "did it come?"** — read the topic's `status` and
  `scheduled_for` / `run_on` / `last_edition_at` and answer. A missing
  edition in this session's history is not evidence it never landed.
- **"I want the paper twice a day" / "send it at 10:30 too" / "drop the
  second edition"** — a second (or third) full-paper delivery time is not a
  topic, so it never goes through `topics.py`: it is `delivery.extra_hours`
  in `pt/config.json`, a list of "HH:MM" strings alongside `delivery.hour`.
  Ask the local time they want (in their own zone), convert it with

      /var/lib/hermes/skills/pt-setup/scripts/convert_delivery.py --local-hour HH:MM --owner-tz <owner.timezone from config.json>

  never mental UTC-offset math. Append (or remove) the printed hour in
  `extra_hours`, validate with
  `pt_config_gate.py`, paste its output, then re-run
  `/var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py` so
  `pt-daily-edition-2` (or `-3`, numbered by list order) exists or is
  removed **now**. Never hand-register a cron for this with `hermes cron
  create` — a name register_crons.py's sweep doesn't recognize is invisible
  to every future reconcile forever (measured live: exactly this mistake
  once put a second edition at the wrong hour with nothing able to fix it
  but a human noticing). Confirm in one line, in the owner's own terms —
  "got it, the paper now arrives at 03:00 and 10:30" — never mention the
  container's zone or the conversion.
- **"I want a newspaper about X at 12:00" / "another paper at 18:00 with
  Y" / "put Z in the noon paper"** — this is **not** `extra_hours`. It is a
  `section` with `--deliver-at HH:MM` (container-local, converted with
  `convert_delivery.py` the same way as `delivery.hour`). Sections that share
  an hour share one paper;
  a different hour is a different paper (`pt-paper-HHMM`). Convert the
  owner's local time, then:

      topics.py add --text "<topic>" --kind section --depth quick --deliver-at HH:MM

  If `deliver_at` equals `delivery.hour`, omit `--deliver-at` — it rides
  the main paper. Count news sections **per paper** (max 8 on that hour's
  roster, standing desks do not count). Then run `register_crons.py` so
  `pt-paper-HHMM` exists now. Confirm in the owner's terms: "you'll get a
  sports paper at 12:00".
- **"drop the 18:00 paper" / "cancel the noon newspaper"** — resolve against
  active sections with that `deliver_at`; `topics.py cancel` each, then
  `register_crons.py` so the `pt-paper-*` job is swept. Confirm in one line.
  Dropping one section from a multi-section paper is "stop watching X",
  not dropping the whole paper.
- **"put my mail in the paper" / "drop the letters column"** — `mail.configured`
  in `pt/config.json`. Probe through Latch before writing true, **Google
  (`plow-gog gmail search`) first, Mail.app only if that fails** (same
  argv order as pt-setup). Validate with the gate, then confirm in one line.
  The daily job already exists; no extra cron.

## New topic — classify, then write

Decide, in this order:

**1. Is this a topic at all?** If setup is not finished (`setup_needed.py`
prints `SETUP_NEEDED`), stop and load `pt-setup` — even for a greeting.
Once setup is ready: a greeting, a question about the agent, a complaint
about an edition — none of these is a topic. Answer it like a person and
stop. A question the OWNER wants researched is a topic only when the
answer must be *looked up* on the web, not when it's something you know
or can say in a line.

**2. Which of the four shapes is it?**

| The owner says | Shape | What it becomes |
|---|---|---|
| "my paper should have X" / "X in the paper every day" | `section` | a fixed block in the **main** daily paper (no `deliver_at`) |
| "a paper about X at 12:00" / "Y in the noon newspaper" | `section` with `--deliver-at` | a block in that hour's paper, not the main one |
| "X in tomorrow's paper" / "Y in Friday's paper" | `assignment` | one research pass whose result appears **only** in that day's paper |
| "research X, tell me later" | `one_off` | its own edition, delivered once |
| "update me on Y every night" / "keep an eye on Z" | `subscription` | its own edition, re-run on the delivery hour |
| "send me the paper now" / "generate a copy I can read right now" | **not a topic** | run the daily edition on demand — see below |

**"Give me a copy of my paper" is not a subject to research.** It names no
claim to look up; it asks you to run the paper the owner already
configured, now instead of at the delivery hour. Filing it as a topic
produces an edition *about the phrase*: measured live, it became a
`one_off` reading "A current copy of my daily newspaper", the research pass
went looking for that on the web, and the paper came back with the standing
desks and a news block saying "No separate news desk in this quick pass" —
while 48 saved sections sat unread, because a one-off edition carries only
its own topic. Do not add a topic. Run the daily edition's own steps, which
`pt-edition` documents under **On demand**.

**Before running those steps, post the wait line with the script, not a
sentence you type.** A live turn delivers every assistant chunk to chat —
measured live, that became a play-by-play of every desk and URL, then a
file named `edition.pdf`. First tool call, before research:

    /var/lib/hermes/skills/pt-shared/scripts/chat_status.py --soon

One line in `owner.language` lands in chat ("Seu jornal sai daqui a alguns
minutos." / "Your paper will be ready in a few minutes."). After that,
**no owner-facing text until the PDF.** During research, after every desk
and every topic, run `chat_status.py --wait` — it no-ops until a few
minutes have passed, then posts once ("Mais uns minutos — o jornal está
quase pronto."). Cron-fired papers never call this script. Do not type
those sentences yourself; Hermes will not deliver typed mid-turn text
on plow_chat. Do not narrate a decision in between.

A subscription/section is anything with a cadence in it. A one-off/assignment
is a single ask. When the owner genuinely cannot be read as one or the other,
ask — one question, then classify their answer. Do not silently guess a
cadence into someone's mornings.

**3. Quick or deep?** The clock decides the default: a topic asked during the
owner's waking day is `quick`; a topic asked late at night, anything they
said to "keep an eye on", and every subscription's nightly run is `deep`.
**Sections are always `quick`** — eight sections at deep would blow any
delivery lead, so depth there is not offered. Assignments default `quick`; an
explicit "properly" / "deep dive" can raise them. An explicit "quick, one
line" lowers anything.

Two rules that keep the paper honest:

- **Dedup.** Resolve the new ask against what already exists. "My paper
  should have weather" when the weather desk already runs every day → point
  at that desk instead of adding a news section that would search the same
  forecast twice. Same for calendar and, when configured, mail. "My paper
  should have the dollar" when a dollar section is already active → point at
  the existing one. An assignment whose subject matches a section → one
  question: "every day, or only in tomorrow's paper?".
- **The news desk holds at most 8 sections per paper.** Weather, calendar
  and mail do not count against it. Count only sections that share the same
  paper hour (unscoped + main `delivery.hour` together; each other
  `deliver_at` is its own roster). If the owner asks for a ninth on that
  paper, refuse with the count and ask which one to drop.

Then write it — this script is the ONLY writer for topics.json:

    /var/lib/hermes/skills/pt-intake/scripts/topics.py add --text "<the topic, in the owner's words>" --kind one_off|subscription|section|assignment --depth quick|deep [--run-on YYYY-MM-DD] [--deliver-at HH:MM]

Adding a `section` the owner already has is a no-op: the script prints
`{"duplicate_of": "<id>", ...}` and adds nothing, because a section is an
evergreen standing interest, not a second beat. That output is a success,
not an error — do not retry it with different wording to force a second
copy. One-offs and assignments are never collapsed; "research X again" is
a real second request.

`--run-on` is required for an assignment and refused for every other kind.
`--deliver-at` is section-only: a container-local `HH:MM` for a paper other
than the main daily edition. Omit it for the main paper. Convert the owner's
stated local time with `convert_delivery.py` (owner.timezone from config,
already learned from Latch — do not ask the zone). Compute "tomorrow"/"Friday" as a real calendar date in **the owner's timezone**
(the one in `pt/config.json`), never from the container's clock reading past
midnight. If the day is ambiguous ("the 15th", "next Friday"), ask — never
guess a date onto a promise. Paste the script's output; the `id` it prints is
the topic's identity everywhere else.

## Schedule the run — one-time crons, never inline

All jobs fire in the container's zone (`TZ` in `compose.yml`'s environment —
register_crons.py refuses to register at all if it's empty). pt-setup
converts the owner's stated local delivery hour into that zone once, at
write time, so `delivery.hour` is already correct; register_crons.py no
longer compares it against `owner.timezone` itself. Every job carries
`--deliver plow_chat:${PLOW_HOME_CHANNEL}`: the run's final response IS the
edition, and relaying it is the chat leg.

- **Section** — nothing to schedule by hand: write the topic (with
  `--deliver-at` when it belongs to a non-main paper), then run
  `/var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py` so
  `pt-daily-edition` or `pt-paper-HHMM` is created (or its schedule
  reconciled) **now**, not at the next bring-up.
  Paste the script's output and report its exit status.
- **Assignment** — **never gets a cron of its own**: it rides the daily
  edition. The daily job exists because the assignment is pending (the
  registration you run after writing it sees that). Confirm with the *real*
  date it will appear: if the target day's edition has already left by the
  time the owner asks, the assignment lands in the next one — say so, and
  remember the late tag follows it.
- **One-off, quick** — a one-time job ~3 minutes out. Compute the local time
  now+3m and register it as a 5-field expression with that exact minute:
  `<min> <hour> <dom> <month> *`, name `pt-oneoff-<id>`, skill `pt-research`,
  **`--deliver plow_chat:${PLOW_HOME_CHANNEL}`** (the same target named
  above — restated here because this is the one path that hand-builds the
  `hermes cron create` call instead of going through register_crons.py,
  which bakes the deliver target in; measured live, a run built by hand
  without it completes with a real final response that never reaches chat
  at all — the job succeeds and the owner gets nothing), prompt "Run
  pt-research on topic <id> now, then pt-edition for it. Post the PDF only
  (post_to_chat.py --pdf, empty body). Final response is NO_REPLY. When the
  edition is delivered, mark the
  topic delivered with topics.py and remove this job with `hermes cron
  remove pt-oneoff-<id>`." Record the scheduled moment at add time via
  `--scheduled-for`.
- **One-off, deep** — the same, including `--deliver
  plow_chat:${PLOW_HOME_CHANNEL}`, at the next `delivery.hour` from
  pt/config.json (today if it has not passed, tomorrow otherwise), so the
  result lands with the morning paper.
- **Subscription** — write the topic, then run
  `/var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py` so `pt-subscription-<id>`
  exists now.

If `hermes cron create`, or `register_crons.py`, fails, say so — a topic
whose run was never scheduled is a promise with no paper behind it, and the
owner must hear it rather than wait for an edition that will never come.

## Confirm, in one line

The turn's final response is a confirmation with a time, not a progress
report: "On it — an edition on <topic> lands here in ~3 minutes" or "You'll
get one on <topic> every morning at 7" or "A sports paper at 12:00" or
"Weather joins your paper tomorrow at 7" or "The iPhone 15 price goes in
Friday's paper". Never narrate the
mechanics (no "writing topics.json", no "scheduling a cron"). The edition,
when it lands, speaks for itself.

## Budgeted statuses, kept honest

The run itself moves the topic through `pending → running → delivered` (via
`topics.py mark`, from the cron-fired session). A subscription or section
goes back to `pending` after delivery, awaiting the next fire. An assignment
is terminal once delivered. Never mark a topic delivered yourself in the
intake turn — nothing has been delivered yet, and a delivered mark on a topic
whose edition failed is how a silent gap looks like a working paper.
