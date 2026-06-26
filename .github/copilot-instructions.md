# GitHub Copilot instructions

The full, canonical agent guide for this repo is **[`/AGENTS.md`](../AGENTS.md)** —
read it first. Key points repeated here so Copilot has them inline:

## Project

`bargain-hunter` = two Python (3.12+) packages run by GitHub Actions:
`src/bargain_hunter/` (deal pipeline, every 5 min) and `src/strategy_hunter/`
(daily money-saving "guide" pipeline: collect → extract → publish). Plus a
Next.js site in `frontend/` and Cloudflare Workers. Read `frontend/AGENTS.md`
before touching `frontend/` — it pins a pre-release Next.js with breaking
changes.

## Build / test / lint

```bash
pip install -e ".[dev]"
ruff check .     # line-length 100, py312, rules E,F,I,UP,B,SIM,DTZ
pytest           # pythonpath=src; tests use fixtures in tests/fixtures/
```

Prefer the smallest targeted `pytest`/`ruff` selector for your change.

## Conventions

- Pydantic v2 models; **timezone-aware datetimes only** (ruff `DTZ`).
- Parse XML with `defusedxml`; HTTP via `httpx` with a browser UA.
- A source that fails/rate-limits must be skipped gracefully — never crash the
  whole run. Optional integrations degrade when their secrets are unset.
- **`config/settings.yaml` is shared by both packages**; `bargain_hunter`'s
  `Settings` is `extra="forbid"`, so adding a top-level section can break the
  deal pipeline unless it's tolerated. Run the full suite after editing it.
- **Never commit secrets**; `.env` is git-ignored, CI uses Actions secrets.
- Conventional Commits (`fix(strategy): …`, `chore: …`). `main` moves often
  (auto `[skip ci]` commits) — rebase and retry on push.
