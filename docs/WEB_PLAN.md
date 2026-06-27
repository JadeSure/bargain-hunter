# Bargain Hunter Web Frontend Plan

- Status: **Shipped** — live on Cloudflare Pages + Workers. This doc now reflects
  what was actually built (Magic Link auth + access waitlist; Google OAuth was
  scaffolded but is not yet wired).
- Date: 2026-06-27
- Related docs: `docs/PRD.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## Tech Stack

| Layer | Technology | Deployment (now) | Deployment (AWS migration) |
|---|---|---|---|
| Frontend | Next.js 15 + TypeScript + Tailwind | Cloudflare Pages | OpenNext + CloudFront + S3 |
| API | Hono (TypeScript) | Cloudflare Worker | AWS Lambda (swap adapter) |
| Auth | Magic Link (email) · Google OAuth *(scaffolded, not wired)* | Cloudflare Worker | AWS Lambda (swap adapter) |
| Session / Token | Cloudflare KV | - | DynamoDB / ElastiCache |
| Data | Notion — existing **Subscribers** DB + separate **Waitlist** DB | - | Can migrate to DynamoDB |
| Email | Resend API (magic link + owner access-request notice) | - | AWS SES |
| UI Design | Claude Design | - | - |

**The Python scraping engine is unchanged and continues running on GitHub Actions cron.**

---

## Repository Structure (as built)

```
bargain-hunter/
  frontend/                    <- Next.js project (Cloudflare Pages)
    app/
      page.tsx                 <- Landing page (public) + "Request Access" modal
      login/
        page.tsx               <- Magic-link login (email only)
        check-email/page.tsx   <- "check your inbox" confirmation
      portal/
        layout.tsx             <- Auth-gated shell
        context.tsx, actions.ts<- Portal state + server actions
        page.tsx               <- Settings home
        keywords/page.tsx      <- Watch / block keyword management
        settings/page.tsx      <- Notification settings
      guides/
        page.tsx               <- Strategy guide index
        [slug]/page.tsx        <- Individual guide
        GuidesFilter.tsx       <- Client-side filter
    lib/api.ts                 <- Frontend wrapper for portal-worker calls
    middleware.ts              <- Protect /portal/* routes
    next.config.ts
    wrangler.toml              <- Cloudflare Pages config

  portal-worker/               <- Hono API Worker
    src/
      index.ts                 <- Entry, multi-origin CORS, route registration
      middleware/
        auth.ts                <- Session validation middleware (requireAuth)
      routes/
        auth/
          magic-link.ts        <- POST /auth/magic-link, GET /auth/verify
          request-access.ts    <- POST /auth/request-access (waitlist) · GET (owner-only list)
          logout.ts            <- POST /auth/logout
        subscriber.ts          <- GET/PUT /api/me
      lib/
        notion.ts              <- Read/write Notion Subscribers + Waitlist DBs
        kv.ts                  <- Session / magic-token operations
        email.ts               <- Resend magic link + owner access-request notice
        origins.ts             <- Parse FRONTEND_URL into a CORS allow-list
      types.ts
    wrangler.jsonc
    package.json

  terraform/                   <- Deploys BOTH feedback-worker and portal-worker
    main.tf                    <- Portal KV namespace, portal-worker script + subdomain
    variables.tf               <- subscribers_db_id, waitlist_db_id, resend_api_key,
                                  frontend_url, owner_email
```

> Google OAuth was scaffolded in `kv.ts` (`createOAuthState`/`verifyOAuthState`)
> but no `routes/auth/google.ts` or UI button ships yet — login is email-only.

---

## Implementation status (as built)

### Phase 1 — UI Design ✅
- [x] Landing page (hero, feature highlights, **Request Access** CTA)
- [x] Magic-link login page (email field; no Google button yet)
- [x] Portal (keyword management, notification settings, account info)
- [x] Strategy guide pages (`/guides`, `/guides/[slug]`)

### Phase 2 — Infrastructure ✅
- [x] Terraform: Cloudflare KV namespace (sessions + magic-link tokens)
- [x] Terraform: portal-worker script + `workers.dev` subdomain (`terraform/main.tf`)
- [x] Terraform vars: `subscribers_db_id`, `waitlist_db_id`, `resend_api_key`,
      `frontend_url`, `owner_email`
- [x] Deploy: portal-worker ships via **`terraform-feedback.yml`** (shared with the
      feedback worker) on pushes touching `portal-worker/src/**` or `terraform/**`
- [x] Deploy: frontend ships via **`deploy-frontend.yml`** (`wrangler pages deploy`)
- [ ] *(deferred)* Google OAuth vars / Pages project as a Terraform resource

### Phase 3 — Hono API Worker ✅
- [x] Scaffold `portal-worker/` (Hono + TypeScript + wrangler)
- [x] KV wrapper: session + magic-token CRUD (`lib/kv.ts`)
- [x] Notion wrapper: Subscribers read/update **and** Waitlist add/list (`lib/notion.ts`)
- [x] `POST /auth/magic-link` → token in KV → Resend email
- [x] `GET /auth/verify?token=…` → validate, set session cookie, redirect to portal
- [x] `POST /auth/request-access` → upsert into Notion **Waitlist** DB + notify owner
- [x] `GET /auth/request-access` (owner-only) → list waitlist
- [x] `POST /auth/logout` → clear session
- [x] Auth middleware (`requireAuth`): validate session cookie, inject user
- [x] `GET /api/me` / `PUT /api/me`: read/update Subscriber fields
- [ ] *(deferred)* `GET /auth/google` + callback (KV state helpers exist, no route)

### Phase 4 — Next.js Frontend ✅
- [x] `middleware.ts`: redirect unauthenticated `/portal/*` to `/login`
- [x] Landing (`/`) with Request Access modal
- [x] Login (`/login`) + `check-email` confirmation (replaces the planned
      `/auth/callback` page — verification is handled server-side by the worker)
- [x] Portal home + keywords + settings
- [x] Strategy guide index + detail pages

### Phase 5 — Polish
- [x] Multi-origin CORS — `FRONTEND_URL` is a comma-separated allow-list so the
      custom domain and `*.pages.dev` both work (`portal-worker/src/lib/origins.ts`)
- [x] Anti-enumeration: request-access / magic-link always return `{ok:true}`
- [ ] Mobile responsiveness / SEO polish — ongoing

---

## Fields Managed in the Portal

Corresponding to the existing `Subscriber` model — all editable in the portal:

| Field | Type | Description |
|---|---|---|
| `watch_keywords` | list[str] | Watch keywords, one per line |
| `block_keywords` | list[str] | Block keywords, one per line |
| `subscribe_hot` | bool | Whether to subscribe to hot deal alerts |
| `min_discount_percent` | float | Minimum discount threshold |
| `max_alerts_per_day` | int | Hot deals daily cap |
| `max_watch_alerts_per_day` | int | Watch alerts daily cap |
| `channels` | list[str] | Email / Telegram |
| `categories` | list[str] | Category preferences |

`name`, `email`, `telegram_chat_id` are read-only display fields (not editable in the portal, to avoid bypassing maintainer review).

---

## Auth Flows

### Magic Link (live)
```
User enters email → portal-worker generates token (15 min expiry), stores in KV
→ Resend sends email (with link) → user clicks link
→ portal-worker validates token → creates session cookie → redirects to /portal
```

### Access request / waitlist (live)
```
Visitor submits email in the "Request Access" modal
→ POST /auth/request-access → portal-worker upserts a row in the Notion
   Waitlist DB (dedup by email; bumps Count + Last Seen on repeats)
→ best-effort owner notification email (Resend)
→ always returns {ok:true} (anti-enumeration; the UI shows success regardless)
The maintainer reviews the Waitlist DB and manually adds approved emails to the
Subscribers DB, which is what unlocks magic-link login.
```

### Google OAuth *(deferred — not yet wired)*
```
Planned: "Sign in with Google" → portal-worker → Google → callback
→ validate email exists in Notion Subscribers DB → session cookie → /portal
```
KV state helpers (`createOAuthState`/`verifyOAuthState`) exist, but no route or
UI button ships yet.

**Login requires the email to exist in the Notion Subscribers database.**
Self-registration is not accepted — requests land in the Waitlist DB and the
maintainer manually promotes them.

---

## Migration to AWS (reference notes)

| Now | AWS replacement |
|---|---|
| Cloudflare Pages | CloudFront + S3 (via OpenNext) |
| Cloudflare Worker (Hono) | AWS Lambda (swap to `hono/aws-lambda` adapter) |
| Cloudflare KV | DynamoDB or ElastiCache |
| Resend | AWS SES |

Hono business logic code requires no changes — only the entry adapter is swapped.
