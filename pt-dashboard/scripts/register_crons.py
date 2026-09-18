#!/usr/bin/env python3
"""Register the Plow Times' crons, idempotently, from the topic store.

Why this exists at all. `hermes cron` persists jobs to
/var/lib/hermes/cron/jobs.json, which no rebuild replays -- so a rebuilt
agent would come up with subscriptions that never fire and nothing to diff
against. Keeping the spec here, derived from pt/topics.json (the one record
of what the owner asked to be watched), means "set up the plow times crons"
replays a reviewed derivation instead of improvising schedules from a
sentence. The same mechanism ld-dashboard's register_crons.py uses, with a
spec that is data-driven rather than fixed: the topic list changes.

The spec (design doc §3.6 and the personalized-paper plan §3.3/§6):

  pt-daily-edition       <min> <hour> * * *        one job; exists while
                         computed as                setup can register
                         delivery.hour -
                         lead_minutes (owner
                         zone, wraparound
                         exact)
  pt-daily-edition-<n>   same, extra_hours         reprint of the MAIN paper
                         (n ≥ 2)                    (unscoped sections), not
                                                    a different roster
  pt-paper-HHMM          same computation          one job per distinct
                         against a section's        section deliver_at that
                         deliver_at                 is not delivery.hour
  pt-subscription-<id>   0 <delivery.hour> * * *   one per subscription topic
                                                   not yet cancelled
  pt-oneoff-<id>         created by pt-intake at   one-time; its own prompt
                         the scheduled minute      self-removes after firing

This script therefore CREATES missing jobs and REMOVES pt-* jobs whose
topic is gone -- cancelled, delivered one-offs their prompt failed to
remove, or names with no topic behind them. "Created/removed as topics
change", the design doc calls it. It never touches a job whose name does
not start with pt-: those are not this agent's to manage.

It also RECONCILES drift, which create-if-missing alone does not: a job
that is registered with a different schedule, skill or prompt than the spec
calls for (the owner changed delivery.hour, the lead changed, the delivery
contract moved -- PDF-only vs transcript) is removed and recreated. Without
this, "already present, skipped" means a changed delivery hour or a new
chat payload is silently ignored forever -- the exact class of failure this
script exists to prevent. Drift is only judged when hermes's own jobs.json
carries the field; a fixture or an older row without a schedule is left
alone rather than recreated on a guess.

One refusal is the point of the script, inherited from ld-dashboard: an
unreadable or unexpected jobs.json aborts. Never read "I could not tell what
is registered" as "nothing is" -- that re-registers every job and duplicates
all of them.

`delivery.hour` is always the CONTAINER's local time, "HH:MM" -- `hermes
cron create` takes no per-job zone, so every schedule fires in the
container's zone regardless of what `owner.timezone` says. This used to be
enforced by
refusing to register at all unless owner.timezone equalled the container's
TZ (the only way delivery.hour could safely be read as the owner's own local
hour with zero conversion). That traded a real product cost for the safety:
an owner in a different zone than whatever the container happens to be
running in could not get a paper at all without someone restarting the
container first -- mid-conversation, the one thing this agent cannot do for
itself. pt-setup now does the conversion instead: it asks the owner's real
zone and what local time they want, computes the equivalent container-local
hour with `zoneinfo`, and writes THAT as delivery.hour, while owner.timezone
keeps the owner's real zone for display and for recomputing after a
container restart changes TZ. So this script trusts delivery.hour as
already correct for the container it is running in, the same way it always
trusted a hand-edited "changing one setting" update to be correct -- the
conversion risk moved to one write path (pt-setup), not away.

It runs INSIDE the container, where /opt/hermes/bin/hermes and that file
live -- from a turn, which inherits PLOW_HOME_CHANNEL from the gateway.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import date

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "pt-intake", "scripts"),
)

HERMES = "/opt/hermes/bin/hermes"
# Where `hermes cron` persists its jobs -- nothing replays it on a rebuild,
# which is the reason this script exists.
JOBS_FILE = "/var/lib/hermes/cron/jobs.json"
CONFIG_FILE = "/var/lib/hermes/pt/config.json"
# The only job names this spec owns. Pinned as a fullmatch so a name that
# does not parse is never interpreted, and a half-matching id never removes
# a job (see stale_names).
_JOB_NAME_RE = re.compile(r"^pt-(?P<kind>subscription|oneoff)-(?P<tid>t_[0-9a-f]{4})$")
# The one daily-paper job; no topic id because it is the whole paper, not a
# topic. Owned and swept by name, exactly like the id-borne jobs above.
DAILY_NAME = "pt-daily-edition"
# A second (or third, ...) full-paper delivery time, from
# delivery.extra_hours -- same paper, same sections, re-researched and
# re-delivered at another hour of the same day. Numbered from 2 so the
# canonical DAILY_NAME reads as "the" edition and these read as its
# reruns, matching the lock-name convention (daily2-<date>, daily3-<date>)
# a hand-registered job already used before this existed as a real spec.
_EXTRA_DAILY_RE = re.compile(r"^pt-daily-edition-(?P<n>[2-9]\d*)$")
# A focused paper at a section's deliver_at, named from the hour so two
# sections at 12:30 share one job and a dropped hour is sweepable by name.
_PAPER_RE = re.compile(r"^pt-paper-(?P<hhmm>(?:[01]\d|2[0-3])[0-5]\d)$")
_LOCK_RE = re.compile(
    r"^(?:daily\d*|paper-\d{4})-(\d{4}-\d{2}-\d{2})\.lock$"
)
DEFAULT_LEAD_MINUTES = 0

SUBSCRIPTION_PROMPT = (
    "Run pt-research on topic {tid} now (depth deep), then pt-edition for it. "
    "pt-edition writes edition.json, runs render_edition.py, and posts the PDF "
    "only with post_to_chat.py --pdf (empty body, no chat transcript). When "
    "the edition is out, mark the topic delivered with pt-intake's topics.py "
    "and then mark it pending again, so tomorrow's run finds it. Final "
    "response is NO_REPLY so --deliver does not send the text a second time."
)


def daily_prompt(lock_name):
    """The daily paper's run prompt, parametrized by its lock name.

    lock_name is "daily" for the canonical slot and "daily2"/"daily3"/... for
    an extra delivery time (delivery.extra_hours) -- each slot re-researches
    and re-delivers the same paper independently, so each needs its own lock
    or a second slot firing minutes after the first would read the first
    slot's lock as "held" and silently skip the whole edition. It works in
    one cron-fired session: acquire the run lock (two runs racing on the
    SAME slot would deliver a hollow edition), research every active section
    that belongs to the MAIN paper (no deliver_at, or deliver_at equal to
    delivery.hour in pt/config.json — not a section that owns another paper
    hour) and every assignment due today, compile one edition.json, render it,
    deliver. post_to_chat.py runs print_edition.py when a printer is
    configured (best-effort), then release the lock.

    The print leg used to be a separate skill step the model could skip:
    measured live 2026-09-17 Latch saw no `lp`; measured live 2026-09-18
    the PDF posted and print_edition.py was never invoked. It is inside
    post_to_chat.py now.
    """
    return (
        f"Run the daily edition now, in one session. First run "
        f"/var/lib/hermes/skills/pt-shared/scripts/run_lock.py acquire "
        f"--name {lock_name}-<today's date in the owner's "
        f"zone> --stale-minutes 120; if its output is 'held', another run owns "
        f"this slot -- say NO_REPLY and stop. Then "
        f"/var/lib/hermes/skills/pt-intake/scripts/topics.py reopen-sections "
        f"(delivered sections are yesterday's paper, not a skip). Then run pt-research: first "
        f"every standing desk pt-research/references/desks.md lists, in its order, "
        f"then every active news section with no deliver_at (or deliver_at "
        f"equal to delivery.hour in pt/config.json — skip sections that belong "
        f"to another paper hour) and every assignment with run_on <= "
        f"today, writing each topic's notes and desk notes under run/desk-*. "
        f"One plow_browser_open for the whole paper (apex + www + *.host on "
        f"each origin). Never plow_browser_request without origins (Latch "
        f"returns 'needs origins'); never retry a host after NS_ERROR_UNKNOWN_HOST "
        f"or 'Paused for'. "
        f"Then run pt-edition for the batch -- it compiles edition.json from "
        f"those notes (each run/desk-* notes file as its own desk, then news), "
        f"renders it (--pdf, then "
        f"post_to_chat.py --pdf only per pt-edition/SKILL.md step 2 -- do not skip the "
        f"PDF leg just because this is a rerun; do not pipe the chat text). "
        f"post_to_chat.py already runs print_edition.py when printer.configured "
        f"is true (best-effort: a print failure costs only the page, never the "
        f"chat edition, and never re-runs research). Do not invoke pt-print "
        f"yourself. "
        f"Mark every news topic it carried: sections "
        f"delivered then pending, assignments delivered. Do not mark desks. "
        f"Release the lock "
        f"with /var/lib/hermes/skills/pt-shared/scripts/run_lock.py release "
        f"--name the same {lock_name}-<date>. "
        f"Final response is NO_REPLY so --deliver does not send the transcript."
    )


def paper_prompt(lock_name, hour):
    """Run prompt for a focused paper at ``hour`` (a section deliver_at)."""
    return (
        f"Run the {hour} paper now, in one session. First run "
        f"/var/lib/hermes/skills/pt-shared/scripts/run_lock.py acquire "
        f"--name {lock_name}-<today's date in the owner's "
        f"zone> --stale-minutes 120; if its output is 'held', another run owns "
        f"this slot -- say NO_REPLY and stop. Then "
        f"/var/lib/hermes/skills/pt-intake/scripts/topics.py reopen-sections "
        f"(delivered sections are yesterday's paper, not a skip). Then run pt-research: first "
        f"every standing desk pt-research/references/desks.md lists, in its order, "
        f"then ONLY active news sections whose deliver_at is {hour} "
        f"(read topics.json; do not research unscoped sections, sections of "
        f"another hour, or assignments). Write notes under run/<id>/ and "
        f"run/desk-*. One plow_browser_open for the whole paper (apex + www + "
        f"*.host). Never plow_browser_request without origins (needs origins); "
        f"never retry a host after NS_ERROR_UNKNOWN_HOST or 'Paused for'. "
        f"Then run pt-edition for that batch -- desks plus those "
        f"news notes, renders it (--pdf, then post_to_chat.py --pdf only per "
        f"pt-edition/SKILL.md step 2 -- do not pipe the chat text). "
        f"post_to_chat.py already runs print_edition.py when printer.configured "
        f"is true (best-effort: a print failure costs only the page, never the "
        f"chat edition, and never re-runs research). Do not invoke pt-print "
        f"yourself. "
        f"Mark every news topic it carried: sections delivered then pending. "
        f"Do not mark desks. Do not mark assignments. Release the lock "
        f"with /var/lib/hermes/skills/pt-shared/scripts/run_lock.py release "
        f"--name the same {lock_name}-<date>. "
        f"Final response is NO_REPLY so --deliver does not send the transcript."
    )

DELIVER_TARGET = "plow_chat:${PLOW_HOME_CHANNEL}"


def require_timezone_agreement(config_path=CONFIG_FILE, env=None):
    """Refuse to register if the container or the config can't name a zone.

    NOT an owner.timezone == container TZ check anymore (see the module
    docstring) -- pt-setup now converts the owner's stated local delivery
    time into the container's local hour at write time, so delivery.hour is
    trusted as already correct for whatever zone this container is running
    in, the same way a hand-edited "changing one setting" update always was.
    What's still refused: a container with no TZ at all (nothing here could
    even attempt the conversion), and a config missing owner.timezone
    entirely (pt-setup's conversion step needs it, and it's the number shown
    back to the owner). Name kept for the smaller blast radius on callers and
    tests; only its body changed.
    """
    env = os.environ if env is None else env
    container = (env.get("TZ") or "").strip()
    if not container:
        raise SystemExit(
            "refusing to register: TZ is empty in this container. Set TZ "
            "in compose.yml's environment (e.g. America/Sao_Paulo) and "
            "restart -- nothing else here fires without it, and the "
            "schedules would otherwise fire in a zone nothing here can name."
        )
    path = pathlib.Path(config_path)
    try:
        owner = json.loads(path.read_text())["owner"]["timezone"]
    except FileNotFoundError:
        raise SystemExit(
            f"refusing to register: {path} is missing. pt-setup writes it; "
            "its owner.timezone is what every schedule here is written against."
        ) from None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(
            f"refusing to register: could not read owner.timezone from {path} "
            f"({exc!r})."
        ) from exc
    if not str(owner or "").strip():
        raise SystemExit(
            f"refusing to register: {path} has a blank owner.timezone."
        )


def registered_jobs(jobs_path=JOBS_FILE):
    """What is already scheduled, from hermes's own persisted state.

    Reads the file `hermes cron` writes rather than parsing `hermes cron
    list` -- a human rendering nothing pins. Returns {name: is_runnable};
    a paused job is registered but will never fire, and the caller must
    tell those apart (re-registering duplicates it, skipping it silently
    strands it).

    The invariant with teeth: never read "I could not tell what is
    registered" as "nothing is". Only FileNotFoundError means empty -- an
    unreadable or unexpected file raises and stops the run.
    """
    try:
        jobs = json.loads(pathlib.Path(jobs_path).read_text())["jobs"]
    except FileNotFoundError:
        return {}
    return {
        job["name"]: bool(job["enabled"]) and not job["paused_at"]
        for job in jobs
    }


def resolve_deliver(deliver, env=None):
    """Expand every ${VAR} in a delivery target from the container environment.

    The chat uid is whichever chat the owner holds with this agent -- never
    a literal in this repo. First boot publishes PLOW_HOME_CHANNEL; run this
    from a turn, which inherits it from the gateway. Unset or blank REFUSES
    loudly: an empty target is a chat leg that silently delivers nowhere.
    """
    import re

    values = os.environ if env is None else env
    source = "the container environment" if env is None else "the injected env"

    def expand(match):
        name = match.group(1)
        value = (values.get(name) or "").strip()
        if not value:
            raise SystemExit(
                f"refusing to register: deliver target {deliver!r} needs {name}, "
                f"which is unset or blank in {source}. Registering without it "
                "would create a chat leg that silently delivers nowhere."
            )
        return value

    return re.sub(r"\$\{(\w+)\}", expand, deliver)


def load_delivery_hour(config_path=CONFIG_FILE):
    """delivery.hour from pt/config.json -- its exact 'HH:MM' shape is the
    gate's contract; both parts feed the schedule."""
    path = pathlib.Path(config_path)
    try:
        config = json.loads(path.read_text())
        return str(config["delivery"]["hour"])
    except FileNotFoundError:
        raise SystemExit(
            f"refusing to register: {path} is missing -- pt-setup owns it"
        ) from None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"refusing to register: malformed {path} ({exc!r}).") from exc


