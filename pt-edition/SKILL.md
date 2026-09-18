---
name: pt-edition
description: Compile one or more topics' research notes into edition.json, render it with render_edition.py into printable HTML and PDF, post the PDF only via post_to_chat.py (which also runs print_edition.py when a printer is configured), end the turn with NO_REPLY, and mark the topics it carried. Runs in the cron-fired session after pt-research.
---

# pt-edition — notes become the edition

The edition is the product. Every rule here serves one idea: a reader on a
phone (or holding a printed page) gets a short, sourced answer, and nothing
in it is a guess.

**Compiling, rendering and delivering happen silently — the owner sees the
PDF (or the on-demand copy's own confirmation) and nothing about the steps
that produced it.** Measured live, on an on-demand "send me a paper now"
with the owner watching in real time: "PDF rendered successfully. Now
posting it to chat.", "PDF posted. Now marking topics delivered and
handling the print leg." — in English, mid-run, on a Portuguese setup. No
step in this skill's recipe calls for a sentence like that; a tool call's
own result is never something to narrate back.

## Write `edition.json`, never the layout

You compile structured content; the layout is code, not text. **Never write
HTML.** Hand-write `edition.json` under the run directory:

```json
{
  "date": "2026-09-11",
  "location": "Sao Paulo",
  "sections": [
    { "kind": "section", "desk": "weather",
      "title": "Weather",
      "headline": "Rain in the afternoon",
      "body": "3–6 sentences from desk-weather notes, city named.",
      "forecast": [
        { "day": "Tue", "date": "17/05", "icon": "partly-cloudy", "high": 19, "low": 9 },
        { "day": "Wed", "date": "18/05", "icon": "rain", "high": 17, "low": 6 }
      ],
      "sources": ["https://…"],
      "could_not_source": [] },
    { "kind": "section", "desk": "calendar",
      "title": "Calendar",
      "headline": "Two meetings before noon",
      "body": "9am — Product sync.\n\n11am — Investor call.\n\nUpcoming: Thu — dentist at 3pm.",
      "schedule": [
        { "time": "9am", "title": "Product sync", "icon": "meeting" },
        { "time": "11am", "title": "Investor call", "icon": "call" },
        { "time": "Thu", "title": "Dentist at 3pm", "icon": "reminder" }
      ],
      "sources": ["Calendar.app"] },
    { "kind": "section", "desk": "mail",
      "title": "Letters",
      "headline": "Three messages overnight",
      "body": "Ana Costa — partnership proposal.\n\nBanco XP — invoice available.\n\nGitHub — new pull request awaiting review.",
      "messages": [
        { "sender": "Ana Costa", "subject": "Partnership proposal" },
        { "sender": "Banco XP", "subject": "Invoice available" },
        { "sender": "GitHub", "subject": "New pull request awaiting review" }
      ],
      "sources": ["Gmail"] },
    { "kind": "section", "desk": "sports",
      "title": "Sports",
      "headline": "Flamengo takes the field tonight",
      "body": "Flamengo hosts Palmeiras tonight at 9pm for the Brasileirão. Corinthians lead São Paulo 1–0 in the second half. Grêmio and Internacional drew 2–2 in today's early game.",
      "games": [
        { "home": "Flamengo", "away": "Palmeiras", "status": "scheduled", "note": "Tonight, 9pm" },
        { "home": "Corinthians", "away": "São Paulo", "status": "live", "home_score": 1, "away_score": 0, "note": "62'" },
        { "home": "Grêmio", "away": "Internacional", "status": "final", "home_score": 2, "away_score": 2 }
      ],
      "sources": ["https://site.api.espn.com"] },
    { "kind": "section", "topic_id": "t_8c1d", "desk": "news",
      "title": "The dollar",
      "headline": "The real headline",
      "body": "3–6 sentences, every one traceable to a note.",
      "sources": ["https://…"],
      "could_not_source": ["…"] },
    { "kind": "assignment", "topic_id": "t_3f2a", "run_on": "2026-09-11",
      "desk": "news",
      "title": "iPhone 15 price",
      "body": "…", "sources": ["https://…"],
      "tag": "special for this edition",
      "could_not_source": ["…"] }
  ]
}
```

- **Never write a Sudoku into `edition.json`.** The renderer always
  generates and verifies one Easy or Medium puzzle from `scripts/sudoku.py`,
  seeded on `date`, and fills `{{SUDOKU}}`. There is no JSON field for it;
  a grid the model authored would be the one thing this page cannot afford
  to get wrong.
- **`topic_id` is mandatory per section** — the delivery step marks each
  topic from it. Without it, marking depends on session memory, which SOUL.md
  forbids. `run_on` is required for an assignment.
- **The title is the topic's text**, trimmed of pleasantries; it is the
  owner's own words.
- **Write `headline` and `body` in `pt/config.json`'s `owner.language`** —
  Portuguese in, Portuguese out; English in, English out; Mandarin in,
  Mandarin out, whatever pt-intake last recorded there. This is the whole
  edition's reading language, not a translation step: research the sources
  in whatever language they're actually in, then write the synthesis in the
  owner's. `title` stays exactly as the owner phrased their topic (it may
  legitimately be in a different language than today's `owner.language`
  if they asked for it earlier, in another language — never retranslate
  someone's own words). No `owner.language` at all (an install from before
  pt-intake started keeping it, or one where the owner has only ever
  written once) is the one case to fall back on the language the sourced
  notes themselves read most naturally in, never a hardcoded default.
