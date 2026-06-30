# Bargain Hunter — Web frontend

Next.js + React + Tailwind site for [bargain-hunter](../README.md), deployed to
**Cloudflare Pages**. It serves four things:

- **Landing** (`/`) — product pitch + a "Request Access" modal that posts to the
  portal worker's access **waitlist**.
- **Hot Deals** (`/deals`) — a live board of currently-trending OzBargain /
  CamelCamelCamel deals, statically rebuilt from the pipeline's deal
  observations (`data/observations/*.jsonl`, via `lib/deals.ts`). A deal stays
  listed while it is still active (present in the latest scan batch), for up to
  **72h** after it was last flagged hot, ordered by tier
  (🔥 Top → ⚡ Great → ✅ Good). Expired/out-of-stock deals are absent from the
  latest batch and drop off at the next rebuild.
- **Strategy guides** (`/guides`, `/guides/[slug]`) — statically generated from
  `data/strategies/guides/*.json`.
- **Subscriber portal** (`/portal/*`) — magic-link login, watch/block keyword
  management, and notification settings. `/portal/*` is gated by `middleware.ts`.

> ⚠️ This pins a **pre-release Next.js** with breaking changes. Read
> `frontend/AGENTS.md` and the bundled guides in `node_modules/next/dist/docs/`
> before editing.

## Dev

```bash
npm install
npm run dev        # http://localhost:3000
```

The portal calls the `portal-worker` API at `NEXT_PUBLIC_WORKER_URL`
(see `lib/api.ts`). Set it in `.env.local` for local testing, e.g.
`NEXT_PUBLIC_WORKER_URL=https://bargain-portal-api.<subdomain>.workers.dev`.

`npm run build:cf` runs `next build` + `@cloudflare/next-on-pages` to produce the
Pages output locally; `npm run lint` runs ESLint.

## Deploy

Pushing to `main` (paths `frontend/**` or `data/strategies/guides/**`) triggers
`.github/workflows/deploy-frontend.yml`, which builds with `next-on-pages` and
runs `wrangler pages deploy`. The worker URL is injected via the workflow's
`NEXT_PUBLIC_WORKER_URL` env. The portal API itself (`portal-worker`) deploys
separately through Terraform — see `terraform/README.md`.

Because **Hot Deals** (`/deals`) reads `data/observations/**` (not in the push
`paths`), the same workflow also redeploys after each successful **`bargain-hunter`**
pipeline run (`workflow_run`, gated to ~one deploy / 30 min) plus a throttled
`*/30` cron backup, so newly-hot deals reach the page without a code change.
