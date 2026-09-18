# Manual checks

## E2E priority desk

Needs Latch on the Mac. Until a human run, **NEEDS HUMAN RUN**.

| # | Action | Expected |
| --- | --- | --- |
| 1 | New setup (`docker compose down -v`, "oi") | Questions in order: hour, printer, **priority**, mail, sections |
| 2 | Answer "yes" on priority | Creates `~/Plow/prioritization.md` (or finds the existing one); seeds `~/Plow/advisors/` if missing |
| 3 | Fill the file: company state, goals, 1 deadline, 3 pieces of advice, one rule | — |
| 4 | Check `pt/config.json` | `priority.configured: true`, `priority.file` |
| 5 | Force the edition (`hermes cron run pt-daily-edition`) | The page opens with the priority; the "why" cites the file and the calendar |
| 6 | Check `run/desk-priority/advisors/` and `notes.json` | The advisor files copied raw; the notes carry a stage label, the stage's one-line reason as the first "why", a focus, and `NOT TODAY` |
| 6b | Tell the notes file the company is now at $14M ARR and run again | The stage moves to Scale and the reason says what moved |
| 6c | Delete `~/Plow/advisors/` and run | The desk is `unavailable`; the rest of the paper still ships |
| 7 | Read `pt/history.json` after the paper is delivered | Today's desk is recorded; nothing is recorded for a paper that failed to deliver |
| 8 | Rename the file on the Mac and run again | Page ships without the priority block (or with the notice); the rest of the paper is normal |
| 9 | Close Latch and run | Desk marks `unavailable`; the paper is still delivered |