def load_extra_hours(config_path=CONFIG_FILE):
    """delivery.extra_hours from pt/config.json -- additional full-paper
    delivery times the same day, each "HH:MM" like delivery.hour itself.

    Optional and defaults to empty: an install with one delivery time a day
    (the common case) has no extra_hours key at all, and a schedule that
    refused to compute without it would strand a working agent. The gate
    validates each entry's shape when the key is present; this just reads
    it back, in order (order is the slot numbering -- pt-daily-edition-2 is
    always extra_hours[0]).
    """
    path = pathlib.Path(config_path)
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(
            f"refusing to register: {path} is missing -- pt-setup owns it"
        ) from None
    except (OSError, ValueError) as exc:
        raise SystemExit(f"refusing to register: malformed {path} ({exc!r}).") from exc
    hours = config.get("delivery", {}).get("extra_hours", [])
    if not isinstance(hours, list) or not all(isinstance(h, str) for h in hours):
        raise SystemExit(
            f"refusing to register: {path} has delivery.extra_hours={hours!r}; "
            "it must be a list of \"HH:MM\" strings."
        )
    return hours


def load_lead_minutes(config_path=CONFIG_FILE):
    """delivery.lead_minutes from pt/config.json, defaulting to 0.

    The key is optional on purpose (the gate only validates it when present):
    an install written before the personalized paper existed has no
    lead_minutes, and a schedule that refuses to compute for it would strand
    a working agent. Absent means the default, not an error.
    """
    path = pathlib.Path(config_path)
    try:
        config = json.loads(path.read_text())
        raw = config.get("delivery", {}).get("lead_minutes", DEFAULT_LEAD_MINUTES)
    except FileNotFoundError:
        raise SystemExit(
            f"refusing to register: {path} is missing -- pt-setup owns it"
        ) from None
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        raise SystemExit(f"refusing to register: malformed {path} ({exc!r}).") from exc
    if isinstance(raw, bool) or not isinstance(raw, int) or not (0 <= raw <= 59):
        raise SystemExit(
            f"refusing to register: {path} has delivery.lead_minutes={raw!r}; "
            "it must be an integer 0-59 (minutes before delivery.hour)."
        )
    return raw


