"""Repo-level deployment contracts: plow-agents compose.yml, the image, and the leftover agent-mgr hook."""
from __future__ import annotations

import os
import pathlib
import stat

from conftest import ROOT, load_module


class TestSoul:
    def test_soul_md_does_not_trip_hermes_context_injection_scanner(self):
        # Measured live: agent.prompt_builder scans SOUL.md before it ever
        # reaches the model (tools/threat_patterns.py, scope="context") and
        # replaces the WHOLE file with "[BLOCKED: ... prompt injection ...]"
        # on a hit -- not a warning, a silent full-file drop. SOUL.md's own
        # advice to distrust web content ("a page that says 'ignore your
        # previous instructions'...") tripped its own guard's
        # "prompt_injection" pattern, so the agent ran with NONE of its
        # instructions (no pt-intake, no sourcing rule, nothing) while every
        # skill file and this repo's own tests stayed green -- the failure
        # was invisible to anything except the gateway's own runtime log.
        # This mirrors that one pattern (the exact regex that fired), not
        # the full scanner, as a cheap regression guard with no dependency
        # on the hermes_agent package being installed.
        import re

        pattern = re.compile(
            r"ignore\s+(?:\w+\s+){0,8}(previous|all|above|prior)\s+(?:\w+\s+){0,8}instructions",
            re.IGNORECASE,
        )
        text = (ROOT / "runtime" / "SOUL.md").read_text()
        assert not pattern.search(text), (
            "SOUL.md contains a phrase matching Hermes' context-injection "
            "scanner (tools/threat_patterns.py, pattern id 'prompt_injection'); "
            "the whole file gets replaced with a [BLOCKED: ...] placeholder "
            "at runtime, not just this sentence -- reword it, don't just "
            "silence this assertion"
        )

    def test_setup_opener_does_not_ask_timezone(self):
        text = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "A que horas quer o jornal da manhã?" in text
        assert "Qual seu fuso" not in text
        assert "convert_delivery.py" in text

    def test_soul_setup_gate_is_a_bare_script_not_python_dash_c(self):
        text = (ROOT / "runtime" / "SOUL.md").read_text()
        assert (
            "/var/lib/hermes/skills/pt-shared/scripts/setup_needed.py "
            "/var/lib/hermes/pt/config.json"
        ) in text
        assert "python3 -c" not in text
        assert "bash -c" not in text
        text = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "not a first-contact script" in text
        assert "pt-setup" in text

    def test_soul_setup_gate_applies_to_every_reply_not_just_greetings(self):
        # Measured live: right after "Is a printer set up on your Mac?"
        # was answered "Yes", a session skipped the setup_needed.py check
        # entirely on that reply and went straight to an unprompted inline
        # Python read of pt/config.json (which doesn't exist yet at that
        # point) wrapped in a heredoc -- tripping the dangerous-command
        # gate for a file read nothing asked for.
        text = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "every single reply" in text
        assert "config.json').read_text()" in text
        assert "a reason to reach for inline" in text
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "ad-hoc Python" in setup or "ad-hoc script" in setup

    def test_setup_latch_probe_uses_argv_not_command(self):
        # Latch plow_run_command (tools.ts) requires argv and
        # additionalProperties: false. A "command" key never reaches lpstat.
        text = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert '"command":' not in text
        assert '"argv": ["lpstat", "-p"]' in text
        assert "mcp__plow__plow_run_command" in text

    def test_setup_printer_probe_requests_network_for_cups_ipc(self):
        # Root cause, reproduced directly against Latch's generated profile
        # on a real Mac: lpstat reaches cupsd over a local Unix domain
        # socket, and the seatbelt profile grants network*/system-socket
        # only when `network` is true. Without the flag CUPS cannot open
        # the socket to its own scheduler and libcups reports "Bad file
        # descriptor". Deterministic, not flaky: 25/25 pass with the flag,
        # 10/10 fail without it, and a plain shell outside Latch always
        # passes. `network: true` is the workaround from this side (the
        # scoped fix belongs in Latch's own sandbox profile, not here).
        text = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert '"network": true' in text
        assert "Bad file descriptor" in text
        # The flag covers local IPC, not just remote access — the whole
        # reason this looked like a CUPS fault for so long.
        assert "local IPC" in text

    def test_setup_printer_probe_falls_back_to_plow_run_applescript(self):
        # Root cause, measured three runs back to back on the owner's Mac:
        # cupsd is launchd-on-demand, and a SANDBOXED lpstat cannot trigger
        # the rendezvous that starts it. cupsd asleep + sandbox => "Bad file
        # descriptor", and it stays asleep; unsandboxed => works AND starts
        # it; sandboxed immediately after => works. That is the whole
        # "intermittent" story, and Latch's audit log shows it directly:
        # same argv, same "Network: allowed", exit 0 at 01:00 and exit 1 at
        # 01:12. So network:true is necessary but NOT sufficient, and the
        # retry must go through plow_run_applescript -- the tool that really
        # runs outside the sandbox -- which also wakes cupsd for later runs.
        text = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "plow_run_applescript" in text
        assert '"app": "System Events"' in text
        assert "necessary but NOT sufficient" in text
        assert "launchd" in text

    def test_setup_printer_probe_never_runs_osascript_via_run_command(self):
        # The retry that could only ever fail: osascript handed to
        # plow_run_command is an ordinary process.exec intent and runs under
        # sandbox-exec, so it inherited the identical denial and reproduced
        # the identical error one layer down. Inside the printer probe it may
        # appear ONLY as the documented warning, never as an instruction.
        text = (ROOT / "pt-setup" / "SKILL.md").read_text()
        probe = text[text.index('"argv": ["lpstat", "-p"]'):text.index("record_setup.py /var/lib/hermes/pt/config.json printer.configured=true")]
        assert probe.count('["osascript"') == 1, "osascript appears in the probe other than as the warning"
        assert probe.index("Do not") < probe.index('["osascript"')

    def test_pt_shared_documents_every_script_it_ships(self):
        # Measured live, at the news-desk step: a session ran
        # `python3 -c "...record_setup.py').read_text()"` -- reading a flow
        # script's OWN SOURCE to work out how to call it -- and handed the
        # owner an /approve prompt instead of the next question. Root cause:
        # record_setup.py was the one script in pt-shared/scripts absent from
        # pt-shared/SKILL.md's inventory, and it is the most-invoked script
        # in the setup flow. An interface nobody documents is one a run will
        # go read. Every script in the directory must carry a bullet.
        listed = (ROOT / "pt-shared" / "SKILL.md").read_text()
        shipped = sorted(p.name for p in (ROOT / "pt-shared" / "scripts").glob("*.py"))
        assert shipped, "no scripts found -- path wrong, test is vacuous"
        missing = [n for n in shipped if n not in listed]
        assert not missing, f"undocumented pt-shared scripts: {missing}"

    def test_soul_forbids_reading_flow_script_source(self):
        # The guard used to cover wrapping an invocation and reading
        # config.json, but never "read the script to learn its interface" --
        # the one variant with an actual motive behind it.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "own source" in soul
        assert "Never open one of these scripts." in soul
        # And it must point at where the contract actually lives.
        assert "pt-shared" in soul

    def test_language_is_a_recorded_fact_not_a_prose_reminder(self):
        # Four live drifts: three failure explanations and one printer
        # SUCCESS reply, the last in Dutch, all in interviews written wholly
        # in English. Each drift was answered by attaching a reminder to that
        # branch -- and the next drift arrived on a branch without one. The
        # gate already runs as the first action of every reply, so the
        # recorded language rides back on every one of them.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "owner.language=" in setup, "the interview must record the language"
        assert "LANG:unrecorded" in setup
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "LANG:" in soul
        # And the gate must actually emit it.
        gate = (ROOT / "pt-shared" / "scripts" / "setup_needed.py").read_text()
        assert "def language_line" in gate
        assert "LANG:" in gate
        # ...and it must survive into the config a scheduled edition reads.
        assert '"language"' in (ROOT / "pt-setup" / "scripts" / "finalize_setup.py").read_text()

    def test_on_demand_copy_is_routed_and_not_filed_as_a_topic(self):
        # Measured live: "generate a copy for me to read right now" had no
        # route -- pt-intake's five rows are all "a new subject to research"
        # -- so it became a one_off topic reading "A current copy of my daily
        # newspaper" and the research pass went looking for that phrase on the
        # web. The paper came back with the standing desks and a news block
        # saying "No separate news desk in this quick pass", while 48 saved
        # sections went unread: a one-off edition carries only its own topic.
        intake = (ROOT / "pt-intake" / "SKILL.md").read_text()
        assert "not a topic" in intake, "the on-demand row is missing from the routing table"
        edition = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "## On demand" in edition
        # It must POINT at the cron's own recipe, never restate it: a second
        # copy of those steps is a second thing to keep in sync.
        assert "--show-daily-recipe" in edition
        crons = (ROOT / "pt-dashboard" / "scripts" / "register_crons.py").read_text()
        assert '"--show-daily-recipe"' in crons

    def test_render_step_gives_complete_commands_not_a_merge(self):
        # Measured live: the render step showed ONE command plus a comment
        # ("# add --html PATH too when a printer is configured"), so a run
        # with a printer had to assemble its own argv -- and lost --pdf while
        # inventing a valueless --chat (exit 2). It rendered edition.html and
        # edition.chat.txt, no PDF, and posted text. weasyprint 62.3 was
        # installed and working on that machine.
        text = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "# add --html PATH too" not in text, "the merge-a-comment form is back"
        render = [
            line.strip()
            for line in text.splitlines()
            if "render_edition.py" in line and line.startswith(" " * 7)
        ]
        assert len(render) >= 2, "both the printer and no-printer commands must be spelled out"
        for line in render:
            assert "--pdf" in line, f"a render command without --pdf: {line}"

    def test_pdf_fallback_is_keyed_on_weasyprint_not_on_any_failure(self):
        # The fallback used to fire whenever "render_edition.py produced no
        # PDF", which a usage error satisfies -- so a typo silently demoted
        # the owner to plain text, permanently.
        import re

        text = (ROOT / "pt-edition" / "SKILL.md").read_text()
        flat = re.sub(r"\s+", " ", text.replace("*", ""))
        assert "not the weasyprint fallback" in flat
        assert "exit_code: 2" in flat

    def test_text_leg_needs_no_shell_redirect(self):
        # /bin/sh -c '... < edition.chat.txt' tripped the dangerous-command
        # gate. A flag needs no shell.
        text = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "--text-file" in text
        script = (ROOT / "pt-shared" / "scripts" / "post_to_chat.py").read_text()
        assert '"--text-file"' in script

    def test_edition_post_seals_the_owner_chat_session(self):
        # Measured live: one plow_chat DM since 14/09 carried 150k tokens
        # of Latch dumps into the next "gera um jornal", and Kimi spent
        # the turn hand-patching desk JSON. post_to_chat stamps; the
        # gateway pin rotates the session on agent:end.
        script = (ROOT / "pt-shared" / "scripts" / "post_to_chat.py").read_text()
        assert "after_posted" in script
        assert "seal_chat_session" in script
        assert "maybe_print" in script
        assert "print_edition.py" in script
        edition = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "print_edition.py" in edition
        assert "call `pt-print`" in edition

        seal = ROOT / "pt-shared" / "scripts" / "seal_chat_session.py"
        assert seal.is_file()
        import os
        assert os.access(seal, os.X_OK)
        edition = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "seal_chat_session.py" in edition or "after_posted" in edition or "new session" in edition.lower()
        dockerfile = (ROOT / "Dockerfile").read_text()
        assert "patch_seal_session.py" in dockerfile
        assert "plow_seal_session.py" in dockerfile
        assert "/opt/hermes/gateway/run_turn.py" in dockerfile
        assert "/opt/hermes/gateway/response_filters.py" in dockerfile
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "seal_chat_session.py" in soul or "next chat is a new session" in soul



    def test_close_step_names_a_command_for_writing_the_config(self):
        # Measured live: step 3 said "**Write** config.json from the draft"
        # and named no tool, and nothing in the tree wrote that file. A run
        # with every field it needed ran the gate against a file nobody had
        # created, got "not valid JSON" (what the gate says for a MISSING
        # file) and told the owner the setup hit a configuration error.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "finalize_setup.py" in setup
        assert "--owner-tz" in setup
        # The bare, un-actioned instruction must not come back.
        assert "**Write** `/var/lib/hermes/pt/config.json` from the draft" not in setup
        assert (ROOT / "pt-setup" / "scripts" / "finalize_setup.py").exists()

    def test_close_step_names_a_command_for_clearing_the_draft(self):
        # Measured live: the close step said "delete .setup-draft.json" and
        # named no command, so a run reached for an inline -c one-liner
        # calling os.remove and tripped the dangerous-command gate in front
        # of the owner -- with the newspaper otherwise finished. An
        # instruction with no affordance is the bug; the script that owns the
        # draft owns deleting it too.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "--done" in setup
        assert "os.remove" in setup, "the failure mode must stay named"
        # The bare, un-actioned instruction must not come back.
        assert "and delete `.setup-draft.json`." not in setup
        shared = (ROOT / "pt-shared" / "SKILL.md").read_text()
        assert "--done" in shared

    def test_soul_generalizes_the_missing_affordance_rule(self):
        # Two variants of one class (read a script's source; delete a file
        # with an interpreter). The guard must state the class, not just
        # enumerate the instances.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "names no command" in soul
        assert "record_setup.py" in soul and "--done" in soul

    def test_no_skill_prefixes_an_interpreter_or_splits_a_command(self):
        # SOUL.md says "do not prefix an interpreter", and every one of these
        # scripts is executable with a shebang -- yet six SKILL.md examples
        # across four skills opened with `python3 ` and wrapped onto a second
        # line with a backslash. Measured live: given that shape, a run
        # reached for execute_code to run convert_delivery.py and tripped the
        # dangerous-command gate. An example that contradicts the rule is the
        # bug; the rule is right.
        for path in sorted(ROOT.glob("pt-*/SKILL.md")):
            text = path.read_text()
            assert "python3 /var/lib/hermes" not in text, f"interpreter prefix in {path.name}"
            for line in text.splitlines():
                if "/var/lib/hermes/skills/" in line and line.rstrip().endswith("\\"):
                    raise AssertionError(f"split script invocation in {path.name}: {line.strip()}")

    def test_every_bare_invoked_script_is_executable(self):
        # The SKILL.md examples name scripts by absolute path with no
        # interpreter, so each one must be executable and carry a shebang --
        # otherwise the documented command simply fails. render_edition.py was
        # mode 0644 when its `python3 ` prefix was removed, and only the
        # Dockerfile's `-perm -u+x` chmod would have carried the bit through.
        import re

        seen = set()
        for path in sorted(ROOT.glob("pt-*/SKILL.md")):
            for match in re.finditer(r"/var/lib/hermes/skills/(pt-[\w-]+/scripts/[\w.]+\.py)", path.read_text()):
                seen.add(match.group(1))
        assert seen, "no script invocations found -- regex is wrong, test is vacuous"
        for rel in sorted(seen):
            script = ROOT / rel
            assert script.exists(), f"{rel} is invoked but not in the tree"
            assert script.read_text().startswith("#!"), f"{rel} has no shebang"
            import os

            assert os.access(script, os.X_OK), f"{rel} is invoked bare but is not executable"

    def test_shebang_entry_scripts_are_executable_even_if_only_the_recipe_names_them(self):
        # Measured live 2026-09-17: an on-demand "exemplar impresso agora"
        # never started research. The daily recipe says "run pt-shared's
        # run_lock.py" (no interpreter). That file was 0644; bash returned
        # Permission denied (126). The model then opened the source and
        # wrapped python3, which tripped Hermes' /approve gate in a loop.
        # SKILL.md-only scanning misses this: the lock lives in
        # register_crons.py's printed recipe, not in a SKILL.md example.
        skip = {"bearer_http.py", "sudoku.py"}  # imported, never invoked bare
        missing = []
        for path in sorted(ROOT.glob("pt-*/scripts/*.py")):
            if path.name in skip:
                continue
            if not path.read_text().startswith("#!"):
                continue
            if not os.access(path, os.X_OK):
                missing.append(str(path.relative_to(ROOT)))
        assert not missing, (
            "shebang entry scripts must be executable; on-demand paper "
            f"stops at Permission denied otherwise: {missing}"
        )

    def test_soul_forbids_execute_code_for_flow_commands(self):
        # execute_code was the one route the guard never named: it enumerated
        # -c, heredocs, shells, ||, &&, ;, printf -- so the run picked the
        # door that wasn't on the list.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "execute_code" in soul
        assert "shebang" in soul

    def test_research_web_is_latch_browser_only(self):
        # Measured live, 2026-09-17: an on-demand paper opened Latch for
        # the priority file, then spent ~70 tool turns on Hermes
        # web_extract / Firecrawl / Exa / Keenable / Parallel against
        # ESPN and F1 from the container. Those calls never hit the
        # owner's Mac. The paper's web is Latch's browser or it is not
        # sourced -- including sports JSON that desks.md used to call a
        # "plain HTTP fetch" that "does not compete for the browser pass".
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        research = (ROOT / "pt-research" / "SKILL.md").read_text()
        desks = (ROOT / "pt-research" / "references" / "desks.md").read_text()
        for text in (soul, research):
            assert "plow_browser_" in text
            assert "web_extract" in text
            assert "Firecrawl" in text
            assert "Exa" in text
            assert "Keenable" in text
            assert "Parallel" in text
        assert "plain HTTP fetch" not in desks
        assert "does not compete for the browser pass" not in desks
        assert "plow_run_command can fetch this" not in desks
        assert "plow_browser" in desks
        assert "site.api.espn.com" in desks

    def test_research_one_browser_session_does_not_retry_origin_errors(self):
        # Measured live 2026-09-18: an on-demand paper spent ~30 minutes.
        # ipapi.co NS_ERROR_UNKNOWN_HOST every run; then plow_browser_request
        # with no origins ("needs origins and/or credential_items"); then
        # goto techcrunch.com while only *.techcrunch.com was allowlisted;
        # then MCP "Paused for ~44s" and the same call again. The contract:
        # one open for the whole paper, apex+wildcard together, fail once.
        research = (ROOT / "pt-research" / "SKILL.md").read_text()
        desks = (ROOT / "pt-research" / "references" / "desks.md").read_text()
        assert "needs origins" in research
        assert "apex" in research and "*.example.com" in research
        assert "Paused" in research
        assert "do not close" in desks or "Do not close" in desks
        assert "do not retry ipapi" in desks or "never retry ipapi" in desks
        assert "reopen-sections" in research

    def test_setup_warns_against_wrapping_record_setup_in_python(self):
        # Measured live: with a real printer found (network:true worked),
        # the assistant recorded a perfectly valid printer name by
        # wrapping record_setup.py in `python3 - <<'PY' ... PY` for no
        # technical reason -- there was nothing in the value that needed
        # it -- and Hermes correctly flagged it as dangerous script
        # execution, handing the owner a raw /approve prompt instead of
        # an answer. Both files must say plainly that a dotted/underscored
        # *value* never requires any wrapping.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "python3 - <<'PY'" in soul
        assert "wrap this in" in setup
        assert "taken verbatim" in setup

    def test_setup_reads_location_through_the_browser_not_run_command(self):
        # Measured live: /usr/bin/python3 (via xcrun) and a curl fallback
        # both failed under plow_run_command's sandbox -- xcrun's own dylib
        # blocked by the file-read allowlist, then DNS resolution blocked
        # even with network:true. plow_browser_* is a different code path
        # (a real, unsandboxed browser on the owner's Mac) and hits
        # neither restriction.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        desks = (ROOT / "pt-research" / "references" / "desks.md").read_text()
        for text in (setup, desks):
            assert "plow_browser_open" in text
            assert "plow_browser_close" in text
        assert "xcrun" in desks
        assert "Could not resolve host" in desks
        assert '"/usr/bin/python3"' not in setup

    def test_setup_location_lookup_falls_back_past_a_dead_domain(self):
        # Measured live: even through plow_browser_*, ipapi.co alone came
        # back NS_ERROR_UNKNOWN_HOST on one owner's Mac -- a dead domain,
        # not a sandbox gap. The procedure must try other providers, not
        # give up (or retry the same host) after one goto error.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        desks = (ROOT / "pt-research" / "references" / "desks.md").read_text()
        for text in (setup, desks):
            assert "ipapi.co" in text
            assert "ipwho.is" in text
            assert "ifconfig.co" in text
            assert "NS_ERROR_UNKNOWN_HOST" in text

    def test_soul_warns_failure_replies_still_match_owner_language(self):
        # Measured live, three times now: an all-English interview got a
        # Portuguese reply anyway -- twice in plain-text failure messages,
        # once inside a `clarify` tool call's question text. The rule must
        # cover tool-produced owner-facing strings, not just plain text.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "Measured live, three times" in soul
        assert "flipped exactly on the one turn" in soul or "failure explanation" in soul
        assert "clarify" in soul

    def test_setup_close_step_forbids_asking_the_owner_for_a_city(self):
        # Measured live: on reaching NEXT_QUESTION=close, a run skipped
        # straight past plow_browser_open and used the `clarify` tool to
        # ask the owner what city they're in -- exactly what desks.md
        # already forbids. It also wandered through five unrelated skills
        # first. The close section needs its own explicit guard, not just
        # a cross-reference to desks.md's rule.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        close = setup.split("## Close:", 1)[1]
        assert "clarify" in close
        assert "Em que cidade" in close or "do only the three numbered" in close

    def test_setup_never_narrates_its_own_step_classification(self):
        # Measured live, TWICE: a bare "Oi" got back a paragraph classifying
        # the message and naming the step number, in English, stacked in
        # front of the actual Portuguese opener. Told to stop, the second
        # "Oi" got a reworded version of the identical violation -- proof
        # the fix has to be a mechanical check (first character of the
        # reply must be the opener's own first character), not a sentence
        # to avoid repeating.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "and only that message" in setup
        assert "DRAFT:none. This is step 1a" in setup
        assert "This is a bare greeting 'Oi' with DRAFT:none" in setup
        assert "reply's very first character is the opener's own first character" in setup
        assert "nothing else — never" in soul
        assert "your own reasoning about which step" in soul
        assert "reworded version of the same thing" in soul
        assert "reworded" in setup
        assert "first character must be the real answer's own" in soul

    def test_soul_reapplies_language_and_silence_rules_after_setup_is_ready(self):
        # Measured live: a whole setup interview ran correctly in Portuguese,
        # then the very next request -- "send me a paper now", answered live
        # with the owner watching -- narrated its entire research and print
        # run in English. LANG: only prints while SETUP_NEEDED; READY gave
        # no reminder to keep checking owner.language, and no skill outside
        # pt-setup had ever been told to stay silent between tool calls.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "gives you no such" in soul
        assert "silent between them" in soul
        assert "--show-daily-recipe" in soul

    def test_research_and_edition_run_silently_even_live(self):
        # Same measured incident: pt-research and pt-edition were written
        # assuming a cron-fired session with nobody watching, but an
        # on-demand "send me a paper now" runs the identical recipe live in
        # chat. Both must say explicitly that tool calls produce no
        # owner-facing narration, live or cron-fired alike.
        research = (ROOT / "pt-research" / "SKILL.md").read_text()
        edition = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "Run silently" in research
        assert "no text between tool calls" in research
        assert "happen silently" in edition
        assert "PDF rendered successfully" in edition

    def test_print_skill_uses_a_container_path_for_render_not_a_mac_path(self):
        # Measured live: pt-print's own render step told the model to pass
        # `~/Plow/...` (a Mac path, Latch's convention) as an argument to
        # render_edition.py, which runs INSIDE THE CONTAINER -- `~` there
        # resolves to nothing meaningful on the owner's Mac. The render
        # step must target a container path; ~/Plow only means something
        # inside the actual Latch write call afterward.
        text = (ROOT / "pt-print" / "SKILL.md").read_text()
        render_step = text[text.index("## Render the HTML"):text.index("## Ship it through Latch")]
        assert "--html /var/lib/hermes" in render_step
        assert "never an argument to a" in render_step

    def test_print_skill_ships_html_through_print_edition_not_the_model(self):
        # Measured live 2026-09-17: the model cat'd edition.html (~43k) then
        # tried to paste it into plow_write_file's content. The LLM stream
        # died (RemoteProtocolError / incomplete chunked read) twice; lp
        # never ran. Chat still worked because post_to_chat.py reads the
        # PDF from disk. Print must be the same shape: one bare script,
        # HTML stays in the file, never in a tool-call argument.
        text = (ROOT / "pt-print" / "SKILL.md").read_text()
        assert "Do not run this skill from the live turn" in text
        assert (
            "/var/lib/hermes/skills/pt-print/scripts/print_edition.py"
        ) in text
        ship = text[text.index("## Ship it through Latch"):]
        assert "one `cat`, once" not in ship
        assert "content=<the HTML>" not in ship
        assert "plow_write_file" not in ship
        assert "Every step below runs silently" in text
        script = ROOT / "pt-print" / "scripts" / "print_edition.py"
        assert script.is_file()
        assert script.read_text().startswith("#!")
        import os
        assert os.access(script, os.X_OK)

    def test_on_demand_paper_warns_the_owner_it_takes_a_few_minutes(self):
        # Measured live: a live on-demand turn posted every research
        # decision into chat, then attached edition.pdf. The wait line is
        # chat_status.py --soon (a POST, not a sentence the model types),
        # plus one --wait if the pass is still running.
        intake = (ROOT / "pt-intake" / "SKILL.md").read_text()
        research = (ROOT / "pt-research" / "SKILL.md").read_text()
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        edition = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "chat_status.py --soon" in intake
        assert "chat_status.py --wait" in research
        assert "chat_status.py --soon" in soul
        assert "interim_assistant_messages: false" in soul
        assert "The-Plow-Times-" in edition
        assert "--filename" in edition
        script = ROOT / "pt-shared" / "scripts" / "chat_status.py"
        assert script.is_file()
        assert script.read_text().startswith("#!")
        import os
        assert os.access(script, os.X_OK)

    def test_setup_treats_yes_as_the_default_hour(self):
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "send its opener" not in soul
        # SOUL.md delegates to pt-setup's own NEXT_QUESTION-driven steps
        # rather than duplicating the "yes"/07:00 acceptance list itself —
        # two descriptions of the same rule is how they drifted apart
        # before. pt-setup/SKILL.md is the one place that rule lives.
        assert "record_setup.py" in soul and "NEXT_QUESTION" in soul
        assert '"yes"' in setup and '"sim"' in setup
        assert "local_hour=07:00" in setup

    def test_setup_writes_the_draft_only_through_record_setup(self):
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        # The bug this guards: a session once hand-wrote .setup-draft.json
        # with a plain write_file call, then probed the printer and asked
        # about mail in that same reply, without the owner ever seeing the
        # printer question or the probe's answer ever landing in the
        # draft. record_setup.py is the only sanctioned writer now.
        assert "never a hand-edited" in setup
        assert "record_setup.py" in setup
        assert "NEXT_QUESTION" in setup
        for field in ("printer.configured", "mail.configured", "news_asked"):
            assert field in setup

    def test_soul_does_not_gate_the_hour_answer_behind_draft_none(self):
        # The bug this guards: the owner answered "7 is fine" while the
        # draft was still DRAFT:none (nothing had been recorded yet), and
        # SOUL.md's own DRAFT:none branch said "send the opener, stop" --
        # so the assistant re-sent the exact same hour question instead of
        # recording the answer it had just been given. SOUL.md must always
        # hand off to pt-setup (whose own step 1b recognizes an hour
        # answer) rather than deciding straight from DRAFT:none itself.
        soul = (ROOT / "runtime" / "SOUL.md").read_text()
        assert "always load" in soul and "pt-setup" in soul
        assert "never decide" in soul.lower() or "not mean the incoming message" in soul

    def test_setup_distinguishes_a_probe_error_from_no_printer(self):
        # The bug this guards: lpstat -p came back exit_code=1 with
        # "lpstat: Bad file descriptor" -- a probe execution error, not a
        # real "no destinations" report -- and the assistant told the
        # owner "no printer was found" as if the check had actually run
        # cleanly. printer.configured still becomes false either way (never
        # guess true), but the two situations are not the same claim.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "Bad file descriptor" in setup
        assert "didn't run cleanly" in setup or "isn't a real lpstat report" in setup

    def test_setup_says_probe_outcomes_in_the_owners_language(self):
        # The bug this guards: after the printer probe, the assistant
        # replied in Portuguese even though the entire conversation (every
        # prior owner message) had been in English.
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert setup.count("owner's own language") >= 2


