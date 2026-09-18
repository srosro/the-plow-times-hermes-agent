# Manual checks

## E2E priority desk

Needs Latch on the Mac. Until a human run, **NEEDS HUMAN RUN**.

| # | Action | Expected |
| --- | --- | --- |
| 1 | New setup (`docker compose down -v`, "oi") | Questions in order: hour, printer, **priority** (the goal question), mail, sections |
| 2 | Answer the goal question | Creates `~/Plow/prioritization.md` with the answer under `## Goals` (or adds it to the existing file); seeds `~/Plow/advisors/` if missing |
| 3 | Check `pt/config.json` | `priority.configured: true`, `priority.file` |
| 4 | Force the edition (`hermes cron run pt-daily-edition`) | The page opens with `STAGE · …` and its reason, `TODAY` events with notes, a focus, `WHO` with real names, a `DRAFT`, `NOT TODAY` |
| 5 | Run again the next day | A `YESTERDAY` line checks the previous focus against what happened |
| 6 | Text "stop telling me to hire" | A dated line lands under `## Not now`; the next paper does not advise hiring |
| 7 | Deny the iMessage read on the Mac and run | Paper still ships; the desk works from calendar and mail |
| 8 | Rename the file on the Mac and run again | Page ships without the owner's goals; the rest of the paper is normal |
| 9 | Close Latch and run | Desk marks `unavailable`; the paper is still delivered |