def _hour_minute(delivery_hour):
    """Parse a gate-shaped "HH:MM" into (hour, minute) ints."""
    hour_part, minute_part = delivery_hour.split(":")
    return int(hour_part), int(minute_part)


def daily_schedule(delivery_hour, lead_minutes):
    """The daily paper's cron expression, wraparound exact.

    delivery.hour is any real "HH:MM" (the gate's contract). Subtracting the
    lead is done in minutes from the OWNER's chosen minute, not just the
    hour, and taken modulo a day, so 00:00 - 45 min is the PREVIOUS day's
    23:15 and yields "15 23 * * *" -- not "45 -1 * * *", which is not a cron
    expression, and not a schedule that fires a day late. A daily job fires
    at that local minute every day, which is exactly one edition per day at
    the promised moment.
    """
    hour, minute = _hour_minute(delivery_hour)
    total = (hour * 60 + minute - lead_minutes) % (24 * 60)
    return f"{total % 60} {total // 60} * * *"


def has_paper(topics):
    """The daily paper always exists once setup can register crons.

    Weather and calendar desks run even with zero news sections; mail joins
    when configured. Topics only add news blocks. `topics` is unused and
    kept so callers and tests stay the same shape.
    """
    return True


def daily_job(delivery_hour, lead_minutes, env=None, *, name=DAILY_NAME, lock_name="daily"):
    """One full-paper delivery job -- the canonical slot, or an extra one."""
    return {
        "name": name,
        "schedule": daily_schedule(delivery_hour, lead_minutes),
        "prompt": daily_prompt(lock_name),
        "skill": "pt-research",
        "deliver": DELIVER_TARGET,
    }


