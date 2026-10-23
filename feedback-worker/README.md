# Feedback worker

A tiny Cloudflare Worker that receives 👍/👎 clicks from digest emails and writes
them to the Notion **Feedback** database. Serverless: it runs only on a click,
idles at $0, and the free plan (100k requests/day) is far beyond this use.

## Deployment is via Terraform

This worker is deployed by the Terraform module in [`../terraform`](../terraform) (state in R2). See its README for the deploy flow. The `wrangler` steps below are kept only for **local testing** (`wrangler dev`) and as an alternative manual deploy path.

## Deploy (first time)

```bash
cd feedback-worker
npm install -g wrangler        # or use npx wrangler ...
npx wrangler login             # opens browser, OAuth

# 1. Put the Notion token in as an encrypted secret (NOT in any file):
npx wrangler secret put NOTION_TOKEN      # paste your ntn_... when prompted

# 2. Set the Feedback DB id (printed by scripts/setup_notion.py) in wrangler.jsonc:
#    "FEEDBACK_DB_ID": "xxxxxxxx..."

# 3. Ship it:
npx wrangler deploy
```

`wrangler deploy` prints the public URL, e.g.
`https://bargain-feedback.<you>.workers.dev`.

## Wire it into the digest emails

Set the worker URL as `FEEDBACK_BASE_URL` for the Python app (local `.env` and
GitHub Actions secret/var). The email template then renders 👍/👎 links per deal.
If `FEEDBACK_BASE_URL` is unset, the links are simply omitted.

## Test

```bash
curl "https://bargain-feedback.<you>.workers.dev/?d=ozbargain:964116&v=up&e=test@example.com"
# -> a row appears in the Notion Feedback DB
```

## Hardening

- **Signed links.** Every link carries an HMAC token over `deal|verdict|email`
  (`FEEDBACK_HMAC_SECRET`); unsigned or tampered requests get a 403.
- **Mail-scanner pre-clicks.** Corporate scanners (Safe Links, Proofpoint,
  Mimecast) fetch every link before the user does. A `GET` therefore only
  verifies the token and serves a small page whose script `POST`s back to the
  same URL — only the `POST` writes to Notion. `HEAD` probes are answered
  without recording. A `<noscript>` confirm button covers users with scripts off.
- **Monitoring.** Each recorded vote logs `{deal, verdict, ua}` to Workers Logs
  (`npx wrangler tail bargain-feedback`, or the dashboard). A scanner that does
  run JS shows up there as a burst of votes with a non-browser user-agent.

Smoke test (GET must not write; POST must):

```bash
curl -I "$URL"            # 200, no row
curl "$URL"               # confirm page, no row
curl -X POST "$URL"       # row appears in the Feedback DB
```
