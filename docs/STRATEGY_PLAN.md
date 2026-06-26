# Strategy Guide Aggregator (Strategy Hunter)

- Status: Stage 1 (collection) implemented; Stage 2/3 planned
- Date: 2026-06-26
- See also: `docs/PRD.md`, `docs/WEB_PLAN.md`

Aggregates money-saving combination strategies scattered across forums and OzBargain,
distils them with AI into structured guides, and publishes them on the website — so users
don't have to dig around. Runs independently from `bargain_hunter` (single-deal alerts);
they are two separate pipelines.

---

## Two content types

| Type | Example | Notes |
|---|---|---|
| Evergreen playbook | "Cheapest way to buy a MacBook in AU" | Relatively stable, high SEO value |
| Live stack | "X gift cards 5% off + Cashrewards 3% right now" | Expires in days; can reuse deal pipeline |

---

## Three-stage pipeline

### Stage 1 — Collection (GitHub Actions, fully automated daily) ✅

`src/strategy_hunter/` follows the `bargain_hunter` `sources/` adapter pattern.

- **Sources** (configurable under `strategy:` in `config/settings.yaml`):
  - OzBargain forums: `/forum/1341` Find Me A Bargain, `/forum/38183` Financial (HTML scrape of board + thread OP)
  - Reddit: r/AusFinance, r/AusFrugal, r/fiaustralia (Atom RSS; requires browser UA)
  - Whirlpool: `/forum/153` Shopping, `/forum/150` Finance, `/forum/149` Travel (HTML)
- **Relevance filtering**: `relevance.py` counts money-saving signal words; posts below
  `min_relevance` are discarded to avoid feeding noise to the model.
- **Dedup + persistence**: one JSON per post at `data/strategies/raw/<source>/<id>.json`;
  only rewritten when `content_hash` changes (edited posts only).
- **Digest**: each day's new material is grouped by board, sorted by relevance, and rendered
  to `data/strategies/digest/<AET-date>.md` — ready for a model to read in one pass.
- Workflow `.github/workflows/collect-strategies.yml`; commits corpus with `[skip ci]`.

### Stage 2 — Extraction (local / subscriber model) 🔜

Feed the digest to Claude / ChatGPT etc. following the schema in
`src/strategy_hunter/prompts/extract_guide.md`. **Cluster by purchase goal** and produce
structured guide JSON at `data/strategies/guides/<id>.json`
(matching `strategy_hunter.models.Guide`). Model backend is pluggable (local Ollama works).

Validate after each run:
```
python -m strategy_hunter validate-guides
```
Checks: kebab-case id, unique ids, non-empty steps and sources, `confidence` ∈ 0..1.

### Stage 3 — Publish (website) ✅

`frontend/` (Next.js App Router) includes a public guides section:
- `app/guides/page.tsx` — list with client-side technique filter.
- `app/guides/[slug]/page.tsx` — detail page, edge-rendered; returns 404 when guide not found.
- `lib/guides.ts` — reads `data/strategies/guides/*.json` at build time; renders an empty state gracefully when no guides exist.
- Landing page nav includes a "Saving Guides" link; styles reuse `globals.css` design tokens.

---

## Data model

- `CapturedPost`: collection unit (forum thread / Reddit post) with source/title/body/board/relevance.
- `Guide`: structured guide = goal + technique combination + ordered steps + risks + sources + expiry + confidence.
  Techniques use a stable English enum (cashback / discounted_giftcard / education_store / ...) for filtering.

---

## Verified source structure (2026-06-26)

- Reddit: `/r/<sub>/<listing>.rss` (JSON endpoint returns 403; RSS works with a browser UA).
  Note: Reddit frequently returns `429` for **datacenter IPs** (e.g. GitHub Actions) on public RSS.
  Residential IPs generally work fine. For stable CI collection from Reddit, configure **OAuth (app-only)**:
  create a *script* app at reddit.com/prefs/apps, store `client_id` / `secret` as repo secrets
  `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` — the workflow passes them through automatically.
  Without credentials, the source gracefully skips on rate-limit (WARNING, not an error, no alert triggered).
- OzBargain: board `/forum/<id>` lists `/node/<id>` threads; first `div.content` in a thread = OP body.
- Whirlpool: board `/forum/<id>` lists `a.title[href^=/thread/]`; first `div.replytext` in a thread = OP.

---

## Roadmap

- Local extraction CLI + guide schema validation + MDX rendering
- Embedding-based clustering before synthesis (merge same-goal threads for higher quality)
- Expiry decay: when source deals expire, mark the guide as "may be outdated"
- PR review gate: model output opens a PR; merged by maintainer before going live
- Phase 2 sources: additional community forums (anti-scrape; semi-manual local collection recommended)
- Cross-feed with deal pipeline (evergreen playbooks ↔ live stacks)