def paper_job_name(hour):
    """pt-paper-HHMM from a strict HH:MM (12:30 → pt-paper-1230)."""
    hh, mm = hour.split(":")
    return f"pt-paper-{hh}{mm}"


def paper_hour_from_name(name):
    match = _PAPER_RE.fullmatch(name)
    if match is None:
        return None
    hhmm = match.group("hhmm")
    return f"{hhmm[:2]}:{hhmm[2:]}"


def focused_paper_hours(topics, delivery_hour):
    """Distinct section deliver_at values that are not the main paper hour."""
    hours = []
    seen = set()
    for topic in topics:
        if topic.get("kind") != "section" or topic.get("status") == "cancelled":
            continue
        at = topic.get("deliver_at")
        if not at or at == delivery_hour or at in seen:
            continue
        seen.add(at)
        hours.append(at)
    return sorted(hours)


def paper_job(hour, lead_minutes, env=None):
    """One focused paper: desks plus sections whose deliver_at is this hour."""
    name = paper_job_name(hour)
    lock_name = f"paper-{hour.replace(':', '')}"
    return {
        "name": name,
        "schedule": daily_schedule(hour, lead_minutes),
        "prompt": paper_prompt(lock_name, hour),
        "skill": "pt-research",
        "deliver": DELIVER_TARGET,
    }