class TestUserStub:
    def test_runtime_user_md_forbids_a_profile_interview(self):
        text = (ROOT / "runtime" / "USER.md").read_text()
        assert "not a personal profile" in text.lower()
        assert "pt-setup" in text

    def test_deploy_hook_publishes_user_md(self):
        hook = (ROOT / "deploy-hook").read_text()
        assert "runtime/USER.md" in hook
        assert "memories/USER.md" in hook


class TestSkills:
    def test_every_pt_dir_carries_a_skill_manifest(self):
        for d in sorted(ROOT.glob("pt-*")):
            if not d.is_dir():
                continue
            skill = d / "SKILL.md"
            assert skill.is_file(), f"{d.name} has no SKILL.md"
            head = skill.read_text()
            assert head.startswith("---"), f"{d.name}/SKILL.md has no frontmatter"
            assert f"name: {d.name}" in head, f"{d.name}/SKILL.md frontmatter name mismatch"

    def test_setup_asks_about_the_priority_file(self):
        text = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert "NEXT_QUESTION=priority" in text
        assert "never overwrite an existing file" in text.lower()
        assert "prioritization.template.md" in text

    def test_priority_desk_is_documented_and_wired(self):
        desks = (ROOT / "pt-research" / "references" / "desks.md").read_text()
        assert "## 5. Priority" in desks
        assert "run/desk-calendar/events.json" in desks
        skill = (ROOT / "pt-priority" / "SKILL.md").read_text()
        assert "run/desk-priority/notes.json" in skill
        assert "never infer a stage" not in desks
        edition = (ROOT / "pt-edition" / "SKILL.md").read_text()
        assert "history.py record" in edition

    def test_shared_helpers_exist_and_are_referenced(self):
        shared = ROOT / "pt-shared" / "scripts"
        for name in ("pt_config_gate.py", "post_to_chat.py", "bearer_http.py",
                     "run_lock.py", "setup_needed.py", "record_setup.py",
                     "seal_chat_session.py"):
            assert (shared / name).is_file(), f"pt-shared/scripts/{name} missing"

    def test_record_setup_is_executable_and_referenced(self):
        script = ROOT / "pt-shared" / "scripts" / "record_setup.py"
        assert script.stat().st_mode & stat.S_IXUSR, "record_setup.py must be executable"
        setup = (ROOT / "pt-setup" / "SKILL.md").read_text()
        assert (
            "/var/lib/hermes/skills/pt-shared/scripts/record_setup.py"
        ) in setup

    def test_edition_renderer_and_template_exist(self):
        edition = ROOT / "pt-edition"
        assert (edition / "scripts" / "render_edition.py").is_file()
        assert (edition / "template.html").is_file()

    def test_template_carries_no_script(self):
        # The Chrome-on-Mac PDF fallback executes JavaScript; the template
        # must stay inert, and the renderer is the only writer of markup.
        template = (ROOT / "pt-edition" / "template.html").read_text()
        assert "<script" not in template.lower()
        assert "onload=" not in template.lower()

    def test_template_keeps_every_slot_the_renderer_fills(self):
        # A restyle that drops a placeholder silently drops that desk from
        # the page. The renderer fills these; the template must keep them.
        template = (ROOT / "pt-edition" / "template.html").read_text()
        for slot in ("MASTHEAD", "DATE", "LOCATION", "LEAD", "PRIORITY_BLOCK",
                     "WEATHER_EAR", "DESKS_INLINE", "SECTIONS", "SUDOKU"):
            assert "{{" + slot + "}}" in template, f"template lost {{{{{slot}}}}}"

    def test_template_has_a_newspaper_front_page(self):
        # Measured live 2026-09-18: the page read as a newsletter, not a
        # newspaper. The reference is a broadsheet front page: nameplate
        # with a double rule, a folio line, the lead as a large headline,
        # and news in columns.
        template = (ROOT / "pt-edition" / "template.html").read_text()
        assert "nameplate" in template
        assert "rule-double" in template
        assert "folio" in template
        assert "columns" in template or "column-count" in template
        assert "dropcap" in template
        assert "border-image" not in template  # no fake photo frames
        assert "masthead-row" in template
        assert "ear-box" in template
        assert "news-col" in template
        # The priority card's heading is model-written (owner.language),
        # not a hardcoded English/Portuguese string.
        assert "What should I prioritize today?" not in template
        assert "O que devo priorizar hoje?" not in template
        assert "PRIORITY_BLOCK" in template
        # Broadsheet anatomy: kickers label each story's section, the
        # lead's body runs in columns, desks are a boxed teaser row.
        assert "kicker" in template
        assert "lead-body" in template
        assert "desks-row" in template
        # Never display:none an element that gets a background from
        # another rule -- WeasyPrint 62.3 paints the background anyway
        # (measured: an empty black stripe where the "hidden" h2 was).
        assert "display: none" not in template

    def test_cross_skill_imports_resolve(self):
        # register_crons.py imports topics from pt-intake/scripts at run time;
        # both must be seeded side by side for that to work.
        assert (ROOT / "pt-intake" / "scripts" / "topics.py").is_file()
        assert (ROOT / "pt-dashboard" / "scripts" / "register_crons.py").is_file()
        assert (ROOT / "pt-setup" / "scripts" / "convert_delivery.py").is_file()