- **3–6 sentences per body, every one traceable to a note.** If a claim is
  not backed by a note, cut the sentence.
- **`could_not_source` is per section, not global** — it belongs to the block
  it qualifies. Unsourced claims are named, not hidden.
- **`desk` is the newspaper department, and each one is its own page
  slot** — not a mixed sidebar. `"weather"` → `{{WEATHER}}`, `"calendar"` →
  `{{CALENDAR}}`, `"mail"` → `{{MAIL}}`, `"sports"` → `{{SPORTS}}`,
  `"news"` (the default) → `{{SECTIONS}}`. Same title / headline / body /
  sources shape in every slot.
- **`priority` is optional, priority-desk-only, and copied from
  `run/desk-priority/notes.json` without rewriting.** When present it
  replaces the prose body on the printed page (`skip_body`); `headline` is
  the day's priority and `body` is the first step in prose for the chat
  edition. Shape: `why` (1–3 objects with `text` and `source_label`),
  `first_step`, optional `not_today` (at most two strings), and optional
  `stage_label`, `stage_why`, `yesterday`, `week`, `draft` (non-blank
  strings), `who` (at most three strings) and `today` (at most four
  `{"time": "HH:MM" or null, "title", "note"}`).
- **`forecast` is optional, weather-only, and drawn — not written.** 1-6
  day objects, each `day` (short label, e.g. "Tue"), `date` (e.g.
  "17/05"), `icon` (exactly one of `sun`, `partly-cloudy`, `cloud`,
  `rain`, `storm`, `snow` — the renderer draws a fixed monochrome icon
  for each key, so anything else fails the gate), and `high`/`low`
  (numbers, the units come from the template, not the JSON) — deliberately
  temperatures and the icon only, nothing else; wind/humidity/precip
  were tried and dropped so the strip stays readable at a glance. Only
  include it when desk-weather's notes
  actually name a day-by-day forecast (icon condition + high/low) for
  more than just today; a same-day-only forecast has nothing to put in
  a second or third cell, so leave `forecast` out and let the prose
  `body` carry it alone, same as before this field existed.
- **`schedule` (calendar-only), `messages` (mail-only) and `games`
  (sports-only) are the same idea as `forecast`, optional and drawn.**
  `schedule` is a non-empty list of `{ "time", "title", "icon" }`,
  `icon` exactly one of `meeting`, `call`, `task`, `reminder`, `note` —
  pick the one that actually matches the event (a call is `call`, not
  `meeting`; a standing reminder like "dentist at 3pm" is `reminder`;
  anything that doesn't fit the other four is `note`, never guessed as
  `meeting` to avoid picking). `messages` is a non-empty list of
  `{ "sender", "subject" }` — no icon field, since every letter draws
  the same envelope mark. `games` is a non-empty list of `{ "home",
  "away", "status", "home_score", "away_score", "note" }` — `status`
  exactly one of `scheduled`, `live`, `final`; `home_score`/`away_score`
  are required (integers) for `live`/`final` and meaningless for
  `scheduled`; `note` is optional free text (a kickoff time for
  `scheduled`, a clock/round for `live`, e.g. "62'", nothing needed for
  `final`). All three still need the prose `body` filled in as before
  (the chat edition has no icons to fall back on); include the
  structured field only when the notes actually give you distinct
  events, senders or games to list, not as a mandatory duplicate of the
  prose.