def subscription_job(topic, delivery_hour, env=None):
    """The job spec for one subscription topic: nightly at the delivery hour."""
    hour, minute = _hour_minute(delivery_hour)
    return {
        "name": f"pt-subscription-{topic['id']}",
        "schedule": f"{minute} {hour} * * *",
        "prompt": SUBSCRIPTION_PROMPT.format(tid=topic["id"]),
        "skill": "pt-research",
        "deliver": DELIVER_TARGET,
    }


def desired_jobs(topics, delivery_hour, env=None, lead_minutes=DEFAULT_LEAD_MINUTES,
                  extra_hours=()):
    """The jobs the topic store calls for, in spec order.

    The daily edition comes first (it is the main paper), then one job per
    extra delivery time (delivery.extra_hours -- the same MAIN roster,
    re-researched later the same day), then one job per distinct section
    deliver_at that is not delivery.hour (a different newspaper), then one
    job per subscription.
    """
    jobs = []
    if has_paper(topics):
        jobs.append(daily_job(delivery_hour, lead_minutes, env))
        for n, hour in enumerate(extra_hours, start=2):
            jobs.append(daily_job(hour, lead_minutes, env,
                                   name=f"{DAILY_NAME}-{n}", lock_name=f"daily{n}"))
        for hour in focused_paper_hours(topics, delivery_hour):
            jobs.append(paper_job(hour, lead_minutes, env))
    jobs.extend(
        subscription_job(t, delivery_hour, env)
        for t in topics
        if t["kind"] == "subscription" and t["status"] != "cancelled"
    )
    return jobs


