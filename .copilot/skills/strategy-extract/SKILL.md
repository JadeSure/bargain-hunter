---
name: strategy-extract
description: >-
  Stage 2 of the money-saving pipeline. Use when the user wants to
  purify/extract the collected strategy corpus (data/strategies/digest + raw)
  into structured guide JSON, and/or generate social media share content from
  those guides. Drives a Sonnet 4.6 subagent for the synthesis-heavy extraction
  while the orchestrator (current model) reviews, validates, and corrects.
  Trigger phrases: extract guides, run Stage 2.
---

# Strategy extraction (Stage 2)

Turn the raw harvested discussion into **deduplicated, executable guides**, then
optionally into social media posts. The split of labour is deliberate:

- **Sonnet 4.6** does the heavy synthesis (clustering messy threads by purchase
  goal, writing the guide JSON and social drafts). It is strong at long-context
  synthesis and structured JSON.
- **The orchestrator (you, the current model)** is the reviewer/corrector. You
  never blindly trust the subagent output — you validate the schema, fact-check
  every guide against its cited sources, and fix problems before anything lands.

Never fabricate prices, savings, or sources. A guide that cites a source the
corpus doesn't contain, or invents a discount, is a defect — drop or fix it.

## Inputs

- `data/strategies/digest/<AET-date>.md` — the latest day's LLM-ready digest
  (grouped by board, sorted by relevance). Default to the newest file.
- `data/strategies/raw/<source>/<id>.json` — full corpus, when the subagent
  needs more context than the digest excerpt provides (each post has `url`,
  `title`, `body`, `source`, `relevance`).
- `src/strategy_hunter/prompts/extract_guide.md` — the canonical role + schema.
- `data/strategies/guides/*.json` — already-published guides; do NOT duplicate
  an existing `id`/goal, extend or skip instead.

## Output

- Guides: `data/strategies/guides/<id>.json` (one per purchase goal; matches
  `strategy_hunter.models.Guide`).
- Social posts: `data/strategies/content/<id>.<platform>.md` where platform is
  `tieba` or `xhs`. See `social_post_spec.md`.

---

## Procedure

### 0. Scope the run

1. Find the newest digest: `ls -t data/strategies/digest/*.md | head -1`.
2. List existing guide ids so the run extends rather than duplicates:
   `ls data/strategies/guides/ 2>/dev/null`.
3. Decide the deliverable with the user if unclear: guides only, or guides +
   social content, and which platforms.

### 1. Purify — Sonnet 4.6 subagent

Launch ONE `general-purpose` task agent with `model: claude-sonnet-4.6`
(reasoning_effort high). Give it complete context (it is stateless):

- The full text of `src/strategy_hunter/prompts/extract_guide.md` (role + schema
  + field rules), or instruct it to read that file first.
- The newest digest path, and permission to open raw corpus files for context.
- The existing guide ids to avoid duplicates.
- These hard rules:
  - Cluster by **purchase goal**, not one-post-one-guide. Merge threads about
    the same goal (e.g. "cheap MacBook in AU", "best travel credit card").
  - Only emit guides that are **genuinely useful** for saving money. Skip chit-
    chat, news, and unanswered questions. Quality over quantity — 2 solid guides
    beat 10 thin ones.
  - Every `sources[]` URL MUST come from a corpus post. No invented URLs/prices.
  - Lower `confidence` when the corpus is thin; never overstate savings.
  - `id` is a kebab-case slug, unique across existing + new guides.
  - `techniques[]` use the stable English enum from the schema.
  - Write each guide to `data/strategies/guides/<id>.json` (valid JSON, UTF-8).
  - Set `generated_at` to the current UTC time (ISO 8601).
- Ask it to report: the ids it wrote, the goal of each, and which corpus posts
  (urls) fed each guide — so you can spot-check.

### 2. Review & correct — you (orchestrator)

This is the point of the two-model split. Do all of it:

1. **Schema + semantic gate:** run
   `python -m strategy_hunter validate-guides`.
   Fix every error it reports (kebab-case id, unique ids, non-empty steps &
   sources, `confidence` ∈ 0..1). Re-run until it passes.
2. **Source fact-check:** for each new guide, open the cited corpus posts
   (`data/strategies/raw/.../<id>.json` or fetch the `url`) and confirm:
   - each cited source actually exists in the corpus and supports the technique;
   - no price/percentage/claim was invented beyond what the source says;
   - the steps are genuinely actionable and in sensible order.
   Correct the JSON directly for small issues; for systemic problems, re-prompt
   the subagent with specifics.
3. **Dedup check:** no new `id` or goal collides with an existing guide.
4. **Trim noise:** delete any guide that is thin, speculative, or unsupported.

### 3. Generate share content (optional)

For each **approved** guide, produce social posts per `social_post_spec.md`:
`data/strategies/content/<id>.tieba.md` and/or `<id>.xhs.md`. The Sonnet 4.6
subagent can draft these from the guide JSON; you review for accuracy (same
no-fabrication bar) and tone before saving.

### 4. Corpus hygiene

- Time-based pruning is automatic on each `collect` run (`retention_days`).
- During extraction, simply ignore noise posts (low `relevance`, pure
  chit-chat). Do not hand-delete raw files unless they are clearly broken
  (empty body, parse garbage) — the collector will re-harvest live threads.

### 5. Wrap up

- Re-run `python -m strategy_hunter validate-guides` (must be clean).
- Summarise: guides added (ids + goals), social posts written, anything skipped
  and why.
- Commit guides + content together; the website (`/guides`) statically renders
  the new guide JSON on next build.

## Quality bar (reject if violated)

- A cited source is not in the corpus, or doesn't support the claim.
- Any fabricated price, discount, or "guaranteed" saving.
- `confidence` high on a thin/single-source guide.
- Duplicate of an existing guide's goal.
- `validate-guides` not green.