- **`image` (news sections only) is optional: `{ "url", "credit" }`.**
  `url` must be the direct link to the image file itself (ends up in an
  `<img>` tag), `credit` is a short optional line ("Reuters", "AP
  Photo/Jane Doe") printed under the photo. render_edition.py fetches
  it, converts it to grayscale and crops it to a fixed ratio in Python
  (the page's palette is ink/grey/white, and WeasyPrint doesn't
  implement CSS `filter` or `object-fit`, so the pixels have to already
  be right before they reach the page) — a bad URL, a timeout or a
  non-image response just means the story prints without a photo, never
  a broken page. **Only use an image the source itself offered for
  reuse** — an article's own `og:image`/social-preview image or an RSS
  item's enclosure/media:thumbnail, the same kind of thumbnail a feed
  reader or link-preview card would show, never a photo scraped off a
  page some other way, and never one from a paywalled or explicitly
  restricted source. When in doubt, leave `image` out; a story with no
  photo is the normal case, not a gap to fill. This is a small
  single-reader paper, not a publication — that doesn't make an image's
  own rights irrelevant, so stay inside "the kind of thumbnail the
  publisher already serves for syndication."
- **Calendar and mail bodies are one item per paragraph, blank-line
  separated — never joined with periods into one run-on sentence.** The
  template renders each paragraph as its own bulleted line; "9am —
  Product sync.\n\n11am — Investor call." reads as two clean bullets,
  "9am — Product sync. 11am — Investor call." reads as a dense wall of
  text. One event, one sender, one line each.
- The daily paper always includes weather and calendar from
  `run/desk-*/notes.json`. Mail only when `pt/config.json` has
  `mail.configured: true` **and** `run/desk-mail/notes.json` exists;
  otherwise omit the mail block entirely so that slot stays empty.
  Sports is the same pattern: only when `pt/config.json` has
  `sports.configured: true` **and** `run/desk-sports/notes.json`
  exists; otherwise omit the sports block entirely — never fill it with
  a generic league digest just because a desk slot exists for it. A focused
  paper at another hour uses the same desks plus **only** the news topics
  this run researched (the sections whose `deliver_at` is that hour). Never
  compile a main-paper section into a noon paper, or the reverse. Owner
  `section` and `assignment` topics are always `"desk": "news"`. Do not put
  a news topic on the weather desk to make it look important.
- **Pagination is the renderer's job.** News that does not fit one Letter
  sheet continues on page 2+ of the PDF (WeasyPrint, `column-fill: auto`).
  Each desk box stays whole; if the rail itself overflows, the next desk
  starts on the following page. Never hand-split copy across pages.
- **`location` is this run's city** from the Latch location step, a string,
  optional. It is the dateline, not a stored profile: if location failed,
  omit the field.
- **`layout` is optional, `"main"` (the default) or `"sidebar"`.** Only news
  blocks honor it — a news story the owner wanted as a boxed panel. Standing
  desks ignore it; the renderer already puts them on the rail.
- **Never pad.** Three sourced sentences beat six where one is a guess. An
  empty pass (zero sourced claims) is still an edition: the title, one honest
  sentence ("nothing usable in the budget this time"), and what was tried.
  A thin weather or calendar desk is still printed; it is a department of
  the paper, not optional filler.

## On demand — "send me the paper now"

The owner asking for a copy right now is **not** a new topic (see
`pt-intake`'s routing table). It runs the same edition the 7am cron runs,
sections and all. Do not retype those steps from memory and do not write a
shorter version: ask for them, so an on-demand copy can never drift from
what the scheduled run actually does.

    /var/lib/hermes/skills/pt-dashboard/scripts/register_crons.py --show-daily-recipe

That prints the daily run's steps verbatim, from the same function the cron
job is built from. Follow what it prints, exactly, including the run lock —
the lock is what stops an on-demand copy from racing the scheduled paper and
delivering a hollow edition to both. Printing the recipe registers nothing
and changes no job.

The one difference: the recipe ends with `NO_REPLY` so the cron's
`--deliver` does not send the transcript. A copy the owner asked for in chat
still ends with `NO_REPLY` — step 2 below already sent them the PDF, and a
transcript after it is the wall of text they did not ask for.

## Render and deliver

1. Run the renderer — it is the only thing that writes the edition. Two
   complete commands; **copy the one that matches and change only the
   paths.** Do not build a third by merging them, and do not add flags
   that are not here:

   No printer configured:

       /var/lib/hermes/skills/pt-edition/scripts/render_edition.py <edition.json> --pdf run/<id>/edition.pdf

   Printer configured:

       /var/lib/hermes/skills/pt-edition/scripts/render_edition.py <edition.json> --pdf run/<id>/edition.pdf --html run/<id>/edition.html

   `--pdf` is in both, always. `--chat PATH` is optional and takes a path
   when used; the chat transcript is not posted, so you normally leave it
   out entirely.

   **Then check that `run/<id>/edition.pdf` actually exists before step 2.**
   If it does not, read the renderer's own stderr and act on which failure
   it was:

   - **A usage error** (`exit_code: 2`, e.g. `argument --chat: expected one
     argument`) means YOUR command was wrong, not that the PDF is
     impossible. Fix the command and re-run it. This is **not** the
     weasyprint fallback and must never be treated as one.
   - **A malformed `edition.json`** is refused by name. Fix the JSON and
     re-run; never hand-assemble a page to route around the gate.
   - **Only** when the renderer's stderr says *weasyprint is not installed*
     is the PDF genuinely impossible — that costs the PDF file alone; take
     the text fallback in step 2 and do not write the edition by hand.

   Measured live: a run built its own argv, passed a bare `--chat` with no
   value (exit 2), then retried having dropped `--pdf` — rendering
   `edition.html` and `edition.chat.txt` and no PDF at all — and posted the
   text. The owner had asked for a copy of the paper and got a wall of
   text, on a machine where weasyprint 62.3 was installed and working.
2. **Send the PDF yourself, by running `post_to_chat.py --pdf`, instead of
   returning the transcript as your final response.** The owner asked for
   the newspaper file, not the file plus the chat dump. `post_to_chat.py`
   with `--pdf` posts an empty body and the attachment — the same envelope
   plow-chat-platform uses for photo-only sends. Do not pipe
   `edition.chat.txt` into it:

       /var/lib/hermes/skills/pt-shared/scripts/post_to_chat.py --pdf run/<id>/edition.pdf --filename The-Plow-Times-<date>.pdf

   Omit `--pdf` **only** when step 1 established that weasyprint is
   genuinely absent — never because your own command failed. In that one
   case the text leg is also a complete command, with no shell redirect:

       /var/lib/hermes/skills/pt-shared/scripts/post_to_chat.py --text-file run/<id>/edition.chat.txt

   Use `--text-file`, never `< file`, never `/bin/sh -c`, never a pipe:
   those are shell operators and SOUL.md's gate flags them, which hands the
   owner an `/approve` prompt instead of their newspaper (measured live,
   on exactly this call). Pointing `--pdf` at a file that does not exist is
   refused by name.
   `PLOW_API_BASE`, `PLOW_HOME_CHANNEL` and `PLOW_AGENT_TOKEN` come from the
   process environment already; nothing to pass for those.

   A successful `--pdf` POST then runs `print_edition.py` itself when
   `printer.configured` is true (sibling `edition.html`, same run dir). Do
   **not** call `pt-print` or `print_edition.py` after this — measured live,
   the model posted the PDF and skipped the print script. A print failure
   prints `page not printed — …` on stdout and still leaves the chat
   edition delivered.

   A successful POST stamps `/var/lib/hermes/skills/pt-shared/scripts/seal_chat_session.py`
   (you do not have to run that script yourself). When this turn ends, the
   gateway starts a **new plow_chat session**. Do not keep researching,
   patching desk JSON, or reading this turn's Latch dumps after the PDF
   is out — the next owner message will not see them anyway.

   **Final response is `NO_REPLY` and nothing else.** Never a recap of
   the desks or headlines — measured live, "Seu jornal foi gerado e
   entregue" plus a bullet list landed after the PDF. The PDF is the
   delivery. The cron job still
   carries `--deliver`, and a final response that is the chat transcript
   would send the text a second time (or as a second message). `NO_REPLY`
   is the token the gateway already treats as silence. Never return the
   renderer’s chat output as the turn’s last line once the PDF has posted.
3. **Record the priority desk** when the edition carried it (its notes say
   `"status": "ok"`), only after the chat leg is out, so tomorrow's follow-up
   never refers to advice that was not delivered:
   `/var/lib/hermes/skills/pt-priority/scripts/history.py record --date <DATE> --notes-json /var/lib/hermes/pt/run/desk-priority/notes.json`
4. **Mark every topic the edition carried** from its `topic_id`:
   `/var/lib/hermes/skills/pt-intake/scripts/topics.py mark <id> --status delivered`. Do this
   only after the chat leg is out — a delivered mark on an undelivered
   edition is how a silent gap looks like a working paper. A section then
   goes back to `pending` for tomorrow's paper. An assignment stays
   `delivered` (terminal).
   - A `topics.py mark` that **refuses because the topic was cancelled while
     the run worked is expected, not an error**: the owner said stop at 6h20;
     the edition already left without it. Report it and carry on — do not
     crash the delivery over a valid cancellation.
   - **Never mark a standing desk.** Weather, calendar, mail and sports
     have no topic id on purpose.

## Repo note — the edition gate

The renderer validates `edition.json` structurally before emitting anything
(the same discipline `pt_config_gate.py` holds for the config): a bad shape
exits non-zero with the failing field named. A run that cannot render says so
and waits for the next cycle — it does not ship a half page.