def stale_names(topics, registered, extra_hours_count=0, delivery_hour=None):
    """Registered pt-* jobs the topic store no longer calls for.

    A subscription job outlives only its non-cancelled topic; a one-off job
    outlives only a topic still pending or running (its prompt self-removes
    it after firing -- this sweep is the backstop, and prunes delivered,
    cancelled or vanished topics' leftovers). The daily job and every
    numbered extra-daily job outlive only a paper that still exists; an extra
    job also goes stale the moment the owner removes that many delivery
    times. A pt-paper-HHMM job outlives only an active section still at that
    hour (and not the main delivery.hour). Names not starting with pt- are
    never ours to remove.
    """
    by_id = {t["id"]: t for t in topics}
    live_papers = set()
    if delivery_hour is not None:
        live_papers = {paper_job_name(h) for h in focused_paper_hours(topics, delivery_hour)}
    stale = []
    for name in registered:
        if name == DAILY_NAME:
            if not has_paper(topics):
                stale.append(name)
            continue
        extra_match = _EXTRA_DAILY_RE.fullmatch(name)
        if extra_match is not None:
            n = int(extra_match.group("n"))
            if n > extra_hours_count + 1:
                stale.append(name)
            continue
        if _PAPER_RE.fullmatch(name):
            if delivery_hour is not None and name not in live_papers:
                stale.append(name)
            continue
        match = _JOB_NAME_RE.fullmatch(name)
        if match is None:
            continue
        kind, tid = match.group("kind"), match.group("tid")
        topic = by_id.get(tid)
        if topic is None:
            stale.append(name)
        elif kind == "subscription" and topic["status"] == "cancelled":
            stale.append(name)
        elif kind == "oneoff" and topic["status"] in ("delivered", "cancelled"):
            stale.append(name)
    return stale


