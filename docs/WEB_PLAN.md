# Bargain Hunter Web Frontend Plan

- Status: Planning
- Date: 2026-06-26
- Related docs: `docs/PRD.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## Tech Stack

| Layer | Technology | Deployment (now) | Deployment (AWS migration) |
|---|---|---|---|
| Frontend | Next.js 15 + TypeScript + Tailwind | Cloudflare Pages | OpenNext + CloudFront + S3 |
| API | Hono (TypeScript) | Cloudflare Worker | AWS Lambda (swap adapter) |
| Auth | Magic Link + Google OAuth | - | - |
| Session / Token | Cloudflare KV | - | DynamoDB / ElastiCache |
| Data | Notion (existing Subscriber DB) | - | Can migrate to DynamoDB |
| Email (Magic Link) | Resend API | - | AWS SES |
| UI Design | Claude Design | - | - |

**The Python scraping engine is unchanged and continues running on GitHub Actions cron.**

---

## Repository Structure (new additions)

```
bargain-hunter/
  frontend/                    <- Next.js project
    app/
      page.tsx                 <- Landing page (public)
      login/
        page.tsx               <- Login page (Magic Link + Google)
      portal/
        page.tsx               <- Personal settings home
        keywords/page.tsx      <- Watch / block keyword management
        settings/page.tsx      <- Notification settings
      auth/
        callback/page.tsx      <- OAuth / magic link callback handler
    components/
    lib/
      api.ts                   <- Frontend wrapper for portal-worker calls
    middleware.ts              <- Protect /portal/* routes
    next.config.ts
    package.json
    wrangler.toml              <- Cloudflare Pages config

  portal-worker/               <- Hono API Worker
    src/
      index.ts                 <- Entry point, route registration
      middleware/
        auth.ts                <- Session validation middleware
      routes/
        auth/
          magic-link.ts        <- POST /auth/magic-link, GET /auth/verify
          google.ts            <- GET /auth/google, GET /auth/google/callback
          logout.ts            <- POST /auth/logout
        subscriber.ts          <- GET/PUT /api/me
      lib/
        notion.ts              <- Read/write Notion Subscriber DB
        kv.ts                  <- Session / token operation wrapper
        email.ts               <- Resend magic link email sending
    wrangler.jsonc
    package.json

  terraform/                   <- Extends existing config
    main.tf                    <- Added: KV namespace, portal-worker, Pages project
    variables.tf               <- Added: google_client_id/secret, resend_api_key
```

---

## Implementation Phases

### Phase 1 — UI Design (Claude Design)

- [ ] Landing page design
  - Hero: one sentence explaining what the product does
  - Feature highlights: hot deal alerts / keyword watching / precise filtering
  - CTA: request access / log in
- [ ] Login page design
  - Magic Link input field
  - Google login button
- [ ] Portal design
  - Keyword management (watch / block)
  - Notification settings (toggles, daily cap, minimum discount, categories)
  - Account information

### Phase 2 — Infrastructure

- [ ] Terraform: add Cloudflare KV namespace (session + magic link token)
- [ ] Terraform: add portal-worker resource
- [ ] Terraform: add Cloudflare Pages project
- [ ] Terraform: add variables (Google OAuth, Resend API key)
- [ ] GitHub Actions: `portal-worker` deploy workflow
- [ ] GitHub Actions: `frontend` deploy workflow (Pages)

### Phase 3 — Hono API Worker

- [ ] Scaffold project: `portal-worker/`, Hono + TypeScript + wrangler
- [ ] KV wrapper: session CRUD, magic link token CRUD
- [ ] Notion wrapper: read Subscriber by email, update Subscriber fields
- [ ] `POST /auth/magic-link`: generate token, store in KV, send Resend email
- [ ] `GET /auth/verify?token=xxx`: validate token, create session, redirect to portal
- [ ] `GET /auth/google`: redirect to Google OAuth
- [ ] `GET /auth/google/callback`: handle callback, create session
- [ ] `POST /auth/logout`: clear session
- [ ] Auth middleware: validate session cookie, inject user context
- [ ] `GET /api/me`: return current user's Subscriber data
- [ ] `PUT /api/me`: update keywords / settings, write back to Notion

### Phase 4 — Next.js Frontend

- [ ] Scaffold project: `frontend/`, Next.js 15 + Tailwind + TypeScript
- [ ] `middleware.ts`: redirect unauthenticated `/portal/*` access to `/login`
- [ ] Landing page (`/`): implement per design
- [ ] Login page (`/login`): Magic Link form + Google login button
- [ ] Auth callback page (`/auth/callback`): handle magic link / OAuth redirects
- [ ] Portal home (`/portal`): overview, links to sub-pages
- [ ] Keyword management (`/portal/keywords`): add/remove watch keywords, add/remove block keywords
- [ ] Notification settings (`/portal/settings`):
  - Toggle: subscribe to hot deals (`subscribe_hot`)
  - Max daily alerts (`max_alerts_per_day`, `max_watch_alerts_per_day`)
  - Minimum discount (`min_discount_percent`)
  - Notification channels (`channels`: Email / Telegram)
  - Category preferences (`categories`)

### Phase 5 — Polish

- [ ] Error handling: API error messages, friendly token expiry messages
- [ ] Mobile responsiveness
- [ ] Basic SEO: `<title>`, `<meta description>`, Open Graph
- [ ] Confirm temporary domains are accessible (`*.pages.dev` + `*.workers.dev`)

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

### Magic Link
```
User enters email → portal-worker generates token (15 min expiry), stores in KV
→ Resend sends email (with link) → user clicks link
→ portal-worker validates token → creates session cookie → redirects to /portal
```

### Google OAuth
```
User clicks "Sign in with Google" → portal-worker redirects to Google
→ user authorises → Google callbacks portal-worker
→ validate email exists in Notion Subscriber DB
→ create session cookie → redirect to /portal
```

**Both methods require the email to exist in the Notion subscriber database.** Self-registration is not accepted — the maintainer manually adds subscribers.

---

## Migration to AWS (reference notes)

| Now | AWS replacement |
|---|---|
| Cloudflare Pages | CloudFront + S3 (via OpenNext) |
| Cloudflare Worker (Hono) | AWS Lambda (swap to `hono/aws-lambda` adapter) |
| Cloudflare KV | DynamoDB or ElastiCache |
| Resend | AWS SES |

Hono business logic code requires no changes — only the entry adapter is swapped.
