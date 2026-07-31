# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, GitHub Copilot, etc.) working
in this repository. Read this before making changes. Subdirectories may have
their own `AGENTS.md` that overrides this one for that subtree — **always read
`frontend/AGENTS.md` before touching `frontend/`.**

## What this project is

`bargain-hunter` is an automated, GitHub-Actions-driven deal + money-saving
pipeline for Australia. It is two Python packages plus a website and supporting
infra:

- **`src/bargain_hunter/`** — the core deal pipeline. Runs every 5 min, fetches
  OzBargain + CamelCamelCamel AU deals, scores them (Hot velocity / Watch
  keywords), and emails digests to subscribers stored in Notion.
- **`src/strategy_hunter/`** — a separate **daily** pipeline that harvests
  money-saving *discussion* (combos of techniques to buy things cheaply) and
  turns it into structured "guides". Three stages: **collect** (automated) →
  **extract** (automated via the Gemini API — `strategy-hunter extract`, gated on
  the `GEMINI_API_KEY` secret; opens a review PR, never commits to `main`; falls
  back to a manual LLM step when the key is unset, see
  `src/strategy_hunter/prompts/extract_guide.md`) →
  **publish** (the Next.js frontend renders `/guides`).
- **`frontend/`** — Next.js + React + Tailwind website. ⚠️ Uses a pre-release
  Next.js with breaking changes; read `frontend/AGENTS.md` and the bundled docs
  in `node_modules/next/dist/docs/` first.
- **`feedback-worker/`** — Cloudflare Worker that records digest 👍/👎 feedback
  into Notion. **`portal-worker/`** — Hono API Worker behind the website:
  magic-link auth, subscriber settings (`/api/me`), and the access-request
  **waitlist** (`POST /auth/request-access` → a separate Notion Waitlist DB).
  Google OAuth is scaffolded but not yet wired. CORS reads a comma-separated
  `FRONTEND_URL` allow-list. Both Workers deploy via Terraform.
- **`terraform/`** — infra (both Workers + portal KV + secrets), auto-deployed
  from `main` via `terraform-feedback.yml` (R2-backed state).

Design docs live in `docs/` (`PRD.md`, `IMPLEMENTATION_PLAN.md`,
`STRATEGY_PLAN.md`, `WEB_PLAN.md`).

## Core architecture: cross-file flows

These flows span multiple files and are easy to get wrong by editing just one.
Full formula/scoring detail lives in [`README.md`](README.md) — don't re-derive
it here, but know where the pieces live:

- **Hot scoring pipeline** (`bargain_hunter`): `config/settings.yaml
  (scoring.hot)` → `scoring.py` (`compute_vote_velocity` /
  `compute_comment_velocity` → `compute_hot_score` → `classify_hot` picks
  good/great/top) → `main.py` merges the hot verdict with any `matching.py`
  watch-keyword hit **for the same deal** into one notification → `notify/`
  renders and sends it. A deal state tracked across runs lives in `state.py`
  (`data/deals_state.json`, committed once/day as a calibration seed).