def _persisted_schedule_expr(job):
    """The bare cron expression from a real job's persisted "schedule".

    Measured live against this fleet's own /var/lib/hermes/cron/jobs.json:
    a real registered job's "schedule" is a dict, {"kind": "cron", "expr":
    "15 2 * * *", "display": "15 2 * * *"} -- not the bare string this
    module's own job specs use. Comparing the dict to the spec's string
    directly (job_drift(), before this helper existed) made EVERY managed
    job register as "drifted" on every single run, recreating it every
    time register_crons.py ran -- caught live, not in the test suite, whose
    fixtures had always used a bare string and so never exercised the real
    shape.
    """
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        return schedule.get("expr")
    return schedule


def registered_specs(jobs_path=JOBS_FILE):
    """The registered jobs' own fields, for drift detection.

    registered_jobs() answers only "does it run"; this answers "does it match
    the spec". Only fields hermes actually persisted are returned -- a
    missing key means "unknown", and job_drift() leaves an unknown alone
    rather than recreating on a guess (older rows, and the test fixtures,
    carry no schedule).
    """
    try:
        jobs = json.loads(pathlib.Path(jobs_path).read_text())["jobs"]
    except FileNotFoundError:
        return {}
    return {
        job["name"]: {
            "schedule": _persisted_schedule_expr(job),
            "skill": job.get("skill"),
            "prompt": job.get("prompt"),
            "deliver": job.get("deliver"),
        }
        for job in jobs
    }


def job_drift(job, spec):
    """True when a registered job's persisted fields contradict the spec.

    Only a field that is BOTH persisted and different is a drift; an absent
    field is silence, not a mismatch. Schedule, skill and prompt are the
    fields a spec change actually moves (the delivery hour, the lead, the
    PDF-only vs transcript contract); deliver is not compared because its
    resolved form depends on the turn's environment and a false drift would
    recreate every job on every run.
    """
    for key in ("schedule", "skill", "prompt"):
        stored = spec.get(key)
        if stored is not None and stored != job[key]:
            return True
    return False


def prune_runtime(topics, home):
    """Best-effort housekeeping of the paper's scratch space.

    Removes daily locks older than today (a lock from a day that will never
    fire again) and the notes directory of every terminal topic (delivered
    one-offs and assignments, everything cancelled). Failures are reported,
    never fatal: a stale scratch file is not worth refusing a registration
    over, and the next run prunes again. `home` is the pt state directory.
    """
    run_dir = pathlib.Path(home) / "run"
    if not run_dir.is_dir():
        return []
    removed = []
    today = date.today().isoformat()
    terminal = {
        t["id"] for t in topics
        if t["status"] == "cancelled"
        or (t["kind"] in ("one_off", "assignment") and t["status"] == "delivered")
    }
    for entry in sorted(run_dir.iterdir()):
        try:
            lock_match = _LOCK_RE.fullmatch(entry.name)
            if lock_match is not None:
                stamp = lock_match.group(1)
                if stamp < today:
                    entry.unlink()
                    removed.append(str(entry))
            elif entry.is_dir() and entry.name in terminal:
                shutil.rmtree(entry)
                removed.append(str(entry))
        except OSError as exc:
            print(f"WARNING: could not prune {entry}: {exc!r}")
    return removed


def create_argv(job, env=None):
    argv = [HERMES, "cron", "create", job["schedule"], job["prompt"],
            "--name", job["name"], "--skill", job["skill"]]
    if job["deliver"]:
        argv += ["--deliver", resolve_deliver(job["deliver"], env)]
    return argv


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True)


