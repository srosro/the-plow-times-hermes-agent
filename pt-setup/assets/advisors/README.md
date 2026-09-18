# Advisor notes

Markdown files the paper cites when it picks today's #1. Seeded on setup into
`~/Plow/advisors/`. Edit them, add other investors, delete what does not fit.

## Seeded files

Patrick Salyer (Mayfield), prefixed `salyer-` so other investors' files can sit
alongside. Each file's `source` lists the posts that back its claims.

- `salyer-stage-map.md` — `stages: any`, so it is in context every morning: what each
  stage means, the signals that place a company in one, the pivot override, the
  fundraising modifier, the B2B domain caveat, and the tie-break.
- `salyer-discovery.md` — $0–1M ARR: reach product-market fit.
- `salyer-blueprint.md` — $1–10M ARR: the founder-written playbook, reps at 3x OTE.
- `salyer-scale.md` — $10M+ ARR: the ramp model, from doing to designing.
- `salyer-pivot.md` — any ARR: an acute shock to the company or its model.
- `salyer-fundraising.md` — any stage, while raising: round bars and the pitch.

## File shape

```markdown
---
advisor: Name (firm)
stages: blueprint
domain: b2b-saas-enterprise
source: https://example.com/the-public-post
---
# Blueprint — $1–10M ARR

## Signals
- How you recognize this stage.

## Focus first
- The one job of this stage.

## Do not focus on
- What not to do here.

## Benchmarks
- Numbers that belong to this stage.

## Exit criteria
- How you know you left the stage.
```

- `stages`: one or more of `discovery`, `blueprint`, `scale`, `pivot`, `fundraising`, `any`.
- `source`: the public URLs behind the file's claims, comma-separated on one line.
- `domain`: free label. If company state reads consumer/PLG and the file says
  B2B enterprise, the paper prints a warning instead of hiding the advice.
- Recognized sections: `signals`, `focus` (`Focus first`), `avoid` (`Do not focus on`),
  `benchmarks`, `exit`. Other headings stay as context.
- Quotes on the page are at most 25 words.