- **Watch matching** (`matching.py`): `_parse_keyword` parses the
  `PHRASE [<=PRICE] [@HH:MM|@YYYY-MM-DDTHH:MM]` syntax (see README's "Watch
  keyword syntax" table for examples/semantics) from the Notion Subscribers
  DB; `match_watch` / `filter_watch_matches` apply the noise guard (≥5 votes
  OzBargain / ≥10% discount CamelCamelCamel) before a keyword fires.
- **Alerting throttle** (`alert_throttle.py`): maintainer failure emails only
  after 3 consecutive pipeline failures, then at most hourly — a clean run
  resets the counter. Don't bypass this when adding new failure paths in
  `main.py`.
- **Portal auth proxy**: `portal-worker` (Hono, deployed to
  `*.workers.dev`) issues the session cookie, but the site is served from a
  different origin (`*.pages.dev`/custom domain via Cloudflare Pages), so
  cookies can't be shared directly. Two Next.js edge route handlers —
  `frontend/app/auth/verify/route.ts` and
  `frontend/app/api/[...path]/route.ts` — re-emit the worker's cookie on the
  Pages origin and forward authenticated calls to the worker. If you add a
  new authenticated portal-worker route, it must be reachable through the
  `[...path]` proxy, not called directly from the browser.
- **Deals board** (`/deals` on the frontend): statically rebuilt from the
  pipeline's deal observations (not live-queried) — a deal stays listed for
  up to 72h after it last trended, then drops off at the *next* rebuild.

## Setup, build, test, lint

Python 3.12+. From the repo root:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # install package + dev tools (pytest, ruff)
ruff check .                # lint
pytest                      # run the whole suite
```

- Run the **smallest** targeted check that covers your change, e.g.
  `pytest tests/test_strategy_reddit.py -q` and
  `ruff check src/strategy_hunter/sources/reddit.py`. Escalate to the full suite
  only when needed.
- Tests use `pythonpath=["src"]` (configured in `pyproject.toml`), so import
  packages directly (`from strategy_hunter.sources.reddit import RedditSource`).
- Network-touching sources are tested against **frozen fixtures** in
  `tests/fixtures/` — add a fixture rather than hitting the network in tests.

CLI entry points (defined in `pyproject.toml [project.scripts]`):

```bash
bargain-hunter --dry-run         # deal pipeline, no emails sent
strategy-hunter collect          # daily harvest → corpus + digest + prune
strategy-hunter digest           # rebuild digest from stored corpus
strategy-hunter validate-guides  # validate Stage 2 guide JSON against the schema
```

## Conventions

- **Lint = ruff** (`line-length = 100`, `target-version = py312`, rules
  `E,F,I,UP,B,SIM,DTZ`). Notable: `DTZ` forbids naive datetimes — **always use
  timezone-aware `datetime`** (`datetime.now(UTC)`, `datetime.fromtimestamp(x,
  UTC)`); `SIM105` prefers `contextlib.suppress`.
- **Models = Pydantic v2** (`src/**/models.py`). `bargain_hunter`'s `Settings`
  is strict (`extra="forbid"`).
- **XML parsing = `defusedxml`**, never stdlib `xml.etree` directly.
- **HTTP = `httpx`**. Real sources send a browser User-Agent and pace requests;
  handle rate limits gracefully (retry/backoff, then skip) rather than crashing
  a whole run — one bad source must not sink the pipeline.
- **Comments**: only where they add genuine clarity. No narration.

### ⚠️ Shared config: `config/settings.yaml`

This single file is read by **both** packages. `bargain_hunter.config.Settings`
uses `extra="forbid"`, so **adding any new top-level section breaks the deal
pipeline** unless `Settings` tolerates it (the `strategy:` block is passed
through via a `strategy: dict | None` field). `strategy_hunter` has its own
loader (`load_strategy_config`). When editing this file, keep both consumers in
mind and run the full `pytest` suite.

### Secrets

`.env` is git-ignored; copy from `.env.example`. **Never commit secrets.** CI
reads credentials from GitHub Actions secrets. New optional integrations should
degrade gracefully when their secrets are unset (e.g. the Reddit source falls
back to public RSS when `REDDIT_CLIENT_ID`/`SECRET` are absent).

## Git / commits

- **Conventional Commits**: `fix(strategy): …`, `feat(...): …`, `chore: …`,
  `fix(ci): …`. Scope by area (`strategy`, `ci`, `frontend`, …).
- The deal pipeline auto-commits observations to `main` every few minutes with
  `[skip ci]`, so `main` moves constantly — **rebase and retry** when pushing,
  and add `[skip ci]` to data/corpus commits that shouldn't trigger CI.
- Keep changes surgical and scoped to the task; don't fix unrelated code.

## Repo map

```
src/bargain_hunter/     deal pipeline (fetch, score, match, notify)
src/strategy_hunter/    daily guide pipeline (collect → digest → guides)
  sources/              one module per source (reddit, ozbargain*, whirlpool)
  prompts/              Stage-2 LLM extraction prompt + schema
config/settings.yaml    shared config for BOTH packages (see warning above)
data/strategies/        raw corpus, digests, and extracted guides (committed)
frontend/               Next.js site + portal UI (read frontend/AGENTS.md first!)
portal-worker/          Hono API Worker: magic-link auth, settings, access waitlist
feedback-worker/        Cloudflare Worker: digest 👍/👎 feedback → Notion
terraform/              deploys both Workers + portal KV (R2-backed state)
.github/workflows/      hunt.yml (deals), collect-strategies.yml (guides),
                        terraform-feedback.yml (Workers), deploy-frontend.yml (Pages)
tests/ + tests/fixtures frozen-fixture tests; pythonpath=src
docs/                   PRD, implementation + strategy + web plans
```