def main(argv=None, runner=_run, jobs_path=JOBS_FILE, config_path=CONFIG_FILE, env=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Registration itself takes no flags; parse_args(None) on the CLI is
    # sys.argv[1:] == empty, but in-process callers pass [] so argparse never
    # reads the test runner's argv.
    parser.add_argument(
        "--show-daily-recipe", action="store_true",
        help="print the daily edition's run steps and exit, without touching "
             "any job -- the on-demand copy runs exactly this",
    )
    args = parser.parse_args(argv if argv is not None else [])

    # Printed from daily_prompt(), the same function the cron job is built
    # from, so an on-demand copy can never drift from the 7am run. Answered
    # before every precondition below: asking what the steps ARE needs no
    # hermes binary, no config and no topic store, and must stay answerable
    # on a machine where registration itself would refuse.
    if args.show_daily_recipe:
        print(daily_prompt("daily"))
        return 0

    if not shutil.which(HERMES) and not os.path.exists(HERMES):
        raise SystemExit(f"{HERMES} not found -- run this inside the agent container")

    require_timezone_agreement(config_path, env)
    delivery_hour = load_delivery_hour(config_path)
    extra_hours = load_extra_hours(config_path)
    lead_minutes = load_lead_minutes(config_path)

    # The topic store, via pt-intake's single reader -- so a broken
    # topics.json refuses here too, rather than reading as "no topics" and
    # pruning every subscription job this run could have kept.
    import topics as topics_mod
    topics = topics_mod.load_topics()

    for path in prune_runtime(topics, topics_mod.home()):
        print(f"pruned: {path}")

    registered = registered_jobs(jobs_path)
    specs = registered_specs(jobs_path)
    paused = []

    for job in desired_jobs(topics, delivery_hour, env, lead_minutes, extra_hours):
        if job["name"] in registered:
            if not registered[job["name"]]:
                print(
                    f"WARNING: {job['name']} is registered but PAUSED -- it will "
                    "never fire, and this leaves it alone rather than "
                    f"duplicating it. Resume it: {HERMES} cron resume {job['name']}"
                )
                paused.append(job["name"])
                continue
            spec = specs.get(job["name"], {})
            if not job_drift(job, spec):
                print(f"already present, skipped: {job['name']}")
                continue
            proc = runner([HERMES, "cron", "remove", job["name"]])
            if proc.returncode != 0:
                raise SystemExit(
                    f"could not remove drifted job {job['name']}:\n"
                    f"{proc.stdout}\n{proc.stderr}"
                )
            print(
                f"recreating drifted job: {job['name']} "
                f"(was {spec.get('schedule')!r}, now {job['schedule']!r})"
            )
        proc = runner(create_argv(job, env))
        if proc.returncode != 0:
            raise SystemExit(
                f"could not register {job['name']}:\n{proc.stdout}\n{proc.stderr}"
            )
        print(f"registered: {job['name']} ({job['schedule']})")

    for name in stale_names(topics, registered, len(extra_hours), delivery_hour):
        proc = runner([HERMES, "cron", "remove", name])
        if proc.returncode != 0:
            raise SystemExit(
                f"could not remove stale job {name}:\n{proc.stdout}\n{proc.stderr}"
            )
        print(f"removed stale job: {name}")

    if paused:
        raise SystemExit(
            f"registered what was missing, but {len(paused)} job(s) are "
            f"PAUSED and will never fire: {', '.join(paused)} -- "
            f"{HERMES} cron resume <name>"
        )
    return 0


if __name__ == "__main__":
    # sys.argv[1:] explicitly: main(argv=None) parses [] on purpose, so an
    # in-process caller never reads the test runner's argv -- which also means
    # the CLI has to hand its arguments over itself, or no flag can ever be
    # passed from a terminal (measured: --show-daily-recipe was silently
    # ignored and the run fell through to registration).
    sys.exit(main(sys.argv[1:]))