class TestDeployment:
    def test_deploy_hook_is_executable(self):
        mode = (ROOT / "deploy-hook").stat().st_mode
        assert mode & stat.S_IXUSR, "deploy-hook must be executable"

    def test_agent_env_declares_hook_and_config(self):
        env = (ROOT / "agent.env").read_text()
        assert "AGENT_DEPLOY_HOOK=deploy-hook" in env
        assert "AGENT_CONFIG=runtime/config.yaml" in env

    def test_skills_tsv_is_empty(self):
        # skills.tsv pins SHARED skills from other repos; this agent installs
        # no connectors -- Latch is the only mcp_server. Empty means exactly
        # that, and any row would be a credential-carrying dependency to review.
        content = (ROOT / "skills.tsv").read_text().strip()
        assert content == ""

    def test_config_declares_latch_and_chat_only(self):
        config = (ROOT / "runtime" / "config.yaml").read_text()
        assert "plow-chat-platform" in config
        assert "https://api.plow.co/v1/relay/devices/" in config
        # The credential is interpolated from the dotenv, never a literal.
        assert "DOMO_MCP_TOKEN" in config and "DOMO_DEVICE_UID" in config
        # Hard gate: Hermes web_extract / web_search / Playwright stay off.
        assert "disabled_toolsets" in config
        assert "\n    - web\n" in config
        assert "\n    - search\n" in config
        assert "\n    - browser\n" in config
        # Hard gate: plow_chat must not stream tool progress or mid-turn
        # assistant narration (Hermes default is both on for this platform).
        assert "interim_assistant_messages: false" in config
        assert "tool_progress: off" in config
        assert "long_running_notifications: false" in config
        assert "moonshotai/kimi-k2.5" in config
        assert "default: moonshotai/kimi-k2.5" in config
        assert "moonshotai/kimi-k2.5: {}" in config

    def test_compose_yml_is_the_plow_agents_surface(self):
        # plow-agents' compose.example.yml: service `agent`, credential drop-in,
        # named home volume. compose.override.yml must not exist: Compose loads
        # that filename automatically and would start a second gateway.
        import re

        assert not (ROOT / "compose.override.yml").exists()
        text = (ROOT / "compose.yml").read_text()
        assert re.search(r"^  agent:", text, re.M)
        assert "build: ." in text
        assert "./plow-credentials:/var/lib/plow/credentials.host:ro" in text
        assert "agent-home:/var/lib/hermes" in text
        assert "AGENT_ID: theplowtimes" in text
        assert "TERMINAL_CWD: /var/lib/hermes" in text
        assert "stop_grace_period: 35s" in text
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("-") and "skills" in stripped and "agent-home" not in stripped:
                raise AssertionError(f"skill mount in compose.yml: {stripped}")

    def test_compose_yml_does_not_pin_a_model(self):
        # Measured live: google/gemini-2.5-flash-lite never once called
        # skills_list/skill_view for a news request. Unpinned, provider/model
        # fall back to the Plow-hosted default, the same choice
        # life-assistant-hermes-agent's compose.yml makes by omission.
        text = (ROOT / "compose.yml").read_text()
        assert "HERMES_PROVIDER" not in text
        assert "HERMES_MODEL" not in text

    def test_dockerfile_copies_every_pt_skill_outside_the_home(self):
        import re

        dockerfile = (ROOT / "Dockerfile").read_text()
        skills = sorted(p.parent.name for p in ROOT.glob("pt-*/SKILL.md"))
        missing = [name for name in skills if f"COPY {name}/" not in dockerfile]
        assert missing == [], f"in the tree but never copied into the image: {', '.join(missing)}"
        for name in skills:
            assert re.search(
                rf"^COPY\s+{re.escape(name)}/\s+/opt/hermes/skills/{re.escape(name)}/\s*$",
                dockerfile,
                re.MULTILINE,
            ), f"COPY {name}/ does not land at /opt/hermes/skills/{name}/"
            assert f"/var/lib/hermes/skills/{name}" not in dockerfile
        assert "COPY runtime/SOUL.md /var/lib/hermes/SOUL.md" in dockerfile
        assert "COPY runtime/SOUL.md /opt/hermes/plow-seed/SOUL.md" in dockerfile
        assert "COPY runtime/USER.md /var/lib/hermes/memories/USER.md" in dockerfile
        # Boot recopies plow-seed over home; Sonnet lives there, not only in
        # runtime/config.yaml.
        assert "plow-seed/config.yaml" in dockerfile
        assert "moonshotai/kimi-k2.5" in dockerfile
        assert "02-copy-plow-credentials" in dockerfile
        assert "plow-credentials" in (ROOT / ".dockerignore").read_text()
        assert "plow-credentials" in (ROOT / ".gitignore").read_text()

    def test_dockerfile_installs_weasyprint_for_the_pdf_leg(self):
        # The base image has no HTML-to-PDF engine; the renderer's --pdf leg
        # only works because this image installs weasyprint. The build's own
        # import check is the guard that it actually imports (native Pango/
        # Cairo binding fails at import, not at install).
        dockerfile = ROOT / "Dockerfile"
        assert dockerfile.is_file(), "Dockerfile installs weasyprint for the PDF leg"
        text = dockerfile.read_text()
        assert "weasyprint" in text
        assert "import weasyprint" in text
        # The build check must RENDER, not just import: a pydyf/weasyprint
        # mismatch imports clean and dies on the first write_pdf.
        assert "write_pdf" in text
        assert "pydyf" in text
        # Installed into BOTH interpreters, because which one `python3` means
        # depends on the shell, and this flow uses both:
        #   sh -c / bash -c -> /opt/hermes/.venv/bin/python3
        #   bash -lc        -> /usr/bin/python3   (login resets PATH, dropping
        #                                          /opt/hermes/.venv/bin)
        # History, in order, all measured live: a system dist-packages
        # `--target` made the LOGIN shell work and the plain shell fail, so
        # this test was written to forbid a login-shell probe. Then on
        # 2026-09-16 the venv-only install shipped and the agent's terminal
        # tool -- which runs a LOGIN shell -- got ModuleNotFoundError, was
        # told "weasyprint is not installed", took the text fallback, and
        # handed the owner a wall of text twice while the venv rendered that
        # same edition.json to a valid PDF. Neither interpreter alone is
        # enough; the answer is both, and a probe that proves both.
        assert "--python /opt/hermes/.venv/bin/python3" in text
        assert "--python /usr/bin/python3" in text
        # The probe must exercise the plain shell AND the login shell: each
        # one alone has already shipped a broken PDF leg.
        assert "bash -lc" in text, "the build probe does not test a login shell"
        assert 'sh -c "python3 -c' in text, "the build probe does not test a plain shell"
        # Pinned by digest, like the fleet pin -- a tag re-resolves on pull.
        from_line = next(
            line for line in text.splitlines() if line.startswith("FROM ")
        )
        assert "@sha256:" in from_line

    def test_agent_env_names_the_built_image(self):
        env = (ROOT / "agent.env").read_text()
        assert "AGENT_IMAGE=the-plow-times-hermes-agent:local" in env, (
            "agent.env must name the built tag agent-mgr inspects for the contract"
        )


class TestImportability:
    def test_gate_imports_and_runs(self, tmp_path):
        gate = load_module("gate_contract", "pt-shared/scripts/pt_config_gate.py")
        path = tmp_path / "config.json"
        path.write_text('{"owner": {"timezone": "UTC"},'
                        ' "delivery": {"hour": "07:00"},'
                        ' "printer": {"configured": false}}')
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gate.main([str(path)])
        assert buf.getvalue().strip() == ""
